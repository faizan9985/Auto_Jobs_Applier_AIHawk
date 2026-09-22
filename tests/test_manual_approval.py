import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import NoSuchElementException

from src.aihawk_easy_applier import AIHawkEasyApplier
from src.aihawk_job_manager import AIHawkJobManager
from src.job import Job


@pytest.fixture
def applier(monkeypatch):
    monkeypatch.setattr(AIHawkEasyApplier, "_load_questions_from_json", lambda _: [])
    monkeypatch.setattr("src.aihawk_easy_applier.time.sleep", lambda _: None)
    result = AIHawkEasyApplier(Mock(), None, [], Mock(), Mock())
    result.current_job = Job("Engineer", "Example", "Remote", "https://example.com/job", "Easy Apply")
    result.current_job.evaluate_eligibility()
    result.driver.find_element.return_value.text = "Submit application"
    result._unfollow_company = Mock()
    result._discard_application = Mock()
    return result


@pytest.mark.parametrize("decision,status", [
    ("approve", "submitted"), ("skip", "skipped_by_user"),
    ("defer", "deferred_for_review"), ("abort", "aborted"),
])
def test_gate_decisions(applier, monkeypatch, decision, status):
    button = applier.driver.find_element.return_value

    def choose(_):
        button.click.assert_not_called()
        return decision

    monkeypatch.setattr("builtins.input", choose)
    assert applier._next_or_submit() == status
    assert applier.current_job.application_status == status
    assert button.click.call_count == (1 if decision == "approve" else 0)
    assert applier._discard_application.call_count == (0 if decision == "approve" else 1)
    approval = applier.current_job.approval
    assert approval["decision"] == decision
    assert datetime.fromisoformat(approval["timestamp"]).utcoffset().total_seconds() == 0


def test_disabled_gate_keeps_legacy_submit(applier, monkeypatch):
    applier.manual_approval_before_submit = False
    prompt = Mock(side_effect=AssertionError("Must not prompt"))
    monkeypatch.setattr("builtins.input", prompt)
    assert applier._next_or_submit() == "submitted"
    applier.driver.find_element.return_value.click.assert_called_once()
    assert applier.current_job.approval["decision"] == "auto_submit"


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_closed_or_interrupted_input_aborts(applier, monkeypatch, error):
    monkeypatch.setattr("builtins.input", Mock(side_effect=error))
    assert applier._next_or_submit() == "aborted"
    applier.driver.find_element.return_value.click.assert_not_called()


def test_invalid_input_never_approves(applier, monkeypatch):
    monkeypatch.setattr("builtins.input", Mock(side_effect=["", "yes", "defer"]))
    assert applier._next_or_submit() == "deferred_for_review"
    applier.driver.find_element.return_value.click.assert_not_called()


def test_review_contains_files_eligibility_and_used_answers(applier, monkeypatch, capsys):
    job = applier.current_job
    job.pdf_path = "resume.pdf"
    job.cover_letter_path = "letter.pdf"
    applier._record_application_answer("Years of Python?", "3", "numeric", "cached")
    applier._record_application_answer("Why this role?", "Build useful software", "textbox", "generated")
    monkeypatch.setattr("builtins.input", lambda _: "skip")
    applier._next_or_submit()
    review = capsys.readouterr().out
    for value in (job.company, job.title, job.location, job.link, "needs_review", "unknown",
                  "Job description is unavailable.", "resume.pdf", "letter.pdf",
                  "[cached] Years of Python?: 3", "[generated] Why this role?: Build useful software"):
        assert value in review


@pytest.mark.parametrize("decision,status,filename", [
    ("approve", "submitted", "success"), ("skip", "skipped_by_user", "skipped_by_user"),
    ("defer", "deferred_for_review", "deferred_for_review"), ("abort", "aborted", "aborted"),
])
def test_manager_routes_and_persists_outcome(applier, monkeypatch, tmp_path, decision, status, filename):
    manager = AIHawkJobManager(Mock())
    manager.output_file_directory = tmp_path
    manager.database_path = tmp_path / "jobs.sqlite3"
    manager.apply_once_at_company = False
    manager.company_blacklist = manager.title_blacklist = manager.location_blacklist = []
    manager.seen_jobs = []
    for job_id in (123, 456):
        manager._store().upsert(Job("Engineer", "Example", "Remote",
                                   f"https://www.linkedin.com/jobs/view/{job_id}", "Easy Apply"))
    applier.approval_callback = manager._persist_approval
    applier.submitted_callback = manager._persist_submission
    monkeypatch.setattr("builtins.input", lambda _: decision)

    def apply(job):
        applier.current_job = job
        return applier._next_or_submit()

    manager.easy_applier_component = SimpleNamespace(job_apply=Mock(side_effect=apply))
    outcome = manager.apply_jobs()
    records = json.loads((tmp_path / f"{filename}.json").read_text())
    assert records[0]["application_status"] == status
    assert records[0]["approval"]["decision"] == decision
    assert records[0]["approval"]["timestamp"]
    assert (tmp_path / "success.json").exists() == (decision == "approve")
    assert manager.easy_applier_component.job_apply.call_count == (1 if decision == "abort" else 2)
    assert outcome == ("aborted" if decision == "abort" else None)


