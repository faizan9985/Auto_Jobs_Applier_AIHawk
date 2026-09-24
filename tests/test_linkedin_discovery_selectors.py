from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException, WebDriverException
from src.aihawk_job_manager import AIHawkJobManager
from src.linkedin_selectors import (CARD_SELECTORS, DETAIL_TITLE_SELECTORS,
                                    DETAIL_COMPANY_SELECTORS, DETAIL_LOCATION_SELECTORS)


def element(text='', **attributes):
    result = Mock()
    result.text = text
    result.get_attribute.side_effect = lambda key: attributes.get(key)
    result.is_displayed.return_value = True
    result.find_elements.return_value = []
    return result


def tile(fields=None, **attributes):
    result = element(**attributes)
    result.find_elements.side_effect = lambda by, selector: (fields or {}).get(selector, [])
    return result


@pytest.mark.parametrize('selector', CARD_SELECTORS)
def test_layered_card_selectors(selector):
    card = tile({'a[href*="/jobs/view/"]': [element(href='https://www.linkedin.com/jobs/view/123')]})
    driver = Mock()
    driver.find_elements.side_effect = lambda by, query: [card, card] if query == selector else []
    assert AIHawkJobManager(driver)._find_job_cards() == [card]


def test_hidden_and_non_job_tiles_ignored():
    hidden = tile(**{'data-job-id': '123'})
    hidden.is_displayed.return_value = False
    driver = Mock()
    driver.find_elements.return_value = [hidden, tile()]
    assert AIHawkJobManager(driver)._find_job_cards() == []


def test_fallback_fields_extract_independently():
    card = tile({
        'a[href*="/jobs/view/"]': [element('Unity Developer', href='/jobs/view/123?tracking=test')],
        '.artdeco-entity-lockup__subtitle': [element('Example Studio')],
        '.artdeco-entity-lockup__caption': [element('United States (Remote)')],
        '.job-card-container__footer-item': [element('Easy Apply')],
    })
    assert AIHawkJobManager(Mock()).extract_job_information_from_tile(card) == (
        'Unity Developer', 'Example Studio', 'United States (Remote)',
        'https://www.linkedin.com/jobs/view/123', 'Easy Apply')


def test_guest_card_fields_and_unknown_method():
    card = tile({'.base-search-card__title': [element('Engineer')],
                 '.base-search-card__subtitle': [element('Example')],
                 '.job-search-card__location': [element('New York')],
                 'a.base-card__full-link': [element(href='/jobs/view/456')],
                 '.job-card-container__footer-item': [element('Promoted')]})
    assert AIHawkJobManager(Mock()).extract_job_information_from_tile(card) == (
        'Engineer', 'Example', 'New York', 'https://www.linkedin.com/jobs/view/456', '')


def test_missing_title_does_not_prevent_other_fields_and_id_link():
    card = tile({'a[href*="/company/"]': [element('Example')],
                 '[data-testid="job-location"]': [element('Remote')]}, **{'data-occludable-job-id': '123'})
    assert AIHawkJobManager(Mock()).extract_job_information_from_tile(card) == (
        '', 'Example', 'Remote', 'https://www.linkedin.com/jobs/view/123', '')


def test_aria_title_and_visible_application_label():
    card = tile({'a.job-card-list__title--link': [element(**{'href': '/jobs/view/123', 'aria-label': 'Engineer'})]})
    card.text = 'Engineer\nExample\nApplied'
    result = AIHawkJobManager(Mock()).extract_job_information_from_tile(card)
    assert result[0] == 'Engineer'
    assert result[-1] == 'Applied'


def test_no_cards_saves_html_and_screenshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    driver = Mock(current_url='https://www.linkedin.com/jobs/search/', page_source='<html>No cards</html>')
    wait = Mock()
    wait.until.side_effect = TimeoutException
    monkeypatch.setattr('src.aihawk_job_manager.WebDriverWait', Mock(return_value=wait))
    def screenshot(path):
        from pathlib import Path
        Path(path).write_bytes(b'PNG fixture')
        return True
    driver.save_screenshot.side_effect = screenshot
    assert AIHawkJobManager(driver).get_jobs_from_page() == []
    assert (tmp_path / 'data_folder/output/debug_jobs_page.html').read_text() == driver.page_source
    assert (tmp_path / 'data_folder/output/debug_jobs_page.png').read_bytes() == b'PNG fixture'


