"""Conservative, offline screening of explicit English job requirements.

Application code uses these results as review-only metadata, never as a gate.
Eligible means the recognized requirements match the supplied facts, not a
legal determination. Unsupported or conditional eligibility language needs
human review. No immigration rules are derived from visa names or OPT flags.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Literal, Optional

from src.job_application_profile import CandidateEligibility


Compatibility = Literal["compatible", "incompatible", "unknown"]


@dataclass
class EligibilityResult:
    status: Literal["eligible", "ineligible", "needs_review"] = "needs_review"
    reasons: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    sponsorship_status: Literal["supports", "does_not_support", "unknown"] = "unknown"
    work_authorization_status: Compatibility = "unknown"
    enrollment_status: Compatibility = "unknown"
    date_status: Compatibility = "unknown"


_US = r"(?:U\.?S\.?|USA|United States)"
_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_DATE = rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|{_MONTH}(?: \d{{1,2}},?)? \d{{4}}|\d{{4}})"
_COUNTRIES = {
    "us": "united states", "u.s.": "united states", "usa": "united states",
    "u.s.a.": "united states", "united states of america": "united states",
    "uk": "united kingdom", "u.k.": "united kingdom",
    "canada": "canada", "india": "india", "germany": "germany",
    "united states": "united states", "united kingdom": "united kingdom",
    "australia": "australia", "france": "france",
}


def _country(value: str) -> str:
    value = value.strip().lower()
    return _COUNTRIES.get(value, value)


def _date_bounds(value: str):
    """Preserve month/year precision rather than inventing a specific day."""
    try:
        if re.fullmatch(r"\d{4}", value):
            return date(int(value), 1, 1), date(int(value), 12, 31)
        for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%B %Y"):
            try:
                parsed = datetime.strptime(value, fmt).date()
            except ValueError:
                continue
            if fmt == "%B %Y":
                return parsed, parsed.replace(day=calendar.monthrange(parsed.year, parsed.month)[1])
            return parsed, parsed
    except ValueError:
        pass
    return None


class JobEligibilityEvaluator:
    """Evaluate description + explicit profile facts; no I/O, LLM, or clock.

    A definite mismatch wins over missing/ambiguous facts. Conflicting or
    qualified requirements are reviewed instead of treated as definite rules.
    Silence leaves each dimension unknown. Missing sponsorship language needs
    review unless the candidate explicitly says future sponsorship is unneeded.
    """

    def evaluate(self, description: str, candidate: CandidateEligibility) -> EligibilityResult:
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        result = EligibilityResult()
        failures, reviews = [], []
        dimensions = {name: [] for name in (
            "work_authorization_status", "enrollment_status", "date_status")}
        recognized = 0

        def record(excerpt, reason, compatible: Optional[bool], dimension=None):
            nonlocal recognized
            recognized += 1
            if excerpt not in result.evidence:
                result.evidence.append(excerpt)
            result.reasons.append(reason)
            if compatible is False:
                failures.append(reason)
            elif compatible is None:
                reviews.append(reason)
            if dimension:
                dimensions[dimension].append(compatible)

        # Split sentences without breaking U.S. abbreviations or exact excerpts.
        clauses = [m.group().strip() for m in re.finditer(
            r"[^\n;!?]+(?:[;!?]|$)", description, re.M)]
        clauses = [part.strip() for clause in clauses for part in re.split(
            r"(?<!U\.S)(?<!U\.K)(?<!U\.S\.A)(?<!U)(?<!S)\.(?=\s|$)", clause) if part.strip()]

        sponsorship = []
        ambiguous_sponsorship = False

        def ambiguous(clause, reason):
            nonlocal ambiguous_sponsorship
            record(clause, reason, None)
            ambiguous_sponsorship |= bool(re.search(r"sponsor", clause, re.I))
            for pattern, dimension in (
                (r"authoriz|citizen|permanent residen|clearance", "work_authorization_status"),
                (r"enroll|student|return to school", "enrollment_status"),
                (r"graduat|start date|starts? (?:on|in)", "date_status"),
            ):
                if re.search(pattern, clause, re.I):
                    dimensions[dimension].append(None)

        for clause in clauses:
            lower = clause.lower()
            relevant = re.search(
                r"sponsor|authoriz|citizen|permanent residen|clearance|enroll|student|"
                r"return to school|graduat|start date|starts? (?:on|in)|relocat|"
                r"location|based in|located in|work in|remote from|reside in", lower)
            if not relevant:
                continue
            before = recognized
            # Qualifications/exceptions must not become hard exclusions.
            if re.search(r"\b(?:may(?! \d)|might|prefer(?:red|ably)?|typically|generally|sometimes|"
                r"unless|except|if|but|only|negotiable|flexible|not required|case.by.case)\b", lower) and not re.fullmatch(rf"{_US} citizens only", clause, re.I):
                ambiguous(clause, "Conditional or qualified eligibility language requires review.")
                continue

            no_sponsor = re.search(
                r"\bno (?:visa |immigration |employment )?sponsorship\b|"
                r"(?:unable to|cannot|can't|will not|do not|does not) (?:provide |offer )?(?:visa |immigration )?sponsor|"
                r"sponsorship (?:is |will be )?not (?:available|provided|offered)|"
                r"without (?:current or future |visa )?sponsorship", lower)
            yes_sponsor = re.search(
                r"(?:we |company )?(?:offer|offers|provide|provides) (?:visa |immigration )?sponsorship|"
                r"(?:visa )?sponsorship (?:is )?available|"
                r"(?:we )?(?:will|can) sponsor", lower)
            if re.search(r"\b(?:not|never|no|without|cannot|can't)\b", lower) and not no_sponsor:
                ambiguous(clause, "Negated eligibility language requires review.")
                continue
            if no_sponsor or yes_sponsor:
                sponsorship.append((clause, bool(yes_sponsor) and not bool(no_sponsor)))

            citizen = re.search(
                rf"(?:must be (?:a |an )?|requires? |required:? ){_US} citizen(?:ship|s)?|"
                rf"{_US} citizenship (?:is )?required|{_US} citizens only", clause, re.I)
            resident = re.search(
                rf"(?:must be (?:a |an )?|requires? |required:? ){_US} permanent resident|"
                rf"{_US} permanent residen(?:cy|ce) (?:is )?required", clause, re.I)
            either = citizen and re.search(rf"\bor (?:a |an )?(?:{_US} )?(?:lawful )?permanent resident", clause, re.I)
            if (citizen or resident) and " or " in lower and not either:
                record(clause, "Alternative citizenship/residency requirements need review.", None, "work_authorization_status")
                continue
            if citizen or resident:
                match = (candidate.is_us_citizen is True or candidate.is_us_permanent_resident is True) if either else (
                    candidate.is_us_citizen is True if citizen else candidate.is_us_permanent_resident is True)
                record(clause, "Required citizenship/residency is documented." if match else
                       "Required citizenship/residency is not documented.", match, "work_authorization_status")
            if "clearance" in lower and not citizen:
                record(clause, "Clearance requirement cannot be verified from candidate facts.", None, "work_authorization_status")

            authorization = re.search(rf"(?:must be |required to be )(?:currently |already )?(?:legally )?authorized to work in (?:the )?{_US}\b", clause, re.I)
            if authorization:
                fact = candidate.currently_authorized_to_work_in_us
                record(clause, "US work authorization " + {True: "is documented.", False: "is explicitly absent.", None: "is unspecified."}[fact], fact, "work_authorization_status")

            enrollment = re.search(r"(?:must (?:currently )?be |requires? |required:? )(?:a )?(?:currently )?enrolled|must be (?:a )?(?:current )?student", lower)
            if enrollment:
                fact = candidate.currently_enrolled
                record(clause, "Current enrollment " + {True: "is documented.", False: "is explicitly absent.", None: "is unspecified."}[fact], fact, "enrollment_status")
            returning = re.search(r"(?:must|required to) return to school|returning to school (?:after|following)", lower)
            if returning:
                fact = candidate.returning_to_school_after_internship
                record(clause, "Enrollment after the internship " + {True: "is documented.", False: "is explicitly absent.", None: "is unspecified; graduation alone does not establish future enrollment."}[fact], fact, "enrollment_status")

            window = re.search(rf"(?:graduat\w* (?:date )?(?:must be )?between) ({_DATE}) and ({_DATE})", clause, re.I)
            if window:
                start, end = (_date_bounds(window.group(i)) for i in (1, 2))
                fact = candidate.graduation_date
                valid = start and end and start[0] <= end[1]
                match = start[0] <= fact <= end[1] if valid and fact else None
                record(clause, "Graduation date " + {True: "matches the inclusive window.", False: "falls outside the required window.", None: "or required window is unspecified/invalid."}[match], match, "date_status")

            start_match = re.search(rf"(?:start date(?: is|:)?|starts? on|starts? in|must start(?: on| by)?)\s+({_DATE})", clause, re.I)
            if start_match:
                bounds = _date_bounds(start_match.group(1))
                earliest = candidate.earliest_start_date
                match = None
                if bounds and earliest:
                    match = True if earliest <= bounds[0] else False if earliest > bounds[1] else None
                record(clause, "Role start date " + {True: "is compatible with candidate availability.", False: "precedes candidate availability.", None: "or candidate availability requires clarification."}[match], match, "date_status")
                if bounds and re.search(r"authoriz", description, re.I):
                    auth_start, auth_end = candidate.work_authorization_start_date, candidate.work_authorization_end_date
                    if auth_start or auth_end:
                        outside = (auth_start and auth_start > bounds[1]) or (auth_end and auth_end < bounds[0])
                        within = auth_start and auth_end and auth_start <= bounds[0] and auth_end >= bounds[1]
                        record(clause, "Compare role start with the documented authorization interval.", False if outside else True if within else None, "work_authorization_status")

            location = re.search(r"(?:location:|(?:must be )?(?:based|located) in|must (?:work|reside) in|remote from)\s+(.+)", clause, re.I)
            if location:
                places = {_country(name) for name in _COUNTRIES if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", location.group(1), re.I)}
                targets = candidate.target_countries
                match = bool(places & {_country(c) for c in targets}) if places and targets is not None else None
                record(clause, "Explicit role country " + {True: "matches a target country.", False: "does not match any target country.", None: "or candidate target countries require clarification."}[match], match)
            relocation = re.search(r"(?:must|required to) relocate|relocation (?:is )?required", lower)
            if relocation:
                fact = candidate.willing_to_relocate
                record(clause, "Required relocation " + {True: "is accepted.", False: "is declined.", None: "requires candidate confirmation."}[fact], fact)

            # A recognized rule must not hide a second, unsupported requirement
            # in the same sentence (e.g. sponsorship plus a vague graduation date).
            for unresolved, dimension in (
                ("graduat" in lower and not window, "date_status"),
                (bool(re.search(r"start date|starts? (?:on|in)", lower)) and not start_match, "date_status"),
                (bool(re.search(r"enroll|student", lower)) and not enrollment and not returning, "enrollment_status"),
                (bool(re.search(r"citizen|permanent residen", lower)) and not citizen and not resident, "work_authorization_status"),
                ("authoriz" in lower and not authorization, "work_authorization_status"),
                ("relocat" in lower and not relocation, None),
                (bool(re.search(r"\blocation|based in|located in|remote from|reside in", lower)) and not location, None),
                ("sponsor" in lower and not no_sponsor and not yes_sponsor, None),
            ):
                if unresolved:
                    record(clause, "An additional eligibility requirement needs clarification.", None, dimension)

            # Sponsorship is aggregated below to handle contradictory statements.
            if recognized == before and not (no_sponsor or yes_sponsor):
                record(clause, "Eligibility language could not be resolved deterministically.", None)

        if sponsorship:
            values = {supported for _, supported in sponsorship}
            if len(values) > 1 or ambiguous_sponsorship:
                for clause, _ in sponsorship:
                    record(clause, "Conflicting sponsorship statements require review.", None)
            else:
                supports = values.pop()
                result.sponsorship_status = "supports" if supports else "does_not_support"
                need = candidate.requires_future_h1b_sponsorship
                compatible = True if supports or need is False else False if need is True else None
                for clause, _ in sponsorship:
                    record(clause, "Sponsorship is explicitly available." if supports else
                           "Sponsorship is unavailable; " + {True: "candidate needs future sponsorship.", False: "candidate reports no future sponsorship need.", None: "candidate sponsorship need is unspecified."}[need], compatible)
        elif candidate.requires_future_h1b_sponsorship is not False:
            reviews.append("Sponsorship availability is unknown.")
            result.reasons.append(reviews[-1])

        for dimension, values in dimensions.items():
            setattr(result, dimension, "incompatible" if False in values else
                    "unknown" if not values or None in values else "compatible")
        if not recognized:
            reviews.append("No explicit eligibility requirements could be evaluated.")
            result.reasons.append(reviews[-1])
        result.status = "ineligible" if failures else "needs_review" if reviews else "eligible"
        return result
