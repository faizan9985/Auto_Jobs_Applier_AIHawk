import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.aihawk_easy_applier import AIHawkEasyApplier
from src.aihawk_job_manager import AIHawkJobManager
from src.job import Job
from src.job_application_profile import CandidateEligibility


@pytest.fixture
def candidate():
    return CandidateEligibility(requires_future_h1b_sponsorship=True)


@pytest.fixture
def job():
    return Job("Engineer", "Example", "Remote", "https://example.com/job/1", "Easy Apply")


@pytest.fixture
def applier(monkeypatch, candidate):
    monkeypatch.setattr(AIHawkEasyApplier, "_load_questions_from_json", lambda self: [])
    monkeypatch.setattr("src.aihawk_easy_applier.time.sleep", lambda _: None)
    monkeypatch.setattr("src.aihawk_easy_applier.ActionChains", Mock())
    answerer = Mock(job_application_profile=SimpleNamespace(candidate_eligibility=candidate))
    result = AIHawkEasyApplier(Mock(), None, [], answerer, Mock())
    for name in ("check_for_premium_redirect", "_find_easy_apply_button",
                 "_get_job_recruiter", "_fill_application_form", "_discard_application"):
        monkeypatch.setattr(result, name, Mock())
    result._get_job_recruiter.return_value = ""
    return result


@pytest.mark.parametrize("description,status", [
    ("Visa sponsorship is available.", "eligible"),
    ("We are unable to sponsor.", "ineligible"),
    ("Build software for our team.", "needs_review"),
])
def test_review_attached_before_application_without_gating(applier, job, description, status):
    applier._get_job_description = Mock(return_value=description)

    def check_review(_):
        assert job.description == description
        assert job.eligibility["status"] == status

    applier._fill_application_form.side_effect = check_review
    applier.job_apply(job)
    applier._fill_application_form.assert_called_once_with(job)
    applier._discard_application.assert_not_called()


@pytest.mark.parametrize("description", [None, "", "   "])
def test_missing_description_continues(applier, job, description):
    applier._get_job_description = Mock(return_value=description)
    applier.job_apply(job)
    assert job.eligibility["status"] == "needs_review"
    assert job.eligibility["sponsorship_status"] == "unknown"
    assert "Job description is unavailable." in job.eligibility["reasons"]
    applier._fill_application_form.assert_called_once_with(job)


def test_description_retrieval_failure_continues(applier, job):
    applier._get_job_description = Mock(side_effect=RuntimeError("Unavailable"))
    applier.job_apply(job)
    assert job.eligibility["status"] == "needs_review"
    applier._fill_application_form.assert_called_once_with(job)


@pytest.mark.parametrize("profile", [None, SimpleNamespace(), SimpleNamespace(candidate_eligibility=None)])
def test_missing_profile_and_existing_description(applier, job, profile):
    job.description = "We are unable to sponsor."
    applier.gpt_answerer.job_application_profile = profile
    applier._get_job_description = Mock()
    applier.job_apply(job)
    applier._get_job_description.assert_not_called()
    assert job.eligibility["status"] == "needs_review"
    assert job.eligibility["sponsorship_status"] == "unknown"
    assert "Candidate eligibility profile is unavailable." in job.eligibility["reasons"]
    applier._fill_application_form.assert_called_once_with(job)


@pytest.mark.parametrize("output", ["success", "failed", "skipped", "reviewed", "data"])
def test_persisted_json_has_review(tmp_path, candidate, job, output):
    manager = AIHawkJobManager(Mock())
    manager.output_file_directory = tmp_path
    manager.gpt_answerer = SimpleNamespace(
        job_application_profile=SimpleNamespace(candidate_eligibility=candidate))
    job.description = "We are unable to sponsor."
    manager.write_to_file(job, output)
    manager.write_to_file(job, output)
    records = json.loads((tmp_path / f"{output}.json").read_text())
    assert len(records) == 2
    assert records[0]["eligibility"] == records[1]["eligibility"] == job.eligibility
    assert records[0]["eligibility"] == {
        "status": "ineligible",
        "reasons": ["Sponsorship is unavailable; candidate needs future sponsorship."],
        "evidence": ["We are unable to sponsor"],
        "sponsorship_status": "does_not_support",
        "work_authorization_status": "unknown",
        "enrollment_status": "unknown",
        "date_status": "unknown",
    }


def test_early_failure_persists_unknown_review(tmp_path, job):
    manager = AIHawkJobManager(Mock())
    manager.output_file_directory = tmp_path
    manager.write_to_file(job, "failed")
    review = json.loads((tmp_path / "failed.json").read_text())[0]["eligibility"]
    assert review["status"] == "needs_review"
    assert len(review["reasons"]) == 2


def test_failed_application_preserves_review(applier, job, tmp_path):
    applier._get_job_description = Mock(return_value="We are unable to sponsor.")
    applier._fill_application_form.side_effect = RuntimeError("Form failed")
    with pytest.raises(Exception, match="Form failed"):
        applier.job_apply(job)
    manager = AIHawkJobManager(Mock())
    manager.output_file_directory = tmp_path
    manager.write_to_file(job, "failed")
    assert json.loads((tmp_path / "failed.json").read_text())[0]["eligibility"]["status"] == "ineligible"