def test_screenshot_attempted_when_html_unavailable(tmp_path, monkeypatch):
    from unittest.mock import PropertyMock
    monkeypatch.chdir(tmp_path)
    driver = Mock()
    type(driver).page_source = PropertyMock(side_effect=WebDriverException('Unavailable'))
    AIHawkJobManager(driver)._save_job_page_debug()
    driver.save_screenshot.assert_called_once()


def test_scroll_lookup_failure_does_not_discard_cards(monkeypatch):
    driver = Mock(current_url='https://www.linkedin.com/jobs/search/')
    manager = AIHawkJobManager(driver)
    cards = [tile(**{'data-job-id': '123'})]
    manager._find_job_cards = Mock(return_value=cards)
    driver.find_elements.side_effect = WebDriverException('Scroll container unavailable')
    assert manager.get_jobs_from_page() == cards


def test_footer_scans_past_promoted_item():
    card = tile({'.job-card-container__footer-item': [element('Promoted'), element('Easy Apply')]})
    assert AIHawkJobManager(Mock()).extract_job_information_from_tile(card)[-1] == 'Easy Apply'


def test_empty_href_does_not_abort_card_discovery():
    broken = tile({'a[href*="/jobs/view/"]': [element()]})
    valid = tile(**{'data-job-id': '456'})
    driver = Mock()
    driver.find_elements.side_effect = lambda by, selector: [broken, valid] if selector == CARD_SELECTORS[0] else []
    assert AIHawkJobManager(driver)._find_job_cards() == [valid]


def test_data_testid_field_fallbacks():
    card = tile({'[data-testid="job-title"]': [element('Backend Engineer')],
                 '[data-testid="company-name"]': [element('Example')],
                 '[data-testid="job-location"]': [element('Remote')]}, **{'data-job-id': '789'})
    assert AIHawkJobManager(Mock()).extract_job_information_from_tile(card) == (
        'Backend Engineer', 'Example', 'Remote', 'https://www.linkedin.com/jobs/view/789', '')


@pytest.fixture
def discovery(tmp_path, monkeypatch):
    driver = Mock(current_url='https://www.linkedin.com/jobs/search/')
    detail_fields = {
        DETAIL_TITLE_SELECTORS[0]: [element('Detail Engineer')],
        DETAIL_COMPANY_SELECTORS[0]: [element('Detail Company')],
        DETAIL_LOCATION_SELECTORS[0]: [element('Detail City')],
    }
    driver.find_elements.side_effect = lambda by, selector: detail_fields.get(selector, [])
    manager = AIHawkJobManager(driver)
    manager.database_path = tmp_path / 'jobs.sqlite3'
    manager.company_blacklist = manager.title_blacklist = manager.location_blacklist = []
    manager.seen_jobs = []
    manager._export_result = Mock()
    reader = Mock()
    reader._get_job_description.return_value = 'Full job description'
    monkeypatch.setattr('src.aihawk_job_manager.AIHawkEasyApplier', Mock(return_value=reader))
    monkeypatch.setattr('src.aihawk_job_manager.time.sleep', lambda _: None)

    def until(predicate):
        for _ in range(3):
            if predicate(driver):
                return True
        raise TimeoutException()

    wait = Mock()
    wait.until.side_effect = until
    monkeypatch.setattr('src.aihawk_job_manager.WebDriverWait', Mock(return_value=wait))
    return manager, detail_fields, reader


@pytest.mark.parametrize('missing', [(), ('title', 'company', 'location'),
                                    ('title',), ('company', 'location')])
