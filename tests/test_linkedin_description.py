from pathlib import Path
from unittest.mock import Mock, PropertyMock

import pytest
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from src.linkedin_description import read_job_description, save_description_debug
from src.linkedin_selectors import (DESCRIPTION_SELECTORS, DESCRIPTION_EXPAND_XPATH,
                                    DESCRIPTION_EXPAND_SCOPE_XPATH, DESCRIPTION_HEADING_XPATH)


def body(text):
    node = Mock(text=text)
    node.is_displayed.return_value = True
    node.find_elements.return_value = []
    return node


@pytest.fixture
def driver(monkeypatch):
    driver = Mock(current_url='https://www.linkedin.com/jobs/view/123/', page_source='<html>job</html>')
    driver.find_elements.return_value = []
    def until(predicate):
        for _ in range(3):
            result = predicate(driver)
            if result:
                return result
        raise TimeoutException()
    wait = Mock()
    wait.until.side_effect = until
    monkeypatch.setattr('src.linkedin_description.WebDriverWait', Mock(return_value=wait))
    return driver


@pytest.mark.parametrize('selector', DESCRIPTION_SELECTORS)
def test_primary_and_alternate_descriptions(driver, selector):
    node = body('Responsibilities\nBuild APIs.\nRequirements\nPython')
    driver.find_elements.side_effect = lambda by, query: [node] if query == selector else []
    assert read_job_description(driver) == node.text


def test_heading_scoped_nested_body(driver):
    node = body('Nested visible description')
    driver.find_elements.side_effect = lambda by, query: [node] if query == DESCRIPTION_HEADING_XPATH else []
    assert read_job_description(driver) == node.text


def test_show_more_clicked_and_body_reacquired(driver):
    collapsed = body('Short description')
    expanded = body('Full verified description after expansion')
    button = Mock(id='expand-description')
    button.is_displayed.return_value = button.is_enabled.return_value = True
    section = body('Sidebar text must not be returned')
    section.find_elements.side_effect = lambda by, query: [button] if query == DESCRIPTION_EXPAND_XPATH else []
    collapsed.find_elements.side_effect = lambda by, query: [section] if query == DESCRIPTION_EXPAND_SCOPE_XPATH else []
    driver.find_elements.side_effect = lambda by, query: ([expanded if button.click.called else collapsed] if query == '#job-details' else [])
    assert read_job_description(driver) == expanded.text
    button.click.assert_called_once()


def test_hidden_and_empty_bodies_skipped(driver):
    hidden = body('Hidden unrelated content')
    hidden.is_displayed.return_value = False
    visible = body('Actual description')
    driver.find_elements.side_effect = lambda by, query: [hidden, body(''), visible] if query == '#job-details' else []
    assert read_job_description(driver) == visible.text


def test_no_description_captures_both_files(driver, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def screenshot(path):
        Path(path).write_bytes(b'PNG fixture')
        return True
    driver.save_screenshot.side_effect = screenshot
    with pytest.raises(RuntimeError, match='jobs/view/123'):
        read_job_description(driver)
    assert (tmp_path / 'data_folder/output/debug_job_description.html').read_text() == driver.page_source
    assert (tmp_path / 'data_folder/output/debug_job_description.png').read_bytes() == b'PNG fixture'


def test_screenshot_survives_html_failure(driver, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    type(driver).page_source = PropertyMock(side_effect=WebDriverException('unavailable'))
    save_description_debug(driver)
    driver.save_screenshot.assert_called_once()
