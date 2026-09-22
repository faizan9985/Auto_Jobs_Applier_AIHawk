import json
import os
import random
import time
from itertools import product
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

import src.utils as utils
from src.job import Job
from src.job_store import JobStore, PENDING
from src.aihawk_easy_applier import AIHawkEasyApplier
from loguru import logger
import urllib.parse
import yaml


class EnvironmentKeys:
    def __init__(self):
        logger.debug("Initializing EnvironmentKeys")
        self.skip_apply = self._read_env_key_bool("SKIP_APPLY")
        self.disable_description_filter = self._read_env_key_bool("DISABLE_DESCRIPTION_FILTER")
        logger.debug(f"EnvironmentKeys initialized: skip_apply={self.skip_apply}, disable_description_filter={self.disable_description_filter}")

    @staticmethod
    def _read_env_key(key: str) -> str:
        value = os.getenv(key, "")
        logger.debug(f"Read environment key {key}: {value}")
        return value

    @staticmethod
    def _read_env_key_bool(key: str) -> bool:
        value = os.getenv(key) == "True"
        logger.debug(f"Read environment key {key} as bool: {value}")
        return value


class AIHawkJobManager:
    def __init__(self, driver):
        logger.debug("Initializing AIHawkJobManager")
        self.driver = driver
        self.set_old_answers = set()
        self.easy_applier_component = None
        self.manual_approval_before_submit = True
        self.job_store = None
        self.database_path = Path("data_folder/output/jobs.sqlite3")
        self.retry_failed = False
        self.include_deferred = False
        self.retry_interrupted = False
        self.selected_job_ids = ()
        self.relevance_resume = None
        logger.debug("AIHawkJobManager initialized successfully")

    def set_parameters(self, parameters):
        logger.debug("Setting parameters for AIHawkJobManager")
        self.manual_approval_before_submit = parameters.get('manual_approval_before_submit', True)
        if type(self.manual_approval_before_submit) is not bool:
            raise ValueError("manual_approval_before_submit must be a boolean")
        self.company_blacklist = parameters.get('company_blacklist', []) or []
        self.title_blacklist = parameters.get('title_blacklist', []) or []
        self.location_blacklist = parameters.get('location_blacklist', []) or []
        self.positions = parameters.get('positions', [])
        self.locations = parameters.get('locations', [])
        self.apply_once_at_company = parameters.get('apply_once_at_company', False)
        self.base_search_url = self.get_base_search_url(parameters)
        self.seen_jobs = []

        job_applicants_threshold = parameters.get('job_applicants_threshold', {})
        self.min_applicants = job_applicants_threshold.get('min_applicants', 0)
        self.max_applicants = job_applicants_threshold.get('max_applicants', float('inf'))

        resume_path = parameters.get('uploads', {}).get('resume', None)
        self.resume_path = Path(resume_path) if resume_path and Path(resume_path).exists() else None
        self.output_file_directory = Path(parameters['outputFileDirectory'])
        self.database_path = Path(parameters.get('database_path') or self.output_file_directory / 'jobs.sqlite3')
        self.retry_failed = parameters.get('retry_failed', False)
        self.include_deferred = parameters.get('include_deferred', False)
        self.retry_interrupted = parameters.get('retry_interrupted', False)
        self.selected_job_ids = parameters.get('job_ids', ())
        profile_path = parameters.get('uploads', {}).get('plainTextResume')
        if profile_path:
            self.relevance_resume = yaml.safe_load(Path(profile_path).read_text(encoding='utf-8')) or {}
        self.env_config = EnvironmentKeys()
        logger.debug("Parameters set successfully")

    def set_gpt_answerer(self, gpt_answerer):
        logger.debug("Setting GPT answerer")
        self.gpt_answerer = gpt_answerer

    def set_resume_generator_manager(self, resume_generator_manager):
        logger.debug("Setting resume generator manager")
        self.resume_generator_manager = resume_generator_manager

    def start_collecting_data(self):
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)
        page_sleep = 0
        minimum_time = 60 * 5
        minimum_page_time = time.time() + minimum_time

        for position, location in searches:
            location_url = "&location=" + location
            job_page_number = -1
            utils.printyellow(f"Collecting data for {position} in {location}.")
            try:
                while True:
                    page_sleep += 1
                    job_page_number += 1
                    utils.printyellow(f"Going to job page {job_page_number}")
                    self.next_job_page(position, location_url, job_page_number)
                    time.sleep(random.uniform(1.5, 3.5))
                    utils.printyellow("Starting the collecting process for this page")
                    self.read_jobs()
                    utils.printyellow("Collecting data on this page has been completed!")

                    time_left = minimum_page_time - time.time()
                    if time_left > 0:
                        utils.printyellow(f"Sleeping for {time_left} seconds.")
                        time.sleep(time_left)
                        minimum_page_time = time.time() + minimum_time
                    if page_sleep % 5 == 0:
                        sleep_time = random.randint(1, 5)
                        utils.printyellow(f"Sleeping for {sleep_time / 60} minutes.")
                        time.sleep(sleep_time)
                        page_sleep += 1
            except Exception as exc:
                logger.info(f"Discovery search ended: {exc}")
            time_left = minimum_page_time - time.time()
            if time_left > 0:
                utils.printyellow(f"Sleeping for {time_left} seconds.")
                time.sleep(time_left)
                minimum_page_time = time.time() + minimum_time
            if page_sleep % 5 == 0:
                sleep_time = random.randint(50, 90)
                utils.printyellow(f"Sleeping for {sleep_time / 60} minutes.")
                time.sleep(sleep_time)
                page_sleep += 1

    def _store(self):
        if self.job_store is None:
            self.job_store = JobStore(self.database_path)
        return self.job_store

    def _candidate(self):
        profile = getattr(getattr(self, "gpt_answerer", None), "job_application_profile", None)
        return getattr(profile, "candidate_eligibility", None)

    def start_applying(self):
        """Apply only to the stored inventory; never run a search here."""
        self.easy_applier_component = AIHawkEasyApplier(
            self.driver, self.resume_path, self.set_old_answers,
            self.gpt_answerer, self.resume_generator_manager,
            self.manual_approval_before_submit,
            approval_callback=self._persist_approval,
            submitted_callback=self._persist_submission)
        return self.apply_jobs()

    def _persist_approval(self, job):
        decision = job.approval["decision"]
        state = {"approve": "approved", "auto_submit": "approved", "skip": "skipped",
                 "defer": "deferred", "abort": "deferred"}[decision]
        self._store().transition(job, state)

    def _persist_submission(self, job):
        self._store().transition(job, "submitted")

    def _export_result(self, job, name):
        # JSON is a compatibility export. A failed export cannot undo DB state.
        try:
            self.write_to_file(job, name)
        except Exception as exc:
            logger.warning(f"SQLite saved; JSON export failed for {job.job_id}: {exc}")

    def get_jobs_from_page(self):

        try:

            no_jobs_element = self.driver.find_element(By.CLASS_NAME, 'jobs-search-two-pane__no-results-banner--expand')
            if 'No matching jobs found' in no_jobs_element.text or 'unfortunately, things aren' in self.driver.page_source.lower():
                logger.debug("No matching jobs found on this page, skipping.")
                return []

        except NoSuchElementException:
            pass

        try:
            job_results = self.driver.find_element(By.CLASS_NAME, "jobs-search-results-list")
            utils.scroll_slow(self.driver, job_results)
            utils.scroll_slow(self.driver, job_results, step=300, reverse=True)

            job_list_elements = self.driver.find_elements(By.CLASS_NAME, 'scaffold-layout__list-container')[
                0].find_elements(By.CLASS_NAME, 'jobs-search-results__list-item')
            if not job_list_elements:
                logger.debug("No job class elements found on page, skipping.")
                return []

            return job_list_elements

        except NoSuchElementException:
            logger.debug("No job results found on the page.")
            return []

        except Exception as e:
            logger.error(f"Error while fetching job elements: {e}")
            return []

    def read_jobs(self):
        tiles = self.get_jobs_from_page()
        if not tiles:
            raise RuntimeError("No more jobs on this page")
        # Extract tiles before navigating, so Selenium elements cannot become stale.
        jobs = [Job(*self.extract_job_information_from_tile(tile)) for tile in tiles]
        search_url = self.driver.current_url
        reader = AIHawkEasyApplier(self.driver, None, [], None, None)
        for job in jobs:
            store = self._store()
            row = store.upsert(job)
            job = store.to_job(row)
            try:
                if job.link:
                    self.driver.get(job.link)
                    time.sleep(random.uniform(1.5, 3.5))
                    description = reader._get_job_description()
                    if description:
                        job.description = description
            except Exception as exc:
                logger.warning(f"Description unavailable for {job.link}: {exc}")
            job.evaluate_eligibility(self._candidate())
            store.evaluate(job)
            if self.relevance_resume is not None:
                store.score(job, self.relevance_resume)
            if (store.get(job.job_id)["state"] in PENDING and
                    self.is_blacklisted(job.title, job.company, job.link, job.location)):
                job.application_status = "skipped"
                store.transition(job, "skipped")
                self._export_result(job, "skipped")
            else:
                self._export_result(job, "data")
        self.driver.get(search_url)

    def apply_jobs(self):
        store = self._store()
        states = list(PENDING)
        if self.retry_failed:
            states.append("failed")
        if self.include_deferred:
            states.append("deferred")
        if self.retry_interrupted:
            states.extend(["applying", "approved"])
        if self.relevance_resume is not None:
            store.rescore(self.relevance_resume, states, self.selected_job_ids)
        for row in store.list_jobs(states, self.selected_job_ids):
            job = store.to_job(row)
            job.evaluate_eligibility(self._candidate())
            store.evaluate(job)
            if (self.is_blacklisted(job.title, job.company, job.link, job.location) or
                    (self.apply_once_at_company and store.has_submitted_company(job.company)) or
                    job.apply_method in {"Continue", "Applied", "Apply"}):
                # Preserve existing non-eligibility application restrictions.
                if row["state"] in PENDING:
                    job.application_status = "skipped"
                    store.transition(job, "skipped")
                    self._export_result(job, "skipped")
                continue
            job.approval = None
            job.application_answers = []
            job.application_status = "applying"
            try:
                # Atomic claim prevents two processes from applying the same pending job.
                store.transition(job, "applying", retry=row["state"] not in PENDING,
                                 expected_state=store.get(job.job_id)["state"] if row["state"] in PENDING else row["state"])
            except ValueError:
                logger.info(f"Job {job.job_id} was already claimed; leaving it alone")
                continue
            try:
                status = self.easy_applier_component.job_apply(job)
                if status not in {"submitted", "skipped_by_user", "deferred_for_review", "aborted"}:
                    raise ValueError(f"Unexpected application status: {status}")
                job.application_status = status
                state = {"submitted": "submitted", "skipped_by_user": "skipped",
                         "deferred_for_review": "deferred", "aborted": "deferred"}[status]
                if store.get(job.job_id)["state"] != state:
                    store.transition(job, state)
                self._export_result(job, "success" if status == "submitted" else status)
                if status == "aborted":
                    return "aborted"
            except Exception as exc:
                if job.application_status == "submitted":
                    logger.error(f"Submission clicked for {job.job_id}; check its database state before retrying: {exc}")
                    continue
                job.application_status = "failed"
                # A confirmed click remains submitted even if a later browser operation fails.
                if store.get(job.job_id)["state"] in {"applying", "approved"}:
                    store.transition(job, "failed", failure_reason=str(exc))
                    self._export_result(job, "failed")
                logger.error(f"Application error for {job.job_id}: {exc}")

    def write_to_file(self, job, file_name):
        logger.debug(f"Writing job application result to file: {file_name}")
        if job.eligibility is None:
            profile = getattr(getattr(self, "gpt_answerer", None), "job_application_profile", None)
            job.evaluate_eligibility(getattr(profile, "candidate_eligibility", None))
        pdf_path = Path(job.pdf_path).resolve()
        pdf_path = pdf_path.as_uri()
        data = {
            "job_id": job.job_id,
            "description": job.description,
            "apply_method": job.apply_method,
            "company": job.company,
            "job_title": job.title,
            "link": job.link,
            "job_recruiter": job.recruiter_link,
            "job_location": job.location,
            "pdf_path": pdf_path,
            "eligibility": job.eligibility,
            "application_status": job.application_status or file_name,
            "approval": job.approval,
            "cover_letter_path": job.cover_letter_path,
            "application_answers": job.application_answers
        }
        if self.job_store is not None and job.job_id:
            row = self.job_store.get(job.job_id)
            data.update(state=row['state'], submitted_at=row['submitted_at'],
                        failure_reason=row['failure_reason'])
        file_path = self.output_file_directory / f"{file_name}.json"
        self.output_file_directory.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([data], f, indent=4)
                logger.debug(f"Job data written to new file: {file_name}")
        else:
            with open(file_path, 'r+', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    logger.error(f"JSON decode error in file: {file_path}")
                    existing_data = []
                existing_data.append(data)
                f.seek(0)
                json.dump(existing_data, f, indent=4)
                f.truncate()
                logger.debug(f"Job data appended to existing file: {file_name}")

    def get_base_search_url(self, parameters):
        logger.debug("Constructing base search URL")
        url_parts = []
        if parameters['remote']:
            url_parts.append("f_CF=f_WRA")
        experience_levels = [str(i + 1) for i, (level, v) in enumerate(parameters.get('experience_level', {}).items()) if
                             v]
        if experience_levels:
            url_parts.append(f"f_E={','.join(experience_levels)}")
        url_parts.append(f"distance={parameters['distance']}")
        job_types = [key[0].upper() for key, value in parameters.get('jobTypes', {}).items() if value]
        if job_types:
            url_parts.append(f"f_JT={','.join(job_types)}")
        date_mapping = {
            "all time": "",
            "month": "&f_TPR=r2592000",
            "week": "&f_TPR=r604800",
            "24 hours": "&f_TPR=r86400"
        }
        date_param = next((v for k, v in date_mapping.items() if parameters.get('date', {}).get(k)), "")
        url_parts.append("f_LF=f_AL")  # Easy Apply
        base_url = "&".join(url_parts)
        full_url = f"?{base_url}{date_param}"
        logger.debug(f"Base search URL constructed: {full_url}")
        return full_url

    def next_job_page(self, position, location, job_page):
        logger.debug(f"Navigating to next job page: {position} in {location}, page {job_page}")
        encoded_position = urllib.parse.quote(position)
        self.driver.get(
            f"https://www.linkedin.com/jobs/search/{self.base_search_url}&keywords={encoded_position}{location}&start={job_page * 25}")

    def extract_job_information_from_tile(self, job_tile):
        logger.debug("Extracting job information from tile")
        job_title, company, job_location, apply_method, link = "", "", "", "", ""
        try:
            print(job_tile.get_attribute('outerHTML'))
            job_title = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').find_element(By.TAG_NAME, 'strong').text
            
            link = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').get_attribute('href').split('?')[0]
            company = job_tile.find_element(By.CLASS_NAME, 'job-card-container__primary-description').text
            logger.debug(f"Job information extracted: {job_title} at {company}")
        except NoSuchElementException:
            logger.warning("Some job information (title, link, or company) is missing.")
        try:
            job_location = job_tile.find_element(By.CLASS_NAME, 'job-card-container__metadata-item').text
        except NoSuchElementException:
            logger.warning("Job location is missing.")
        try:
            apply_method = job_tile.find_element(By.CLASS_NAME, 'job-card-container__apply-method').text
        except NoSuchElementException:
            apply_method = "Applied"
            logger.warning("Apply method not found, assuming 'Applied'.")

        return job_title, company, job_location, link, apply_method

    def is_blacklisted(self, job_title, company, link, job_location):
        logger.debug(f"Checking if job is blacklisted: {job_title} at {company} in {job_location}")
        job_title_words = job_title.lower().split(' ')
        title_blacklisted = any(word in job_title_words for word in map(str.lower, self.title_blacklist))
        company_blacklisted = company.strip().lower() in (word.strip().lower() for word in self.company_blacklist)
        location_blacklisted= job_location.strip().lower() in (word.strip().lower() for word in self.location_blacklist)
        link_seen = link in self.seen_jobs
        is_blacklisted = title_blacklisted or company_blacklisted or location_blacklisted or link_seen
        logger.debug(f"Job blacklisted status: {is_blacklisted}")

        return title_blacklisted or company_blacklisted or location_blacklisted or link_seen
