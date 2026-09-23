"""Read visible LinkedIn description text without entering an application flow."""
from pathlib import Path

from loguru import logger
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from src.linkedin_selectors import (DESCRIPTION_SELECTORS, DESCRIPTION_HEADING_XPATH,
                                    DESCRIPTION_EXPAND_XPATH, DESCRIPTION_EXPAND_SCOPE_XPATH)


def save_description_debug(driver):
    directory = Path('data_folder/output')
    logger.warning("Description unavailable at {}; saving job-page diagnostics", driver.current_url)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Cannot create description diagnostic directory: {}", exc)
        return
    try:
        path = directory / 'debug_job_description.html'
        path.write_text(driver.page_source, encoding='utf-8')
        logger.info("Saved description HTML: {}", path)
    except (OSError, WebDriverException) as exc:
        logger.warning("Cannot save description HTML: {}", exc)
    try:
        path = directory / 'debug_job_description.png'
        if not driver.save_screenshot(str(path)):
            logger.warning("Browser did not save description screenshot: {}", path)
        else:
            logger.info("Saved description screenshot: {}", path)
    except (OSError, WebDriverException) as exc:
        logger.warning("Cannot save description screenshot: {}", exc)


def read_job_description(driver):
    logger.info("Reading job description at {}", driver.current_url)
    clicked = set()
    locators = [(By.CSS_SELECTOR, selector) for selector in DESCRIPTION_SELECTORS]
    locators.append((By.XPATH, DESCRIPTION_HEADING_XPATH))

    def extract(_):
        for by, selector in locators:
            try:
                candidates = driver.find_elements(by, selector)
            except WebDriverException:
                continue
            for body in candidates:
                try:
                    if not body.is_displayed():
                        continue
                    scopes = [body, *body.find_elements(By.XPATH, DESCRIPTION_EXPAND_SCOPE_XPATH)]
                    expanded_now = False
                    for scope in scopes:
                        for button in scope.find_elements(By.XPATH, DESCRIPTION_EXPAND_XPATH):
                            if button.id in clicked or not button.is_displayed() or not button.is_enabled():
                                continue
                            button.click()
                            clicked.add(button.id)
                            expanded_now = True
                            logger.info("Description Show more clicked at {}", driver.current_url)
                    if expanded_now:
                        # Reacquire after expansion: the old body may be replaced.
                        return False
                    text = body.text.strip()
                    if text:
                        logger.info("Description selector matched: {}; extracted {} characters; Show more clicked: {}; URL: {}",
                                    selector, len(text), bool(clicked), driver.current_url)
                        return text
                except WebDriverException:
                    # Re-rendered nodes and obstructed buttons may recover next poll.
                    continue
        return False

    try:
        return WebDriverWait(driver, 15, poll_frequency=0.5).until(extract)
    except (TimeoutException, WebDriverException) as exc:
        save_description_debug(driver)
        raise RuntimeError(f"Job description not found at {driver.current_url}; "
                           f"Show more clicked: {bool(clicked)}; diagnostics under data_folder/output") from exc
