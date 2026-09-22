from dataclasses import asdict

import pytest

from src.job_application_profile import CandidateEligibility
from src.job_eligibility import JobEligibilityEvaluator


def evaluate(description, **facts):
    return JobEligibilityEvaluator().evaluate(description, CandidateEligibility(**facts))


@pytest.mark.parametrize("description", [
    "We are unable to sponsor.", "No visa sponsorship.",
    "We cannot sponsor applicants.", "Sponsorship is not available.",
    "We cannot offer visa sponsorship.", "We do not provide immigration sponsorship.",
    "Must work without sponsorship.",
])
def test_no_sponsorship(description):
    result = evaluate(description, requires_future_h1b_sponsorship=True)
    assert result.status == "ineligible"
    assert result.sponsorship_status == "does_not_support"
    assert result.evidence and all(e in description for e in result.evidence)


def test_no_sponsorship_without_need():
    assert evaluate("No sponsorship.", requires_future_h1b_sponsorship=False).status == "eligible"


def test_explicit_sponsorship():
    result = evaluate("Visa sponsorship is available.", requires_future_h1b_sponsorship=True)
    assert result.status == "eligible"
    assert result.sponsorship_status == "supports"
    assert result.work_authorization_status == "unknown"


def test_sponsorship_silence():
    result = evaluate("Build software for our team.", requires_future_h1b_sponsorship=True)
    assert result.status == "needs_review"
    assert result.sponsorship_status == "unknown"
    assert result.evidence == []


@pytest.mark.parametrize("citizen,expected", [(None, "ineligible"), (False, "ineligible"), (True, "eligible")])
def test_citizenship(citizen, expected):
    result = evaluate("Must be a U.S. citizen.", is_us_citizen=citizen, requires_future_h1b_sponsorship=False)
    assert result.status == expected
    assert result.work_authorization_status == ("compatible" if citizen else "incompatible")


def test_citizen_or_resident():
    assert evaluate("Must be a U.S. citizen or permanent resident.",
                    is_us_permanent_resident=True, requires_future_h1b_sponsorship=False).status == "eligible"


def test_residency_required():
    assert evaluate("Must be a US permanent resident.", is_us_permanent_resident=False).status == "ineligible"


@pytest.mark.parametrize("description", [
    "U.S. citizenship is required for security clearance.",
    "US citizens only.", "This position requires United States citizenship.",
])
def test_explicit_citizenship_forms(description):
    assert evaluate(description).status == "ineligible"


def test_lawful_resident_alternative():
    assert evaluate("Must be a U.S. citizen or a lawful permanent resident.",
                    is_us_permanent_resident=True, requires_future_h1b_sponsorship=False).status == "eligible"


def test_clearance_does_not_infer_citizenship():
    result = evaluate("Security clearance required.", current_visa_status="F-1")
    assert result.status == "needs_review"
    assert result.work_authorization_status == "unknown"
    assert evaluate("Security clearance required; must be a U.S. citizen.").status == "ineligible"


@pytest.mark.parametrize("authorized,expected", [(True, "eligible"), (False, "ineligible"), (None, "needs_review")])
def test_generic_authorization(authorized, expected):
    result = evaluate("Must be legally authorized to work in the United States.",
                      currently_authorized_to_work_in_us=authorized, requires_future_h1b_sponsorship=False)
    assert result.status == expected


def test_no_authorization_inference_from_opt():
    result = evaluate("Must be authorized to work in the US.", opt_eligible=True, current_visa_status="F-1")
    assert result.status == "needs_review"
    assert result.work_authorization_status == "unknown"


@pytest.mark.parametrize("enrolled,expected", [(True, "eligible"), (False, "ineligible"), (None, "needs_review")])
def test_enrollment(enrolled, expected):
    result = evaluate("Internship: must be currently enrolled in college.",
                      currently_enrolled=enrolled, requires_future_h1b_sponsorship=False)
    assert result.status == expected


@pytest.mark.parametrize("returning,expected", [(True, "eligible"), (False, "ineligible"), (None, "needs_review")])
def test_return_to_school(returning, expected):
    result = evaluate("Interns must return to school after the internship. Start date: 2030-06-01.",
                      graduation_date="2030-05-01", earliest_start_date="2030-06-01",
                      returning_to_school_after_internship=returning, requires_future_h1b_sponsorship=False)
    assert result.status == expected


@pytest.mark.parametrize("graduation,expected", [
    ("2030-05-01", "eligible"), ("2030-08-31", "eligible"),
    ("2030-04-30", "ineligible"), ("2030-09-01", "ineligible"), (None, "needs_review"),
])
def test_graduation_window(graduation, expected):
    result = evaluate("Must graduate between May 2030 and August 2030.",
                      graduation_date=graduation, requires_future_h1b_sponsorship=False)
    assert result.status == expected