def test_discovery_recovers_only_missing_card_fields(discovery, missing):
    manager, _, reader = discovery
    card_values = {'title': 'Card Engineer', 'company': 'Card Company', 'location': 'Card City'}
    card_selectors = {'title': '[data-testid="job-title"]',
                      'company': '[data-testid="company-name"]',
                      'location': '[data-testid="job-location"]'}
    card = tile({card_selectors[field]: [element(value)]
                 for field, value in card_values.items() if field not in missing},
                **{'data-occludable-job-id': '123'})
    manager.get_jobs_from_page = Mock(return_value=[card])
    manager.read_jobs()
    rows = manager._store().list_jobs()
    assert len(rows) == 1
    row = rows[0]
    for field, card_value in card_values.items():
        assert row[field] == (card_value.replace('Card', 'Detail') if field in missing else card_value)
    assert row['linkedin_job_id'] == '123'
    assert row['job_url'] == 'https://www.linkedin.com/jobs/view/123'
    assert row['description'] == 'Full job description'
    assert row['eligibility']
    assert manager.driver.get.call_args_list[0].args == ('https://www.linkedin.com/jobs/view/123',)
    assert manager.driver.get.call_args_list[-1].args == ('https://www.linkedin.com/jobs/search/',)
    if not missing:
        manager.driver.find_elements.assert_not_called()
    reader.job_apply.assert_not_called()
    reader._find_easy_apply_button.assert_not_called()


def test_detail_metadata_waits_for_rendering(discovery):
    manager, fields, _ = discovery
    manager.get_jobs_from_page = Mock(return_value=[tile(**{'data-occludable-job-id': '123'})])
    calls = 0

    def delayed(by, selector):
        nonlocal calls
        calls += 1
        # First poll contains no metadata; the next poll sees the rendered header.
        if calls <= len(DETAIL_TITLE_SELECTORS) + len(DETAIL_COMPANY_SELECTORS) + len(DETAIL_LOCATION_SELECTORS):
            return []
        return fields.get(selector, [])

    manager.driver.find_elements.side_effect = delayed
    manager.read_jobs()
    assert manager._store().list_jobs()[0]['title'] == 'Detail Engineer'


def test_incomplete_identity_is_logged_and_not_persisted(discovery, monkeypatch):
    manager, fields, _ = discovery
    fields.pop(DETAIL_LOCATION_SELECTORS[0])
    manager.get_jobs_from_page = Mock(return_value=[tile(**{'data-occludable-job-id': '123'})])
    warning = Mock()
    monkeypatch.setattr('src.aihawk_job_manager.logger.warning', warning)
    manager.read_jobs()
    assert manager._store().list_jobs() == []
    manager._export_result.assert_not_called()
    warning.assert_any_call(
        'Skipping malformed job; missing fields: {}; URL: {}; LinkedIn job id: {}',
        'location', 'https://www.linkedin.com/jobs/view/123', '123')


def test_failed_detail_navigation_does_not_persist_blank_identity(discovery):
    manager, _, _ = discovery
    manager.get_jobs_from_page = Mock(return_value=[tile(**{'data-occludable-job-id': '123'})])
    manager.driver.get.side_effect = [WebDriverException('Unavailable'), None]
    manager.read_jobs()
    assert manager._store().list_jobs() == []


def test_incomplete_rediscovery_does_not_erase_existing_metadata(discovery):
    from src.job import Job
    manager, fields, _ = discovery
    job = Job('Existing Engineer', 'Existing Company', 'Existing City',
              'https://www.linkedin.com/jobs/view/123', '')
    store = manager._store()
    store.upsert(job)
    fields.clear()
    manager.get_jobs_from_page = Mock(return_value=[tile(**{'data-occludable-job-id': '123'})])
    manager.read_jobs()
    row = store.get(job.job_id)
    assert (row['title'], row['company'], row['location']) == (job.title, job.company, job.location)


def test_detail_metadata_legacy_fallbacks(discovery):
    manager, fields, _ = discovery
    fields.clear()
    fields.update({'.jobs-unified-top-card__job-title': [element('Legacy Engineer')],
                   '.jobs-unified-top-card__company-name a': [element('Legacy Company')],
                   '.jobs-unified-top-card__bullet': [element('Legacy City')]})
    manager.get_jobs_from_page = Mock(return_value=[tile(**{'data-occludable-job-id': '123'})])
    manager.read_jobs()
    row = manager._store().list_jobs()[0]
    assert (row['title'], row['company'], row['location']) == ('Legacy Engineer', 'Legacy Company', 'Legacy City')
