# Per-job resume tailoring

`tailor_resume_per_job: true` (default) selects content from the original
`data_folder/plain_text_resume.yaml` and renders a local PDF. No LLM or external
builder generates tailored resume content. The external resume object remains
available for the existing application-answer flow.

`src/resume_tailoring.py` separates three stages:

1. **Source facts:** a read-only YAML snapshot, hashed as canonical JSON with SHA-256.
2. **Selected facts:** exact scalar values paired with their source paths. Stable
   keyword overlap orders skills, experience bullets, and projects. Keep up to four
   bullets per position and three projects; retain the original employment order,
   employers, titles, dates, degree details and summary wording. Ties retain source
   order. Omitted leaf paths are recorded, including unsupported sections and
   bracketed placeholders. Legal/self-identification details are not rendered.
3. **Rendered resume:** ReportLab writes escaped selected values into a PDF. It
   adds section labels and layout, never accomplishments, metrics or job-derived
   claims. Content flows across pages without truncation.

The renderer embeds ReportLab's bundled Vera font. Unsupported characters cause a
clear error instead of silently substituting glyphs or changing candidate facts.

The source is user-attested, not independently verified. No skills are inferred
from job requirements or related technologies. No years of experience are
calculated. Each selected value is checked against its original source location.
Original YAML is never changed. Unsupported source sections are recorded as omitted;
review the PDF before approval to confirm the desired content and layout.

## Application integration

The manager prepares the tailored PDF after eligibility/blacklist checks and the
atomic application claim, before `job_apply` opens the job page. Ineligible jobs
never invoke tailoring. Upload uses that exact file instead of the fixed resume
or external builder, validates its SHA-256, and records the uploaded path. Final
submission requires that exact tailored file to have been uploaded and remain
unchanged. The existing manual approval screen displays its absolute path.
Approval metadata includes the tailoring record ID, PDF path and hash.

Set `tailor_resume_per_job: false` to preserve the existing fixed `--resume` PDF
behavior, including the legacy external-builder fallback when no fixed PDF exists.
Tailoring does not alter cover-letter generation, eligibility rules or relevance.

## Cache and regeneration

The cache key is stored job ID + canonical source hash + hash of title/description.
An unchanged job/profile reuses the same record and PDF, including across restarts.
Changes create a new record and file, preserving previous versions. To explicitly
regenerate selected applications:

```text
python main.py --mode apply --job-id JOB_ID --regenerate-resume
```

Normal retry flags still apply. A missing or modified cached file raises an error;
it is not silently regenerated. Explicit regeneration produces a fresh artifact
with approval status `pending`. Cache reuse never bypasses manual approval.

## SQLite schema v4

The new `resume_tailorings` table contains `id`, `job_id`, `source_hash`, `job_hash`,
`algorithm_version`, `resume_path`, `pdf_hash`, `source_facts`, `selected_facts`,
`matched_keywords`, `matched_skills`, `selected_experience_bullets`,
`selected_projects`, `omitted_items`, `generated_at`, and `approval_status`.
Structured fields are JSON. Source snapshots contain the candidate's private data
and remain in the local job database. Existing jobs and score/eligibility columns
are preserved. Approval decisions update the corresponding record transactionally
with job state, and the existing job event retains the approval's artifact identity.

Example (abbreviated, synthetic; hashes/paths are illustrative):

```json
{
  "job_id": "stored-job-id",
  "source_hash": "<SHA-256 of original profile>",
  "job_hash": "<SHA-256 of title and description>",
  "resume_path": "<output>/tailored_resumes/resume-<uuid>.pdf",
  "matched_skills": ["Python", "Unity"],
  "selected_experience_bullets": [
    {"source_path": ["experience_details", 0, "key_responsibilities", 1, "responsibility"],
     "value": "Built Unity simulation with Python tooling."}
  ],
  "selected_projects": [
    {"source_path": ["projects", 1, "name"], "value": "Simulator"}
  ],
  "omitted_items": [["interests", 0]],
  "generated_at": "<UTC timestamp>",
  "approval_status": "pending"
}
```
