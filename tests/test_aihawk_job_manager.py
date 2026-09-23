from src.job import Job
from unittest import mock
from pathlib import Path
import os
import pytest
from src.aihawk_job_manager import AIHawkJobManager
from selenium.common.exceptions import NoSuchElementException
from loguru import logger


@pytest.fixture
def job_manager(mocker, tmp_path):
    """Fixture to create a AIHawkJobManager instance with mocked driver."""
    mock_driver = mocker.Mock()
    manager = AIHawkJobManager(mock_driver)
    manager.database_path = tmp_path / "jobs.sqlite3"
    manager.output_file_directory = tmp_path
    manager.company_blacklist = manager.title_blacklist = manager.location_blacklist = []
    manager.seen_jobs = []
    manager.apply_once_at_company = False
    return manager


def test_initialization(job_manager):
    """Test AIHawkJobManager initialization."""
    assert job_manager.driver is not None
    assert job_manager.set_old_answers == set()
    assert job_manager.easy_applier_component is None


def test_set_parameters(mocker, job_manager):
    """Test setting parameters for the AIHawkJobManager."""
    # Mocking os.path.exists to return True for the resume path
    mocker.patch('pathlib.Path.exists', return_value=True)

    params = {
        'company_blacklist': ['Company A', 'Company B'],
        'title_blacklist': ['Intern', 'Junior'],
        'positions': ['Software Engineer', 'Data Scientist'],
        'locations': ['New York', 'San Francisco'],
        'apply_once_at_company': True,
        'uploads': {'resume': '/path/to/resume'},  # Resume path provided here
        'outputFileDirectory': '/path/to/output',
        'job_applicants_threshold': {
            'min_applicants': 5,
            'max_applicants': 50
        },
        'remote': False,
        'distance': 50,
        'date': {'all time': True}
    }

    job_manager.set_parameters(params)

    # Normalize paths to handle platform differences (e.g., Windows vs Unix-like systems)
    assert str(job_manager.resume_path) == os.path.normpath('/path/to/resume')
    assert str(job_manager.output_file_directory) == os.path.normpath(
        '/path/to/output')


def next_job_page(self, position, location, job_page):
    logger.debug(f"Navigating to next job page: {position} in {location}, page {job_page}")
    self.driver.get(
        f"https://www.linkedin.com/jobs/search/{self.base_search_url}&keywords={position}&location={location}&start={job_page * 25}")


def test_get_jobs_from_page_no_jobs(mocker, job_manager):
    from selenium.common.exceptions import TimeoutException
    mocker.patch('src.aihawk_job_manager.WebDriverWait').return_value.until.side_effect = TimeoutException
    capture = mocker.patch.object(job_manager, '_save_job_page_debug')
    assert job_manager.get_jobs_from_page() == []
    capture.assert_called_once()


def test_get_jobs_from_page_with_jobs(mocker, job_manager):
    cards = [mocker.Mock()]
    job_manager.driver.page_source = 'No matching jobs found (hidden template)'
    job_manager.driver.find_elements.return_value = []
    mocker.patch.object(job_manager, '_find_job_cards', return_value=cards)
    assert job_manager.get_jobs_from_page() == cards


def test_apply_jobs_with_no_jobs(job_manager):
    job_manager.apply_jobs()
    job_manager.driver.find_element.assert_not_called()
    job_manager.driver.find_elements.assert_not_called()


def test_apply_jobs_with_jobs(job_manager):
    job = Job("Title", "Company", "Location", "https://www.linkedin.com/jobs/view/123", "Easy Apply")
    job_manager._store().upsert(job)
    job_manager.easy_applier_component = mock.Mock()
    job_manager.easy_applier_component.job_apply.return_value = "submitted"
    job_manager.apply_jobs()
    job_manager.driver.find_elements.assert_not_called()
    job_manager.easy_applier_component.job_apply.assert_called_once()
    assert job_manager._store().get(job.job_id)["state"] == "submitted"
