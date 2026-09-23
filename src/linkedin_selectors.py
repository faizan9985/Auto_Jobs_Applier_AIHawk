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
