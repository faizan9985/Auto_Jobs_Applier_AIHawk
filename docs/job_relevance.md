# Deterministic job relevance

Discovery scores stored descriptions against the original user-supplied resume YAML.
`python main.py --mode pending --top 20` refreshes scores from
`data_folder/plain_text_resume.yaml` and shows the first 20 ranked records, without
a browser, LLM, or credentials. Without that file, existing scores remain visible
and records with no score display `unscored`. Application startup also refreshes
scores before ordering the stored inventory. Approval and submission rules are unchanged.

Ordering is eligible, needs_review, unknown/unevaluated, then ineligible; within
each group scores descend, followed by oldest discovery date and internal ID.
Pending retains its existing inclusion of deferred, failed, applying, and approved
records for inspection. Retry flags are still required to apply to those records.

Set `minimum_relevance_score: 50` in config.yaml or pass
`--minimum-relevance-score 50` to pending. This only labels records below the
threshold. It never filters them out, changes eligibility, or rejects applications.

## Weights and evidence

| Component | Maximum | Rule |
| --- | ---: | --- |
| Required skills | 35 | Fraction of recognized required skills explicitly listed in resume |
| Preferred skills | 10 | Fraction of recognized preferred skills explicitly listed in resume |
| Role/domain | 15 | Fraction of title families supported by prior titles, explicit skills, or project descriptions |
| Projects | 15 | At least one named project sharing a job domain or an explicitly verified matching skill |
| Experience | 10 | Explicit professional years / required years, capped at one; otherwise matching explicit seniority titles |
| Education | 10 | 5 for matching degree level, 5 for matching stated graduation year |
| Location | 5 | Explicit remote preference or in-person preference with matching candidate city |

The seven stored component scores sum to total_score; skill_score combines required
and preferred points. Reasons report their separate contributions. Missing evidence
earns zero, and absent requirements do not earn free points. Scores are evidence
coverage indicators, not probabilities of hiring or eligibility decisions.

Only `skills`, `technical_skills`, and experience/project `skills_acquired`, `skills`,
or `technologies` lists establish skills. Categorized mappings of lists are supported.
Aliases normalize names without inferring related technologies: Unity never implies
C#, React never implies JavaScript. Interests, search preferences, generated resumes,
and placeholder text are not skill evidence. The input is user-attested; the scorer
does not independently verify claims. It never invents skills or work experience.
Optional `professional_experience_years` is an explicitly supplied nonnegative number;
dates of employment, schooling, and project durations are not converted into years.

Supported title/domain families cover software, frontend, full-stack, XR/AR/VR,
Unity, graphics/3D, simulation/visualization, digital twin, new-grad software, and
post-graduate internships. Domain evidence affects relevance only; it cannot prove
internship eligibility or current enrollment.

## Parsing limits

This intentionally conservative rule-based implementation uses a finite skill
vocabulary extended by the candidate's explicit skill names. Unknown job-only
technologies are not detected. Required/preferred headings carry across lines;
unlabelled skill mentions count as required. Complex alternatives, negations,
degree equivalencies, graduation windows, geographic remote restrictions and
semantic similarity require human review. A missing description earns no skill
points and an explanatory reason. Relevance never replaces eligibility review.

## SQLite migration

Schema version 2 adds nullable numeric columns `total_score`, `skill_score`,
`role_score`, `project_score`, `experience_score`, `education_score`, `location_score`
and JSON-array text columns `matched_skills`, `missing_required_skills`,
`matched_projects`, `reasons` to the existing jobs table. Version 1 records, IDs,
events, states, eligibility, approvals and discovery timestamps are preserved.
Opening the store migrates the schema; rescoring writes only relevance columns.

For a synthetic profile with Python, SQL, Unity, a software engineer title,
a Unity simulation project, two explicitly stated professional years, a bachelor's
degree completed in 2026, and a remote preference, a corresponding posting scores:
skills 45 + role 15 + projects 15 + experience 10 + education 10 + location 5 = 100.
Removing SQL lowers required-skill points by 17.5, without changing eligibility.
