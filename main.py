import os
import re
import sys
from pathlib import Path
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from src.utils import chrome_browser_options
from src.aihawk_authenticator import AIHawkAuthenticator
from src.aihawk_bot_facade import AIHawkBotFacade
from src.aihawk_job_manager import AIHawkJobManager
from src.job_application_profile import JobApplicationProfile
from src.job_store import JobStore, PENDING
from src.job_relevance import validate_threshold
from types import SimpleNamespace
from loguru import logger

# Suppress stderr only during specific operations
original_stderr = sys.stderr

class ConfigError(Exception):
    pass

class ConfigValidator:
    @staticmethod
    def validate_email(email: str) -> bool:
        return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
    
    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        try:
            with open(yaml_path, 'r') as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"File not found: {yaml_path}")

    @staticmethod
    def validate_config(config_yaml_path: Path) -> dict:
        parameters = ConfigValidator.validate_yaml_file(config_yaml_path)
        validate_threshold(parameters.get('minimum_relevance_score', 0))
        parameters.setdefault('manual_approval_before_submit', True)
        parameters.setdefault('enforce_eligibility_filter', True)
        if type(parameters['enforce_eligibility_filter']) is not bool:
            raise ConfigError("enforce_eligibility_filter must be a boolean")
        if type(parameters['manual_approval_before_submit']) is not bool:
            raise ConfigError("manual_approval_before_submit must be a boolean")
        required_keys = {
            'remote': bool,
            'experienceLevel': dict,
            'jobTypes': dict,
            'date': dict,
            'positions': list,
            'locations': list,
            'location_blacklist': list,
            'distance': int,
            'company_blacklist': list,
            'title_blacklist': list,
            'llm_model_type': str,
            'llm_model': str
        }

        for key, expected_type in required_keys.items():
            if key not in parameters:
                if key in ['company_blacklist', 'title_blacklist', 'location_blacklist']:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Missing or invalid key '{key}' in config file {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                if key in ['company_blacklist', 'title_blacklist', 'location_blacklist'] and parameters[key] is None:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Invalid type for key '{key}' in config file {config_yaml_path}. Expected {expected_type}.")

        # Validate experience levels, ensure they are boolean
        experience_levels = ['internship', 'entry', 'associate', 'mid-senior level', 'director', 'executive']
        for level in experience_levels:
            if not isinstance(parameters['experienceLevel'].get(level), bool):
                raise ConfigError(f"Experience level '{level}' must be a boolean in config file {config_yaml_path}")

        # Validate job types, ensure they are boolean
        job_types = ['full-time', 'contract', 'part-time', 'temporary', 'internship', 'other', 'volunteer']
        for job_type in job_types:
            if not isinstance(parameters['jobTypes'].get(job_type), bool):
                raise ConfigError(f"Job type '{job_type}' must be a boolean in config file {config_yaml_path}")

        # Validate date filters
        date_filters = ['all time', 'month', 'week', '24 hours']
        for date_filter in date_filters:
            if not isinstance(parameters['date'].get(date_filter), bool):
                raise ConfigError(f"Date filter '{date_filter}' must be a boolean in config file {config_yaml_path}")

        # Validate positions and locations as lists of strings
        if not all(isinstance(pos, str) for pos in parameters['positions']):
            raise ConfigError(f"'positions' must be a list of strings in config file {config_yaml_path}")
        if not all(isinstance(loc, str) for loc in parameters['locations']):
            raise ConfigError(f"'locations' must be a list of strings in config file {config_yaml_path}")

        # Validate distance
        approved_distances = {0, 5, 10, 25, 50, 100}
        if parameters['distance'] not in approved_distances:
            raise ConfigError(f"Invalid distance value in config file {config_yaml_path}. Must be one of: {approved_distances}")

        # Ensure blacklists are lists
        for blacklist in ['company_blacklist', 'title_blacklist','location_blacklist']:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(f"'{blacklist}' must be a list in config file {config_yaml_path}")
            if parameters[blacklist] is None:
                parameters[blacklist] = []

        return parameters

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> str:
        secrets = ConfigValidator.validate_yaml_file(secrets_yaml_path)
        mandatory_secrets = ['llm_api_key']

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(f"Missing secret '{secret}' in file {secrets_yaml_path}")

        if not secrets['llm_api_key']:
            raise ConfigError(f"llm_api_key cannot be empty in secrets file {secrets_yaml_path}.")
        return secrets['llm_api_key']

class FileManager:
    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        required_files = ['secrets.yaml', 'config.yaml', 'plain_text_resume.yaml']
        missing_files = [file for file in required_files if not (app_data_folder / file).exists()]
        
        if missing_files:
            raise FileNotFoundError(f"Missing files in the data folder: {', '.join(missing_files)}")

        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        return (app_data_folder / 'secrets.yaml', app_data_folder / 'config.yaml', app_data_folder / 'plain_text_resume.yaml', output_folder)

    @staticmethod
    def file_paths_to_dict(resume_file: Path | None, plain_text_resume_file: Path) -> dict:
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(f"Plain text resume file not found: {plain_text_resume_file}")

        result = {'plainTextResume': plain_text_resume_file}

        if resume_file:
            if not resume_file.exists():
                raise FileNotFoundError(f"Resume file not found: {resume_file}")
            result['resume'] = resume_file

        return result

def init_browser() -> webdriver.Chrome:
    try:
        options = chrome_browser_options()
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")

def create_and_run_bot(parameters, llm_api_key):
    browser = None
    try:
        with open(parameters['uploads']['plainTextResume'], "r", encoding='utf-8') as file:
            plain_text_resume = file.read()
        job_application_profile_object = JobApplicationProfile(plain_text_resume)
        if parameters['collectMode']:
            browser = init_browser()
            manager = AIHawkJobManager(browser)
            manager.set_parameters(parameters)
            manager.set_gpt_answerer(SimpleNamespace(job_application_profile=job_application_profile_object))
            AIHawkAuthenticator(browser).start()
            manager.start_collecting_data()
            return

        from lib_resume_builder_AIHawk import Resume, FacadeManager, ResumeGenerator, StyleManager
        from src.llm.llm_manager import GPTAnswerer
        style_manager = StyleManager()
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        resume_generator_manager = FacadeManager(llm_api_key, style_manager, resume_generator, resume_object, Path("data_folder/output"))
        
        # Run the resume generator manager's functions
        resume_generator_manager.choose_style()
        
        
        browser = init_browser()
        login_component = AIHawkAuthenticator(browser)
        apply_component = AIHawkJobManager(browser)
        gpt_answerer_component = GPTAnswerer(parameters, llm_api_key)
        bot = AIHawkBotFacade(login_component, apply_component)
        bot.set_job_application_profile_and_resume(job_application_profile_object, resume_object)
        bot.set_gpt_answerer_and_resume_generator(gpt_answerer_component, resume_generator_manager)
        bot.set_parameters(parameters)
        bot.start_login()
        if (parameters['collectMode'] == True):
            print('Collecting')
            bot.start_collect_data()
        else:
            print('Applying')
            bot.start_apply()
    except WebDriverException as e:
        logger.error(f"WebDriver error occurred: {e}")
    except Exception as e:
        raise RuntimeError(f"Error running the bot: {str(e)}")
    finally:
        if browser is not None:
            browser.quit()


@click.command()
@click.option('--resume', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), help="Path to the resume PDF file")
@click.option('--collect', is_flag=True, help="Compatibility alias for --mode discover")
@click.option('--mode', type=click.Choice(['discover', 'apply', 'pending', 'import-json']), default='apply', show_default=True)
@click.option('--database', type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option('--retry-failed', is_flag=True, help="Intentionally include failed jobs")
@click.option('--include-deferred', is_flag=True, help="Include jobs previously deferred or aborted")
@click.option('--retry-interrupted', is_flag=True, help="Retry applying/approved jobs after checking they were not submitted")
@click.option('--job-id', 'job_ids', multiple=True, help="Limit application or listing to internal job IDs")
@click.option('--top', type=click.IntRange(min=1), default=None, help="Show at most N pending jobs")
@click.option('--minimum-relevance-score', type=click.FloatRange(0, 100), default=None,
              help="Advisory threshold; jobs below it remain pending")
def main(collect=False, resume=None, mode='apply', database=None, retry_failed=False,
         include_deferred=False, retry_interrupted=False, job_ids=(), top=None, minimum_relevance_score=None):
    try:
        data_folder = Path("data_folder")
        output_folder = data_folder / 'output'
        database = database or output_folder / 'jobs.sqlite3'
        if collect:
            if mode not in {'apply', 'discover'}:
                raise click.UsageError("--collect cannot be combined with this mode")
            mode = 'discover'
        if mode in {'pending', 'import-json'}:
            store = JobStore(database)
            if mode == 'import-json':
                click.echo(f"Imported {store.import_json(output_folder)} records into {database}")
            else:
                states = (*PENDING, 'deferred', 'failed', 'applying', 'approved')
                config_path = data_folder / 'config.yaml'
                config = (yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}) if config_path.exists() else {}
                threshold = validate_threshold(minimum_relevance_score if minimum_relevance_score is not None
                                               else config.get('minimum_relevance_score', 0))
                profile_path = data_folder / 'plain_text_resume.yaml'
                if profile_path.exists():
                    store.rescore(yaml.safe_load(profile_path.read_text(encoding='utf-8')) or {}, states, job_ids)
                for row in store.list_jobs(states, job_ids, top=top):
                    score = row['total_score']
                    label = 'unscored' if score is None else f'{score:.2f}/100'
                    if score is not None and score < threshold:
                        label += ' (below advisory threshold)'
                    click.echo(f"{row['id']} | {row['state']} | {row['company']} | {row['title']} | {row['job_url']} | relevance: {label}")
            return
        if mode == 'apply':
            states = list(PENDING)
            if retry_failed:
                states.append('failed')
            if include_deferred:
                states.append('deferred')
            if retry_interrupted:
                states.extend(['applying', 'approved'])
            if not JobStore(database).list_jobs(states, job_ids):
                click.echo("No selected pending jobs. Run --mode discover or explicitly select a retry option.")
                return
        config_file = data_folder / 'config.yaml'
        plain_text_resume_file = data_folder / 'plain_text_resume.yaml'
        output_folder.mkdir(parents=True, exist_ok=True)
        
        parameters = ConfigValidator.validate_config(config_file)
        llm_api_key = (ConfigValidator.validate_secrets(data_folder / 'secrets.yaml')
                       if mode == 'apply' else None)
        
        parameters['uploads'] = FileManager.file_paths_to_dict(resume, plain_text_resume_file)
        parameters['outputFileDirectory'] = output_folder
        parameters['collectMode'] = mode == 'discover'
        parameters.update(database_path=database, retry_failed=retry_failed,
                          include_deferred=include_deferred, retry_interrupted=retry_interrupted,
                          job_ids=job_ids)
        
        create_and_run_bot(parameters, llm_api_key)
    except ConfigError as ce:
        logger.error(f"Configuration error: {str(ce)}")
        logger.error(f"Refer to the configuration guide for troubleshooting: https://github.com/feder-cr/Auto_Jobs_Applier_AIHawk?tab=readme-ov-file#configuration {str(ce)}")

    except FileNotFoundError as fnf:
        logger.error(f"File not found: {str(fnf)}")
        logger.error("Ensure all required files are present in the data folder.")
    except RuntimeError as re:
        logger.error(f"Runtime error: {str(re)}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
