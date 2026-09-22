import json
from unittest.mock import Mock

import pytest

from src.job import Job
from src.job_store import JobStore
from src.aihawk_job_manager import AIHawkJobManager


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "nested" / "jobs.sqlite3")


def make_job(url="https://www.linkedin.com/jobs/view/123", description="Visa sponsorship is available."):
    return Job("Engineer", "Example", "Remote", url, "Easy Apply", description=description)


def test_creation_and_reopen(store):
    job = make_job()
    row = store.upsert(job)
    assert row["id"] == job.job_id
    assert row["state"] == "discovered"
    assert row["linkedin_job_id"] == "123"
    assert row["discovered_at"] == row["last_seen_at"]
    assert JobStore(store.path).get(job.job_id) == row
    with store.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert db.execute("SELECT count(*) FROM job_events").fetchone()[0] == 1


@pytest.mark.parametrize("first,second", [
    ("https://www.linkedin.com/jobs/view/123?trk=abc", "https://uk.linkedin.com/jobs/view/engineer-123/"),
    ("https://www.linkedin.com/jobs/search/?currentJobId=123&keywords=python", "https://www.linkedin.com/jobs/view/123"),
    ("https://example.com/job/1/?utm_source=a#details", "https://EXAMPLE.com/job/1"),
    ("", ""),
])
def test_deduplication_and_update(store, first, second):
    a, b = make_job(first), make_job(second, "Updated full description")
    initial = store.upsert(a)
    result = store.upsert(b)
    assert a.job_id == b.job_id
    assert result["description"] == "Updated full description"
    assert result["discovered_at"] == initial["discovered_at"]
    assert result["last_seen_at"] >= initial["last_seen_at"]
    assert len(store.list_jobs()) == 1


def test_strong_identifiers_do_not_merge_same_title(store):
    store.upsert(make_job("https://www.linkedin.com/jobs/view/123"))
    store.upsert(make_job("https://www.linkedin.com/jobs/view/456"))
    assert len(store.list_jobs()) == 2


def test_fallback_promotes_to_strong_identifier(store):
    a, b = make_job(""), make_job()
    store.upsert(a)
    store.upsert(b)
    assert a.job_id == b.job_id
    assert store.get(a.job_id)["linkedin_job_id"] == "123"


def test_missing_url_reuses_single_known_record(store):
    a, b = make_job(), make_job("")
    store.upsert(a)
    store.upsert(b)
    assert a.job_id == b.job_id
    assert store.get(a.job_id)["job_url"] == a.link


def test_missing_url_does_not_guess_between_distinct_ids(store):
    a, b, c = make_job(), make_job("https://www.linkedin.com/jobs/view/456"), make_job("")
    for job in (a, b, c):
        store.upsert(job)
    assert len({a.job_id, b.job_id, c.job_id}) == 3


def test_state_transitions_eligibility_and_rediscovery(store):
    job = make_job()
    store.upsert(job)
    job.evaluate_eligibility()
    store.evaluate(job)
    assert store.get(job.job_id)["state"] == "needs_review"
    assert json.loads(store.get(job.job_id)["eligibility"]) == job.eligibility
    store.transition(job, "applying")
    job.approval = {"decision": "approve", "timestamp": "2026-09-22T00:00:00+00:00"}
    store.transition(job, "approved")
    job.application_status = "submitted"
    store.transition(job, "submitted")
    before = store.get(job.job_id)
    store.upsert(make_job(description=""))
    after = store.get(job.job_id)
    for name in ("state", "approval", "submitted_at", "description", "eligibility"):
        assert after[name] == before[name]
    assert after["submitted_at"]
    with pytest.raises(ValueError):
        store.transition(job, "applying", retry=True)
    with pytest.raises(ValueError):
        store.transition(job, "bogus")


