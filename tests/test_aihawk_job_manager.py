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
    """Test get_jobs_from_page when no jobs are found."""
    mocker.patch.object(job_manager.driver, 'find_element',
                        side_effect=NoSuchElementException)

    jobs = job_manager.get_jobs_from_page()
    assert jobs == []


def test_get_jobs_from_page_with_jobs(mocker, job_manager):
    """Test get_jobs_from_page when job elements are found."""
    # Mock the no_jobs_element to behave correctly
    mock_no_jobs_element = mocker.Mock()
    mock_no_jobs_element.text = "No matching jobs found"

    # Mocking the find_element to return the mock no_jobs_element
    mocker.patch.object(job_manager.driver, 'find_element',
                        return_value=mock_no_jobs_element)

    # Mock the page_source
    mocker.patch.object(job_manager.driver, 'page_source',
                        return_value="some page content")

    # Ensure jobs are returned as empty list due to "No matching jobs found"
    jobs = job_manager.get_jobs_from_page()
    assert jobs == []  # No jobs expected due to "No matching jobs found"


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