@pytest.mark.parametrize("enabled", [True, False])
def test_abort_returns_without_searching(monkeypatch, enabled):
    manager = AIHawkJobManager(Mock())
    manager.resume_path = None
    manager.manual_approval_before_submit = enabled
    manager.gpt_answerer = Mock()
    manager.resume_generator_manager = Mock()
    manager.positions, manager.locations = ["Engineer", "Developer"], ["Remote"]
    manager.next_job_page = Mock()
    manager.get_jobs_from_page = Mock(return_value=[Mock()])
    manager.apply_jobs = Mock(return_value="aborted")
    constructor = Mock()
    monkeypatch.setattr("src.aihawk_job_manager.AIHawkEasyApplier", constructor)
    monkeypatch.setattr("src.aihawk_job_manager.time.sleep", lambda _: None)
    assert manager.start_applying() == "aborted"
    manager.apply_jobs.assert_called_once()
    manager.next_job_page.assert_not_called()
    assert constructor.call_args.args[-1] is enabled


def test_next_page_does_not_prompt(applier, monkeypatch):
    applier.driver.find_element.return_value.text = "Next"
    applier._check_for_errors = Mock()
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("Premature prompt")))
    assert applier._next_or_submit() is None
    applier.driver.find_element.return_value.click.assert_called_once()


def test_form_returns_explicit_outcome(applier, monkeypatch):
    applier.fill_up = Mock()
    monkeypatch.setattr("builtins.input", lambda _: "defer")
    assert applier._fill_application_form(applier.current_job) == "deferred_for_review"
    applier.fill_up.assert_called_once()


def test_config_defaults_on_and_rejects_non_boolean(applier):
    assert applier.manual_approval_before_submit is True
    assert AIHawkJobManager(Mock()).manual_approval_before_submit is True
    with pytest.raises(ValueError, match="must be a boolean"):
        AIHawkJobManager(Mock()).set_parameters({"manual_approval_before_submit": "false"})
    with pytest.raises(ValueError, match="must be a boolean"):
        AIHawkEasyApplier(Mock(), None, [], Mock(), Mock(), "false")


@pytest.mark.parametrize("decision,status", [
    ("approve", "submitted"), ("skip", "skipped_by_user"),
    ("defer", "deferred_for_review"), ("abort", "aborted"),
])
def test_full_application_returns_status_and_resets_prior_answers(applier, monkeypatch, decision, status):
    job = applier.current_job
    job.description = "Build software"
    job.application_answers = [{"question": "Old job", "answer": "Old answer"}]
    applier.check_for_premium_redirect = Mock()
    applier._find_easy_apply_button = Mock()
    applier._get_job_recruiter = Mock(return_value="")
    applier.fill_up = Mock()
    monkeypatch.setattr("src.aihawk_easy_applier.ActionChains", Mock())
    monkeypatch.setattr("builtins.input", lambda _: decision)
    assert applier.apply_to_job(job) == status
    assert job.application_status == status
    assert job.application_answers == []


@pytest.mark.parametrize("cached", [True, False])
@pytest.mark.parametrize("kind", ["radio", "textbox", "numeric", "date", "dropdown"])
def test_records_answers_actually_used(applier, monkeypatch, cached, kind):
    question, answer = "question", "2026-09-22" if kind == "date" else "3"
    applier.all_data = [{"question": "unrelated", "type": kind, "answer": "unused"}]
    if cached:
        applier.all_data.append({"question": question, "type": kind, "answer": answer})
    applier._save_questions_to_json = Mock()
    applier.gpt_answerer.answer_question_from_options.return_value = answer
    applier.gpt_answerer.answer_question_textual_wide_range.return_value = answer
    applier.gpt_answerer.answer_question_numeric.return_value = answer
    applier.gpt_answerer.answer_question_date.return_value = datetime(2026, 9, 22)
    section = Mock(text=question)
    section.find_element.return_value.text = question
    if kind == "radio":
        section.find_element.return_value.find_elements.return_value = [Mock(text=answer)]
        assert applier._find_and_handle_radio_question(section)
    elif kind in {"textbox", "numeric"}:
        section.find_elements.return_value = [Mock()]
        applier._is_numeric_field = Mock(return_value=kind == "numeric")
        assert applier._find_and_handle_textbox_question(section)
    elif kind == "date":
        section.find_elements.return_value = [Mock()]
        assert applier._find_and_handle_date_question(section)
    else:
        section.find_element.return_value.find_elements.return_value = [Mock()]
        section.find_element.return_value.find_element.return_value.text = question
        select = Mock(options=[Mock(text=answer)])
        select.first_selected_option.text = ""
        monkeypatch.setattr("src.aihawk_easy_applier.Select", Mock(return_value=select))
        assert applier._find_and_handle_dropdown_question(section)
    assert applier.current_job.application_answers == [{
        "question": question, "answer": answer, "type": kind,
        "source": "cached" if cached else "generated",
    }]


def test_uploaded_existing_resume_path_is_recorded(applier, tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"test")
    applier.resume_path = resume
    upload = Mock()
    applier.driver.find_elements.return_value = [upload]
    applier.gpt_answerer.resume_or_cover.return_value = "resume"
    applier._handle_upload_fields(Mock(), applier.current_job)
    upload.send_keys.assert_called_once_with(str(resume.resolve()))
    assert applier.current_job.pdf_path == str(resume.resolve())


def test_failed_approval_persistence_prevents_submit(applier, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "approve")
    applier.approval_callback = Mock(side_effect=OSError("Database unavailable"))
    with pytest.raises(OSError, match="Database unavailable"):
        applier._next_or_submit()
    applier.driver.find_element.return_value.click.assert_not_called()