def test_failed_retry_is_intentional(store):
    job = make_job()
    store.upsert(job)
    store.transition(job, "applying")
    store.transition(job, "failed", failure_reason="Browser unavailable")
    assert store.get(job.job_id)["failure_reason"] == "Browser unavailable"
    assert store.list_jobs() == []
    with pytest.raises(ValueError):
        store.transition(job, "applying")
    store.transition(job, "applying", retry=True)
    assert store.get(job.job_id)["state"] == "applying"
    with store.connect() as db:
        events = [json.loads(row[0]) for row in db.execute("SELECT metadata FROM job_events")]
    assert any(event.get("failure_reason") == "Browser unavailable" for event in events)


def test_claim_cannot_overwrite_another_attempt(store):
    job = make_job()
    store.upsert(job)
    store.transition(job, "applying", expected_state="discovered")
    with pytest.raises(ValueError):
        store.transition(job, "applying", expected_state="discovered")


def test_import_legacy_success_is_idempotent_and_prevents_resubmission(store, tmp_path):
    record = {"company": "Example", "job_title": "Engineer", "job_location": "Remote",
              "link": "https://www.linkedin.com/jobs/view/123", "eligibility": {"status": "needs_review"}}
    for name in ("success", "failed", "data"):
        (tmp_path / f"{name}.json").write_text(json.dumps([record]))
    assert store.import_json(tmp_path) == 1
    assert store.import_json(tmp_path) == 0
    assert store.list_jobs() == []
    assert len(store.list_jobs(["submitted"])) == 1
    assert store.has_submitted_company(" EXAMPLE ")


@pytest.fixture
def manager(store, tmp_path):
    result = AIHawkJobManager(Mock())
    result.job_store = store
    result.output_file_directory = tmp_path
    result.company_blacklist = result.title_blacklist = result.location_blacklist = []
    result.seen_jobs = []
    result.apply_once_at_company = False
    result.easy_applier_component = Mock()
    return result


def test_discovery_fetches_evaluates_and_never_applies(manager, monkeypatch):
    manager.driver.current_url = "https://www.linkedin.com/jobs/search/"
    manager.get_jobs_from_page = Mock(return_value=[Mock()])
    manager.extract_job_information_from_tile = Mock(return_value=("Engineer", "Example", "Remote", make_job().link, "Easy Apply"))
    reader = Mock()
    reader._get_job_description.return_value = "Full description. Visa sponsorship is available."
    monkeypatch.setattr("src.aihawk_job_manager.AIHawkEasyApplier", Mock(return_value=reader))
    monkeypatch.setattr("src.aihawk_job_manager.time.sleep", lambda _: None)
    manager.read_jobs()
    manager.read_jobs()
    rows = manager._store().list_jobs()
    assert len(rows) == 1
    assert rows[0]["description"] == reader._get_job_description.return_value
    assert json.loads(rows[0]["eligibility"])["status"] == "needs_review"
    reader.job_apply.assert_not_called()
    reader._find_easy_apply_button.assert_not_called()
    manager.easy_applier_component.job_apply.assert_not_called()


def test_apply_reads_stored_description_and_retry_flag(manager):
    job = make_job()
    manager._store().upsert(job)
    manager.easy_applier_component.job_apply.side_effect = RuntimeError("Network error")
    manager.apply_jobs()
    used = manager.easy_applier_component.job_apply.call_args.args[0]
    assert used.description == job.description
    assert used.job_id == job.job_id
    assert manager._store().get(job.job_id)["state"] == "failed"
    manager.apply_jobs()
    assert manager.easy_applier_component.job_apply.call_count == 1
    manager.retry_failed = True
    manager.easy_applier_component.job_apply.side_effect = None
    manager.easy_applier_component.job_apply.return_value = "submitted"
    manager.apply_jobs()
    assert manager.easy_applier_component.job_apply.call_count == 2
    assert manager._store().get(job.job_id)["state"] == "submitted"
    manager.driver.find_elements.assert_not_called()


def test_json_failure_does_not_change_submitted_state(manager):
    job = make_job()
    manager._store().upsert(job)
    manager.easy_applier_component.job_apply.return_value = "submitted"
    manager.write_to_file = Mock(side_effect=OSError("Read only export directory"))
    manager.apply_jobs()
    assert manager._store().get(job.job_id)["state"] == "submitted"
    manager.apply_jobs()
    manager.easy_applier_component.job_apply.assert_called_once()
