# LinkedIn session and discovery diagnostics

Authentication checks are non-navigating. Visible login/authwall controls and
login/checkpoint paths take precedence. Signed-in navigation selectors are tried
independently; feed, messaging, network and notification paths also identify a
session. Public-capable jobs and profile URLs require signed-in navigation or a
session cookie, never a public URL alone. Cookie contents are not logged.

When Chrome starts on a blank/non-LinkedIn tab, startup probes `/feed/` before
considering `/login`. Already authenticated pages remain in place. Password,
passkey, SSO and checkpoint completion use the same bounded manual authentication
wait; timeout stops startup instead of silently proceeding into discovery.

`src/linkedin_selectors.py` centralizes ordered fallback selectors for job cards,
scroll containers, titles, companies, locations, links and application methods.
Cards can be found by data attributes, old/new list classes or list items containing
job-view links. Results are deduplicated. Scroll containers are optional. Each
field is extracted independently, with ARIA labels, data-ID URLs and visible method
labels as additional fallbacks. Missing method text means unknown, not Applied.
Raw card HTML is no longer printed to the console.

Logs report the current URL, matching authentication path/selector, card selector
and count, and field fallback selections. After a 10-second card wait finds nothing,
discovery independently attempts these captures:

- `data_folder/output/debug_jobs_page.html`
- `data_folder/output/debug_jobs_page.png`

These are overwritten on the next zero-card page. The HTML/screenshot reflect the
browser's signed-in page and may contain personal information; inspect locally.
No upload is performed. A visible “no results” message or hidden template does not
short-circuit card lookup.

The selectors are compatibility fallbacks tested with mocked DOM responses. They
have not been verified against this user's current live session; LinkedIn can serve
different markup by account or experiment. If jobs remain visible but undetected,
the saved captures are the evidence needed to refine the matching selectors.

Use `--mode discover` for the next live diagnosis. Application, eligibility,
relevance, manual approval, resume tailoring and SQLite state policies are unchanged.

Additional fallbacks include job-card-container view attributes, div job IDs,
and job-title test IDs. Empty job links are skipped without dropping valid
cards. Application-method extraction checks every matching footer item,
including when Promoted precedes Easy Apply. Empty session cookies do not
establish authentication.
