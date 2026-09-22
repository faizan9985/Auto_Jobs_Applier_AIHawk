# Manual approval before submission

Applications now run from the SQLite inventory; see [job database](job_database.md).
Approval decisions are committed to SQLite before the final click. Deferred and
aborted applications use processing state `deferred`, while retaining their
distinct application outcomes and approval decisions.

`manual_approval_before_submit: true` is the default, including for existing
config files that omit the setting. Only the YAML boolean `false` disables the
gate and restores automatic submission. Other types are rejected.

The bot searches, evaluates, generates documents, and fills forms as before.
At the final Submit application button, the terminal displays the company, job
title, location, URL, eligibility status and reasons, sponsorship status, uploaded
resume and cover letter paths, and cached/generated answers used on this job.
Unrecorded files are explicitly labeled so they can be checked in the browser.
Only an explicit `approve` allows the final click. Invalid or blank input prompts
again; EOF or Ctrl+C at the prompt means abort.

| Choice | Application status | Output file | Behavior |
| --- | --- | --- | --- |
| approve | submitted | success.json | Click final submit and continue |
| skip | skipped_by_user | skipped_by_user.json | Discard form and continue |
| defer | deferred_for_review | deferred_for_review.json | Discard form, retain local review record, continue |
| abort | aborted | aborted.json | Discard form and exit the application loop |

Deferral is a local review record, not a saved LinkedIn draft or automatic resume
of a partially completed form. A later attempt must fill the form again.
Failures retain the existing exception handling and are recorded as `failed`.
Existing discovery skips and collection records retain their existing statuses.
`submitted` means the existing final-click sequence completed; it does not add
server-side confirmation beyond the legacy behavior.

Output records include `application_status`, `approval` (decision, UTC timestamp,
and the gate setting), `cover_letter_path`, and `application_answers` alongside
the existing resume path and eligibility metadata. Automatic submission records
`auto_submit`, not a manual approval. Jobs that never reach the gate have null
approval metadata. Answers are scoped to each attempt; unrelated cached answers
are not included. Eligibility remains advisory and does not control submission.