@pytest.mark.parametrize("earliest,expected", [
    ("2030-05-01", "eligible"), ("2030-06-01", "eligible"),
    ("2030-06-02", "ineligible"), (None, "needs_review"),
])
def test_start_date(earliest, expected):
    result = evaluate("Start date: June 1, 2030.", earliest_start_date=earliest, requires_future_h1b_sponsorship=False)
    assert result.status == expected


def test_month_start_precision():
    assert evaluate("Starts in June 2030.", earliest_start_date="2030-06-15",
                    requires_future_h1b_sponsorship=False).status == "needs_review"


@pytest.mark.parametrize("description", [
    "Sponsorship may be available.", "Must graduate in summer 2030.",
    "Start date: 2030-02-30.", "Start date is flexible.",
    "US citizenship preferred.", "Must be a US citizen unless an exception applies.",
    "Location: Paris.", "Looking for an enthusiastic engineer.", "",
    "We do not offer visa sponsorship except for some roles.",
    "Applicants must not be currently enrolled.",
    "Must be a US citizen or have work authorization.",
    "We can sponsor if approved by management.",
])
def test_ambiguous(description):
    assert evaluate(description, requires_future_h1b_sponsorship=False).status == "needs_review"


def test_conflicting_sponsorship():
    result = evaluate("No sponsorship. Visa sponsorship is available.", requires_future_h1b_sponsorship=True)
    assert result.status == "needs_review"
    assert result.sponsorship_status == "unknown"


def test_qualified_sponsorship_conflict():
    result = evaluate("No sponsorship. Sponsorship may be available for some applicants.",
                      requires_future_h1b_sponsorship=True)
    assert result.status == "needs_review"
    assert result.sponsorship_status == "unknown"


def test_authorization_mention_is_not_a_requirement():
    result = evaluate("We welcome people authorized to work in the US.",
                      currently_authorized_to_work_in_us=False)
    assert result.status == "needs_review"


def test_recognized_rule_does_not_hide_ambiguous_dates():
    result = evaluate("We offer sponsorship and require graduation in summer 2030.")
    assert result.status == "needs_review"
    assert result.date_status == "unknown"


@pytest.mark.parametrize("description", [
    "We offer sponsorship and require authorization to work in Canada.",
    "We offer sponsorship but cannot support H1B applicants.",
    "We offer sponsorship and relocation is expected.",
])
def test_recognized_rule_does_not_hide_other_requirements(description):
    assert evaluate(description).status == "needs_review"


def test_country_alias():
    assert evaluate("Location: U.S.", target_countries=["United States"],
                    requires_future_h1b_sponsorship=False).status == "eligible"


@pytest.mark.parametrize("description", [
    "Must graduate between 2029 and 2030.",
    "Must graduate between 2030-01-01 and 2030-12-31.",
])
def test_graduation_date_formats(description):
    assert evaluate(description, graduation_date="2030-06-01",
                    requires_future_h1b_sponsorship=False).status == "eligible"


@pytest.mark.parametrize("targets,expected", [(["USA"], "ineligible"), (["Canada"], "eligible"), (None, "needs_review")])
def test_country(targets, expected):
    assert evaluate("Location: Canada.", target_countries=targets,
                    requires_future_h1b_sponsorship=False).status == expected


@pytest.mark.parametrize("relocate,expected", [(True, "eligible"), (False, "ineligible"), (None, "needs_review")])
def test_relocation(relocate, expected):
    assert evaluate("Relocation is required.", willing_to_relocate=relocate,
                    requires_future_h1b_sponsorship=False).status == expected


def test_authorization_interval():
    result = evaluate("Must be authorized to work in the US. Start date: 2030-06-01.",
                      currently_authorized_to_work_in_us=True, work_authorization_end_date="2030-05-31",
                      earliest_start_date="2030-05-01", requires_future_h1b_sponsorship=False)
    assert result.status == "ineligible"
    assert result.work_authorization_status == "incompatible"


def test_hard_failure_wins_over_unrelated_uncertainty():
    assert evaluate("No sponsorship. Must graduate in summer 2030.",
                    requires_future_h1b_sponsorship=True).status == "ineligible"


def test_serializable_and_no_mutation():
    candidate = CandidateEligibility(requires_future_h1b_sponsorship=True)
    before = asdict(candidate)
    evaluator = JobEligibilityEvaluator()
    result = evaluator.evaluate("We can sponsor.", candidate)
    assert asdict(result)["status"] == "eligible"
    assert asdict(candidate) == before
    assert evaluator.evaluate("Unclear role.", candidate).status == "needs_review"


@pytest.mark.parametrize("field", ["is_us_citizen", "is_us_permanent_resident", "currently_enrolled", "returning_to_school_after_internship"])
def test_new_facts_require_booleans(field):
    with pytest.raises(TypeError):
        CandidateEligibility(**{field: "yes"})
