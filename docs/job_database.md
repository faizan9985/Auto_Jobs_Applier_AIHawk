# Local job inventory

SQLite is the authoritative application inventory, using Python's standard library.
The default file is `data_folder/output/jobs.sqlite3`; `--database PATH` overrides
it for every mode. Schema version 1 is stored in `PRAGMA user_version`. Connections
commit each operation, use foreign keys, and close after each transaction.

## Commands

```sh
python main.py --mode discover
python main.py --mode pending
python main.py --mode apply
python main.py --mode apply --job-id INTERNAL_UUID
python main.py --mode apply --retry-failed --job-id INTERNAL_UUID
python main.py --mode apply --include-deferred --job-id INTERNAL_UUID
python main.py --mode pending --database path/to/jobs.sqlite3
python main.py --mode import-json
```

Discovery searches LinkedIn using the existing search configuration, reads full
descriptions, evaluates eligibility, and refreshes the inventory. It never opens
an application form or invokes resume generation. Discovery uses the candidate
profile but does not require an LLM API key. Missing descriptions keep any prior
stored description; otherwise eligibility is recorded as needing review.

Apply loads the stored description and metadata, re-evaluates against the current
profile, and visits the stored job URL directly. It never runs a discovery search.
The Easy Apply flow fetches a missing description if necessary. Manual approval
remains enabled by default. Eligibility is advisory: both ineligible and unknown
results are reviewable, and neither automatically filters a job. Existing job
blacklists, application-method restrictions, and once-per-company policy remain.

Pending lists UUID, state, company, title, and URL without opening a browser,
loading credentials, or generating documents. It includes failed, deferred, and
interrupted records for visibility; apply excludes those unless explicitly enabled.
Use `--job-id` to restrict a retry; without it, a retry flag includes all matching
jobs in addition to ordinary pending jobs.

## Schema

`jobs` stores:

| Columns | Storage |
| --- | --- |
| id | UUID text primary key |
| linkedin_job_id, normalized_url, fallback_key | Nullable, individually unique text keys |
| company, title, location, job_url, description | Text |
| apply_method, recruiter_link, source | Text |
| discovered_at, last_seen_at | UTC ISO timestamps |
| eligibility | JSON text with evaluator output |
| state | Checked processing state |
| application_status | Detailed result, e.g. skipped_by_user or aborted |
| approval_status, approval | Decision text and full JSON metadata with timestamp |
| resume_path, cover_letter_path | Text |
| application_answers | JSON list of answers used |
| submitted_at, failure_reason | Nullable UTC timestamp and error text |

`job_events` stores an integer event ID, job UUID foreign key, state, UTC timestamp,
and JSON metadata for discoveries, evaluations, transitions, and imports. Failed
attempt reasons and approval decisions remain in history after an intentional retry.

Deduplication uses LinkedIn ID (numeric view URL, slug suffix, or currentJobId)
first, then a normalized URL, then a normalized company/title/location hash only
when a URL is absent. Tracking parameters and fragments are removed from URL keys.
Distinct stable URLs/LinkedIn IDs are not merged merely because their titles match.
A fallback-only record can be promoted when its URL becomes known. Rediscovery
updates metadata and last_seen_at, preserving internal ID, discovered_at, application
state, approval, and existing nonempty descriptions when a fetch fails.

## State model

```text
discovered -> evaluated (eligible) or needs_review (other eligibility results)
discovered/evaluated/needs_review -> applying -> approved -> submitted
applying -> skipped | deferred | failed
approved -> failed
failed/deferred -> applying                 (explicit retry/include flag)
applying/approved -> applying               (explicit interrupted retry)
```

Blacklists and existing application restrictions may also move pending jobs to
skipped. Approve and legacy auto-submit commit `approved` before the click. Skip
records `skipped`; defer and abort record `deferred`. Abort stops the current run.
Submitted jobs are never selected for retry or reset by discovery. Claims are
transactional so ordinary pending jobs cannot be taken by two workers at once.

An interrupted browser or process can leave `applying` or `approved`. Check the
actual LinkedIn application first, then explicitly use `--retry-interrupted`
with `--job-id` if it was not submitted. Do not run concurrent recovery attempts.
There is no atomic transaction spanning SQLite and a remote browser click;
`submitted` retains the existing meaning that the final click returned, not a
new server-side confirmation. It is saved immediately after that click.

## Migration and compatibility

`python main.py` now applies stored jobs only. Run discovery first on a new
inventory. `--collect` remains an alias for discovery and still exports data.json.
Existing JSON files remain available; successful and failed applications and user
decisions still export to their previous filenames. Exports include internal IDs,
descriptions, database state, submission time, and failure reason. Export errors
are logged and cannot change a committed SQLite outcome.

Before applying with an existing JSON history, run `--mode import-json` once.
It reads recognized JSON outputs from `data_folder/output`, imports successes
first to prevent historical resubmissions, and does not roll back newer SQLite
states. Repeating it is safe. Missing historical timestamps stay null rather
than inventing submission dates; original JSON files are not modified. Historical
data records without descriptions can be enriched by discovery or by the apply
flow. Old failed.json entries no longer permanently suppress applications; use
`--retry-failed` to retry their database records intentionally.

Keep the SQLite file with the job output data when backing up or moving runs.
