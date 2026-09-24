"""Ordered discovery fallbacks; keep layout-specific markup out of state logic."""

AUTHENTICATED = (
    '#global-nav', '[data-test-global-nav-link="feed"]',
    'nav a[href*="/messaging/"]', 'a[href*="/mynetwork/"]',
    'button.global-nav__primary-link-me-menu-trigger',
)
LOGIN_FORMS = ('input#session_key', 'input#username', 'input[name="session_password"]',
               'form[action*="login-submit"]', '.authwall', '[data-tracking-control-name="auth_wall_desktop-login-toggle"]')
CARD_SELECTORS = (
    '[data-occludable-job-id]', 'li[data-job-id]',
    '.job-card-container[data-job-id]', '[data-view-name="job-card"]',
    '[data-view-name="job-card-container"]', 'div[data-job-id]',
    '.jobs-search-results__list-item', '.scaffold-layout__list-item',
    '.scaffold-layout__list-container > li', '.job-search-card',
    'li:has(a[href*="/jobs/view/"])', '[role="listitem"]:has(a[href*="/jobs/view/"])',
)
SCROLL_CONTAINERS = ('.jobs-search-results-list', '.scaffold-layout__list',
                     '.jobs-search-results-list__list', '.scaffold-layout__list-container')
TITLE_SELECTORS = ('.job-card-list__title--link span[aria-hidden="true"]',
                   '.job-card-list__title strong', '.job-card-list__title--link',
                   '.job-card-list__title', '[data-view-name="job-card"] a[href*="/jobs/view/"]',
                   '.base-search-card__title', '[data-testid="job-title"]', 'a[href*="/jobs/view/"] strong',
                   'a[href*="/jobs/view/"] span[aria-hidden="true"]', 'a[href*="/jobs/view/"]')
COMPANY_SELECTORS = ('.job-card-container__primary-description',
                     '.artdeco-entity-lockup__subtitle', '.job-card-container__company-name',
                     '.base-search-card__subtitle', '[data-testid="company-name"]', 'a[href*="/company/"]')
LOCATION_SELECTORS = ('.job-card-container__metadata-item', '.artdeco-entity-lockup__caption',
                      '.job-search-card__location', '[data-testid="job-location"]')
LINK_SELECTORS = ('a.job-card-list__title--link', 'a.job-card-list__title',
                  'a.base-card__full-link', 'a[href*="/jobs/view/"]')
METHOD_SELECTORS = ('.job-card-container__apply-method', '.job-card-container__footer-item',
                    '.job-search-card__easy-apply-label', '[aria-label*="Easy Apply"]')

# Current SDUI header from the saved detail page. Scope away from similar jobs
# and the company overview; class names on this layout are generated.
DETAIL_HEADER_SELECTOR = '[id^="JobDetails_ManageJobBanner_"] + div'
DETAIL_TITLE_SELECTORS = (
    f'{DETAIL_HEADER_SELECTOR} [data-display-contents="true"] > p',
    '[data-testid="job-title"]',
    '.job-details-jobs-unified-top-card__job-title h1',
    '.jobs-unified-top-card__job-title', '.top-card-layout__title',
)
DETAIL_COMPANY_SELECTORS = (
    f'{DETAIL_HEADER_SELECTOR} a[href*="/company/"]',
    '.job-details-jobs-unified-top-card__company-name a',
    '.jobs-unified-top-card__company-name a',
    '.topcard__org-name-link', '[data-testid="company-name"]',
)
DETAIL_LOCATION_SELECTORS = (
    f'{DETAIL_HEADER_SELECTOR} p:has(> span:nth-of-type(2)) > span:first-child',
    '[data-testid="job-location"]',
    '.job-details-jobs-unified-top-card__primary-description-container .tvm__text--low-emphasis',
    '.jobs-unified-top-card__bullet', '.topcard__flavor--bullet',
)

# Narrow description bodies first; never fall back to main/body/job-details panes.
DESCRIPTION_SECTION_SELECTOR = '[id^="JobDetails_AboutTheJob_"]'
DESCRIPTION_TEXT_BOX_SELECTOR = '[data-testid="expandable-text-box"]'
DESCRIPTION_EXPAND_BUTTON_SELECTOR = '[data-testid="expandable-text-button"]'
DESCRIPTION_SELECTORS = (
    '#job-details', '.jobs-description-content__text',
    '.job-details-about-the-job-module__description',
    '[data-testid="job-description"]', '[data-view-name="job-description"]',
    '[data-test-id="job-description"]',
    '[data-view-name="job-details-about-the-job"] .show-more-less-html__markup',
    'section.description .show-more-less-html__markup',
    '[aria-label="Job description"]', '[aria-labelledby="job-description-heading"]',
    '[aria-labelledby="job-details-about-the-job-heading"]',
)
DESCRIPTION_HEADING_XPATH = (
    '//section[.//h2[normalize-space(.)="About the job"]]'
    '//*[contains(@class,"show-more-less-html__markup")]'
)
DESCRIPTION_EXPAND_XPATH = (
    './/button[not(@aria-expanded="true") and ('
    '@aria-label="Click to see more description" or '
    'contains(@aria-label,"Show more description") or '
    'normalize-space(.)="Show more" or normalize-space(.)="See more" or '
    'normalize-space(.)="Show more, more about job")]|'
    './/*[@role="button" and @aria-expanded="false" and '
    '(normalize-space(.)="Show more" or normalize-space(.)="See more")]'
)
DESCRIPTION_EXPAND_SCOPE_XPATH = (
    './ancestor::*[contains(concat(" ",normalize-space(@class)," ")," jobs-description ") '
    'or (self::section and (.//h2[normalize-space(.)="About the job"] '
    'or contains(concat(" ",normalize-space(@class)," ")," description ")))][1]'
)
