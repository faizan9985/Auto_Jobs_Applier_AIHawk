from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException
from src.aihawk_authenticator import AIHawkAuthenticator


@pytest.fixture
def auth():
    driver = Mock(current_url='https://www.linkedin.com/login')
    driver.find_elements.return_value = []
    driver.get_cookie.return_value = None
    return AIHawkAuthenticator(driver)


@pytest.mark.parametrize('path', ['/feed', '/feed/', '/messaging/thread/1', '/mynetwork/', '/notifications/'])
def test_authenticated_path_does_not_navigate(auth, path):
    auth.driver.current_url = 'https://www.linkedin.com' + path
    assert auth.is_logged_in()
    auth.start()
    auth.driver.get.assert_not_called()


@pytest.mark.parametrize('path', ['/jobs/', '/jobs/search/?keywords=python', '/in/candidate/', '/me/'])
def test_public_capable_paths_require_session_evidence(auth, path):
    auth.driver.current_url = 'https://www.linkedin.com' + path
    assert not auth.is_logged_in()
    auth.driver.get_cookie.return_value = {'name': 'li_at', 'value': 'test-session'}
    assert auth.is_logged_in()
    auth.handle_login()
    auth.driver.get.assert_not_called()


@pytest.mark.parametrize('url', ['https://www.linkedin.com/login?next=/feed',
    'https://www.linkedin.com/authwall', 'https://www.linkedin.com/checkpoint/challengesV2/',
    'https://www.linkedin.com/uas/login', 'https://linkedin.com.evil.example/feed',
    'https://example.com/feed', 'about:blank'])
def test_logged_out_and_non_linkedin_urls(auth, url):
    auth.driver.current_url = url
    auth.driver.get_cookie.return_value = {'value': 'stale-session'}
    assert not auth.is_logged_in()


def test_login_form_overrides_authenticated_path(auth):
    auth.driver.current_url = 'https://www.linkedin.com/feed/'
    field = Mock()
    field.is_displayed.return_value = True
    auth.driver.find_elements.side_effect = lambda by, selector: [field] if selector == 'input#username' else []
    assert not auth.is_logged_in()


def test_navigation_fallback_and_hidden_login_form(auth):
    auth.driver.current_url = 'https://www.linkedin.com/in/candidate/'
    hidden = Mock()
    hidden.is_displayed.return_value = False
    nav = Mock()
    nav.is_displayed.return_value = True
    auth.driver.find_elements.side_effect = lambda by, selector: ([hidden] if selector == 'input#username'
        else [nav] if selector == 'nav a[href*="/messaging/"]' else [])
    assert auth.is_logged_in()


def test_blank_tab_probes_feed_not_login(auth):
    auth.driver.current_url = 'about:blank'
    def navigate(url):
        auth.driver.current_url = url
    auth.driver.get.side_effect = navigate
    auth.start()
    auth.driver.get.assert_called_once_with('https://www.linkedin.com/feed/')


def test_login_redirect_skips_form(auth):
    def navigate(url):
        auth.driver.current_url = 'https://www.linkedin.com/jobs/'
        auth.driver.get_cookie.return_value = {'value': 'session'}
    auth.driver.get.side_effect = navigate
    auth.enter_credentials = Mock()
    auth.handle_login()
    auth.enter_credentials.assert_not_called()


def test_manual_login_does_not_require_password_field(auth, monkeypatch):
    def complete(predicate):
        auth.driver.current_url = 'https://www.linkedin.com/feed/'
        return predicate(auth.driver)
    wait = Mock()
    wait.until.side_effect = complete
    monkeypatch.setattr('src.aihawk_authenticator.WebDriverWait', Mock(return_value=wait))
    auth.enter_credentials()
    auth.driver.find_element.assert_not_called()


def test_incomplete_login_stops_discovery(auth, monkeypatch):
    wait = Mock()
    wait.until.side_effect = TimeoutException
    monkeypatch.setattr('src.aihawk_authenticator.WebDriverWait', Mock(return_value=wait))
    with pytest.raises(RuntimeError, match='discovery has not started'):
        auth.enter_credentials()


def test_checkpoint_is_not_replaced_with_login(auth):
    auth.driver.current_url = 'https://www.linkedin.com/checkpoint/challengesV2/'
    auth.handle_security_check = Mock()
    auth.handle_login()
    auth.handle_security_check.assert_called_once()
    auth.driver.get.assert_not_called()


def test_empty_session_cookie_is_not_authenticated(auth):
    auth.driver.current_url = 'https://www.linkedin.com/jobs/search/'
    auth.driver.get_cookie.return_value = {'name': 'li_at', 'value': ''}
    assert not auth.is_logged_in()
