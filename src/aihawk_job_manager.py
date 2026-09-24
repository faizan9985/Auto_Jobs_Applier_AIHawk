import json
import os
import random
import time
from itertools import product
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from src.linkedin_selectors import (CARD_SELECTORS, SCROLL_CONTAINERS, TITLE_SELECTORS,
                                    COMPANY_SELECTORS, LOCATION_SELECTORS, LINK_SELECTORS, METHOD_SELECTORS,
                                    DETAIL_TITLE_SELECTORS, DETAIL_COMPANY_SELECTORS, DETAIL_LOCATION_SELECTORS)

import src.utils as utils
from src.job import Job
from src.job_store import JobStore, PENDING, identity
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
        self.enforce_eligibility_filter = True
        self.job_store = None
        self.database_path = Path("data_folder/output/jobs.sqlite3")
        self.retry_failed = False
        self.include_deferred = False
        self.retry_interrupted = False
        self.selected_job_ids = ()
        self.relevance_resume = None
        self.resume_tailor = None
        self.regenerate_resume = False
        logger.debug("AIHawkJobManager initialized successfully")

    def set_parameters(self, parameters):
        logger.debug("Setting parameters for AIHawkJobManager")
        self.manual_approval_before_submit = parameters.get('manual_approval_before_submit', True)
        self.enforce_eligibility_filter = parameters.get('enforce_eligibility_filter', True)
        tailor_resume = parameters.get('tailor_resume_per_job', True)
        if type(tailor_resume) is not bool:
            raise ValueError('tailor_resume_per_job must be a boolean')
        if type(self.enforce_eligibility_filter) is not bool:
            raise ValueError("enforce_eligibility_filter must be a boolean")
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
        self.resume_tailor = None
        self.regenerate_resume = parameters.get('regenerate_resume', False)
        if tailor_resume and profile_path:
            from src.resume_tailoring import ResumeTailor
            self.resume_tailor = ResumeTailor(self._store(), profile_path,
                                             self.output_file_directory / 'tailored_resumes')
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

    def _find_job_cards(self):
        for selector in CARD_SELECTORS:
            try:
                candidates = self.driver.find_elements(By.CSS_SELECTOR, selector)
                cards, seen = [], set()
                for card in candidates:
                    if not card.is_displayed():
                        continue
                    job_id = card.get_attribute('data-occludable-job-id') or card.get_attribute('data-job-id')
                    links = card.find_elements(By.CSS_SELECTOR, 'a[href*="/jobs/view/"]')
                    if not job_id and not links:
                        continue
                    href = links[0].get_attribute('href') if links else None
                    if not job_id and not href:
                        continue
                    key = job_id or urllib.parse.urljoin('https://www.linkedin.com', href).split('?')[0].split('#')[0]
                    if key not in seen:
                        seen.add(key)
                        cards.append(card)
                if cards:
                    logger.info("Job-card selector matched: {} ({} cards)", selector, len(cards))
                    return cards
            except WebDriverException as exc:
                logger.debug("Job-card selector unavailable: {} ({})", selector, type(exc).__name__)
        return []

    def _save_job_page_debug(self):
        directory = Path('data_folder/output')
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Cannot create job-page debug directory: {}", exc)
            return
        # Capture independently so a failure in one does not prevent the other.
        try:
            path = directory / 'debug_jobs_page.html'
            path.write_text(self.driver.page_source, encoding='utf-8')
            logger.info("Saved job-page HTML: {}", path)
        except (OSError, WebDriverException) as exc:
            logger.warning("Could not save job-page HTML: {}", exc)
        try:
            path = directory / 'debug_jobs_page.png'
            if self.driver.save_screenshot(str(path)):
                logger.info("Saved job-page screenshot: {}", path)
            else:
                logger.warning("Browser did not save job-page screenshot: {}", path)
        except (OSError, WebDriverException) as exc:
            logger.warning("Could not save job-page screenshot: {}", exc)

    def get_jobs_from_page(self):
        logger.info("Discovering job cards at {}", self.driver.current_url)
        try:
            cards = WebDriverWait(self.driver, 10).until(lambda _: self._find_job_cards())
            # Scrolling is optional; missing/changed scroll containers must not
            # discard cards that were already found.
            for selector in SCROLL_CONTAINERS:
                try:
                    containers = self.driver.find_elements(By.CSS_SELECTOR, selector)
                except WebDriverException:
                    continue
                if containers:
                    logger.debug("Job-list scroll selector matched: {}", selector)
                    try:
                        utils.scroll_slow(self.driver, containers[0])
                        utils.scroll_slow(self.driver, containers[0], step=300, reverse=True)
                    except (WebDriverException, ValueError) as exc:
                        logger.debug("Optional job-list scrolling failed: {}", exc)
                    break
            cards = self._find_job_cards() or cards
            logger.info("Found {} job cards at {}", len(cards), self.driver.current_url)
            return cards
        except (TimeoutException, WebDriverException) as exc:
            logger.warning("Found 0 job cards at {} ({})", self.driver.current_url, type(exc).__name__)
            self._save_job_page_debug()
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
            try:
                if job.link:
                    self.driver.get(job.link)
                    time.sleep(random.uniform(1.5, 3.5))
                    if self._missing_identity_fields(job):
                        self._fill_detail_metadata(job)
                    description = reader._get_job_description()
                    if description:
                        job.description = description
            except Exception as exc:
                logger.warning(f"Description unavailable for {job.link}: {exc}")
            missing = self._missing_identity_fields(job)
            if missing:
                logger.warning("Skipping malformed job; missing fields: {}; URL: {}; LinkedIn job id: {}",
                               ', '.join(missing), job.link, identity(job)[0] or 'unknown')
                continue
            store = self._store()
            row = store.upsert(job)
            job = store.to_job(row)
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

    @staticmethod
    def _missing_identity_fields(job):
        return [field for field in ('title', 'company', 'location')
                if not getattr(job, field).strip()]

    def _fill_detail_metadata(self, job):
        """Fill only absent card values, waiting for the detail header to render."""
        selectors_by_field = {
            'title': DETAIL_TITLE_SELECTORS,
            'company': DETAIL_COMPANY_SELECTORS,
            'location': DETAIL_LOCATION_SELECTORS,
        }

        def extract(_):
            for field in self._missing_identity_fields(job):
                value = self._tile_value(self.driver, selectors_by_field[field], f'detail {field}')
                if value:
                    setattr(job, field, value)
            return not self._missing_identity_fields(job)

        try:
            WebDriverWait(self.driver, 10, poll_frequency=0.5).until(extract)
        except (TimeoutException, WebDriverException):
            # Keep any recovered values; read_jobs validates before persistence.
            pass

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
            # Persisted discovery evaluation is authoritative for selection.
            # Legacy/imported jobs without a result are evaluated once locally.
            if job.eligibility is None:
                job.evaluate_eligibility(self._candidate())
                store.evaluate(job)
                row = store.get(job.job_id)
            status = job.eligibility.get('status')
            if self.enforce_eligibility_filter and status == 'ineligible':
                try:
                    store.skip_ineligible(job.job_id, expected_state=row['state'])
                except ValueError:
                    logger.info(f"Job {job.job_id} changed before eligibility gating; leaving it alone")
                    continue
                job.application_status = 'skipped'
                logger.info(f"Skipping ineligible job {job.job_id}: {job.eligibility.get('reasons', [])}")
                self._export_result(job, 'skipped')
                continue
            if status == 'needs_review':
                utils.printyellow(f"ELIGIBILITY REVIEW REQUIRED: {job.title} at {job.company}\n"
                                  + '\n'.join(str(reason) for reason in job.eligibility.get('reasons', [])))
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
                if self.resume_tailor is not None:
                    tailored = self.resume_tailor.prepare(job, regenerate=self.regenerate_resume)
                    job.tailoring_id = tailored['id']
                    job.tailored_resume_path = tailored['resume_path']
                    job.tailored_resume_hash = tailored['pdf_hash']
                    job.pdf_path = ''  # Set only after the exact file has been uploaded.
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
                        failure_reason=row['failure_reason'], skip_reason=row['skip_reason'])
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

    def _tile_value(self, tile, selectors, field, attribute=None, accepted=None):
        for selector in selectors:
            try:
                for element in tile.find_elements(By.CSS_SELECTOR, selector):
                    value = element.get_attribute(attribute) if attribute else element.text
                    if not value and not attribute:
                        value = element.get_attribute('aria-label')
                    if value and value.strip() and (accepted is None or value.strip().lower() in accepted):
                        logger.debug("Job {} fallback matched: {}", field, selector)
                        return value.strip()
            except WebDriverException:
                continue
        logger.debug("No job {} selector matched", field)
        return ''

    def extract_job_information_from_tile(self, job_tile):
        job_title = self._tile_value(job_tile, TITLE_SELECTORS, 'title')
        company = self._tile_value(job_tile, COMPANY_SELECTORS, 'company')
        location = self._tile_value(job_tile, LOCATION_SELECTORS, 'location')
        link = self._tile_value(job_tile, LINK_SELECTORS, 'link', 'href')
        if link:
            link = urllib.parse.urljoin('https://www.linkedin.com', link).split('?')[0].split('#')[0]
        else:
            for attribute in ('data-occludable-job-id', 'data-job-id'):
                job_id = job_tile.get_attribute(attribute)
                if job_id and job_id.isdigit():
                    link = f'https://www.linkedin.com/jobs/view/{job_id}'
                    logger.debug("Job link fallback matched attribute: {}", attribute)
                    break
        if not job_title:
            job_title = self._tile_value(job_tile, LINK_SELECTORS, 'title attribute', 'aria-label')
        method = ''
        for selector in METHOD_SELECTORS:
            value = self._tile_value(job_tile, (selector,), 'application method',
                                     accepted={'easy apply', 'applied', 'apply', 'continue'})
            # Footer items also include timestamps and promoted labels.
            if value.lower() in ('easy apply', 'applied', 'apply', 'continue'):
                method = value.title() if value.lower() != 'easy apply' else 'Easy Apply'
                break
        if not method:
            lines = [line.strip().lower() for line in job_tile.text.splitlines()]
            for label in ('applied', 'easy apply', 'continue', 'apply'):
                if label in lines:
                    method = 'Easy Apply' if label == 'easy apply' else label.title()
                    logger.debug("Job application method fallback matched visible label: {}", label)
                    break
        # Missing method is unknown, never evidence of an earlier application.
        return job_title, company, location, link, method

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
