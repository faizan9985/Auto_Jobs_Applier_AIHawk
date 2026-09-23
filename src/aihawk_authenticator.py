from urllib.parse import urlsplit

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from loguru import logger

from src.linkedin_selectors import AUTHENTICATED, LOGIN_FORMS


class AIHawkAuthenticator:
    def __init__(self, driver=None):
        self.driver = driver

    def start(self):
        logger.info("Checking saved LinkedIn session at {}", self.driver.current_url)
        if self.is_logged_in():
            return
        # Chrome often starts on a blank tab. Probe the saved session without
        # sending an already-authenticated user to the login page.
        if not self._linkedin_url():
            self.driver.get('https://www.linkedin.com/feed/')
        try:
            WebDriverWait(self.driver, 10).until(lambda _: self.is_logged_in() or self._logged_out())
        except TimeoutException:
            logger.info("Session probe inconclusive at {}", self.driver.current_url)
        if not self.is_logged_in():
            self.handle_login()

    def _linkedin_url(self):
        url = self.driver.current_url
        if not isinstance(url, str):
            return None
        parts = urlsplit(url)
        host = (parts.hostname or '').lower()
        return parts if parts.scheme in ('http', 'https') and (host == 'linkedin.com' or host.endswith('.linkedin.com')) else None

    def _visible_match(self, selectors):
        for selector in selectors:
            try:
                if any(element.is_displayed() for element in self.driver.find_elements(By.CSS_SELECTOR, selector)):
                    return selector
            except WebDriverException:
                continue
        return None

    def _logged_out(self):
        parts = self._linkedin_url()
        if not parts:
            return False
        path = parts.path.lower()
        if any(path == p or path.startswith(p + '/') for p in
               ('/login', '/uas/login', '/authwall', '/checkpoint', '/signup', '/start/join')):
            logger.debug("Unauthenticated/challenge path matched: {}", path)
            return True
        selector = self._visible_match(LOGIN_FORMS)
        if selector:
            logger.debug("Logged-out selector matched: {}", selector)
            return True
        return False

    def is_logged_in(self):
        logger.debug("Checking LinkedIn authentication at {}", self.driver.current_url)
        parts = self._linkedin_url()
        if not parts or self._logged_out():
            return False
        selector = self._visible_match(AUTHENTICATED)
        if selector:
            logger.info("Authenticated LinkedIn selector matched: {}", selector)
            return True
        path = parts.path.lower()
        if any(path == p or path.startswith(p + '/') for p in ('/feed', '/messaging', '/mynetwork', '/notifications')):
            logger.info("Authenticated LinkedIn path matched: {}", path)
            return True
        # Jobs and public profiles can also be served to guests. Require a
        # session cookie or signed-in navigation, not just a public URL.
        if any(path == p or path.startswith(p + '/') for p in ('/jobs', '/in', '/me')):
            try:
                cookie = self.driver.get_cookie('li_at')
                if cookie and cookie.get('value'):
                    logger.info("Authenticated path plus session cookie matched: {}", path)
                    return True
            except WebDriverException:
                pass
        return False

    def handle_login(self):
        if self.is_logged_in():
            return
        parts = self._linkedin_url()
        if parts and parts.path.startswith('/checkpoint'):
            self.handle_security_check()
            return
        self.driver.get('https://www.linkedin.com/login')
        if self.is_logged_in():
            return
        self.enter_credentials()

    def enter_credentials(self):
        if self.is_logged_in():
            return
        logger.info("Complete LinkedIn login or any security challenge in the browser. URL: {}", self.driver.current_url)
        try:
            # Login can use password, passkey, SSO, or a challenge. Do not require
            # a particular form field while the user completes authentication.
            WebDriverWait(self.driver, 300, poll_frequency=2).until(lambda _: self.is_logged_in())
        except TimeoutException as exc:
            raise RuntimeError('LinkedIn authentication was not completed; discovery has not started') from exc

    def handle_security_check(self):
        if self.is_logged_in():
            return
        self.enter_credentials()
