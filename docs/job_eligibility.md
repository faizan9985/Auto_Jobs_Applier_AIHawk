# Review-only job eligibility evaluation

`JobEligibilityEvaluator.evaluate(description: str, candidate: CandidateEligibility)`
returns an `EligibilityResult` dataclass. It performs no I/O or LLM calls.
The Easy Apply flow retrieves the description when missing, attaches a review
to `Job.eligibility`, and logs its status, sponsorship status, and reasons before
opening the form. Eligibility never changes filtering or final submission.

The shared output writer persists an `eligibility` block in success, failed,
skipped, and collected (`data`) records. Jobs without a review are evaluated
using any description already available. Collection does not fetch additional
descriptions. Missing descriptions or candidate profiles produce `needs_review`
with unknown dimension statuses. Description retrieval errors are logged and
the application flow continues with the available job information.

```python
from dataclasses import asdict
from src.job_application_profile import CandidateEligibility
from src.job_eligibility import JobEligibilityEvaluator

result = JobEligibilityEvaluator().evaluate(
    "We are unable to sponsor.",
    CandidateEligibility(requires_future_h1b_sponsorship=True),
)
print(asdict(result))
```

Result:

```json
{
  "status": "ineligible",
  "reasons": ["Sponsorship is unavailable; candidate needs future sponsorship."],
  "evidence": ["We are unable to sponsor"],
  "sponsorship_status": "does_not_support",
  "work_authorization_status": "unknown",
  "enrollment_status": "unknown",
  "date_status": "unknown"
}
```

All evidence entries are literal substrings of the description, with surrounding
whitespace and sentence delimiters potentially removed. Reasons describe how
those excerpts compare to the supplied candidate facts.

| Description | Candidate facts | Result |
| --- | --- | --- |
| Visa sponsorship is available. | Future sponsorship needed | eligible; sponsorship supports |
| Build software for our team. | Future sponsorship needed | needs_review; sponsorship unknown |
| Must be a U.S. citizen. | Citizenship unspecified | ineligible; authorization incompatible |
| Must be authorized to work in the US. | Authorization true; future sponsorship false | eligible; authorization compatible; sponsorship unknown |
| Must graduate between May 2030 and August 2030. | Graduation 2030-06-01; future sponsorship false | eligible; dates compatible |
| Start date: June 1, 2030. | Earliest start 2030-07-01 | ineligible; dates incompatible |

## Rules and interpretation

- Explicit inability to sponsor conflicts with a documented future H-1B
  sponsorship need. Explicit availability sets `supports`, but does not establish
  work authorization. Contradictory sponsorship statements require review.
- Sponsorship silence stays `unknown`. It requires review unless the candidate
  explicitly reports no future sponsorship need.
- Required US citizenship or permanent residency must be affirmatively documented.
  This deliberate screening rule treats missing documentation as ineligible;
  it is not a claim about the person's actual citizenship. Citizen-or-resident
  alternatives accept either documented fact.
- Generic US work authorization compares only to
  `currently_authorized_to_work_in_us`. Clearance alone requires review;
  citizenship is enforced only when the description explicitly requires it.
- Current enrollment and returning to school compare to separate optional boolean
  facts. A graduation date alone cannot establish current or future enrollment.
  Missing return-to-school documentation requires review, including when
  graduation precedes the internship.
- Graduation windows written as `graduate/graduating/graduation [date] [must be]
  between DATE and DATE` are inclusive. Dates support ISO days, English full-month
  dates, month/year, and years. Month/year boundaries retain their precision.
- Explicit role start dates compare to `earliest_start_date`. An overlapping
  imprecise month/year requires review. Documented authorization boundaries are
  also checked at the start date when the description mentions authorization;
  they do not establish authorization on their own.
- Explicit location labels and residence/work-location requirements compare
  recognized country names to `target_countries`. Supported country names are
  United States, United Kingdom, Canada, India, Germany, Australia, and France;
  US/USA/U.S./U.S.A. and UK/U.K. aliases are normalized. Unrecognized places
  require review; cities are not mapped to countries. Remote work alone does not
  establish country compatibility. Explicit required relocation compares to
  `willing_to_relocate`.
- A definite mismatch takes precedence over unrelated uncertainty. Otherwise,
  conditional, unsupported, or missing relevant facts require review. No
  recognized requirements also produces review. Eligible means the recognized
  requirements match and no unresolved eligibility language was detected; it
  does not certify all possible legal or employment requirements.

The optional profile booleans `is_us_citizen`, `is_us_permanent_resident`,
`currently_enrolled`, and `returning_to_school_after_internship` default to `None`.
They accept only booleans or null, as do the existing boolean facts. Visa labels,
OPT/STEM OPT flags, and other profile sections never supply inferred facts.

This is a conservative English pattern evaluator, not a general natural-language
parser. Unsupported wording should be reviewed. It is intentionally isolated
from production filtering while its coverage is evaluated.
