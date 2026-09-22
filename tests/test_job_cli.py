from unittest.mock import Mock

from click.testing import CliRunner

import main as app
from src.job import Job
from src.job_store import JobStore


def test_pending_and_empty_apply_need_no_credentials_or_browser(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    browser = Mock(side_effect=AssertionError("Must not launch a browser"))
    monkeypatch.setattr(app, "init_browser", browser)
    runner = CliRunner()
    result = runner.invoke(app.main, ["--mode", "pending"])
    assert result.exit_code == 0
    result = runner.invoke(app.main, ["--mode", "apply"])
    assert "No selected pending jobs" in result.output
    assert result.exit_code == 0
    browser.assert_not_called()


def test_pending_shows_stored_ids_and_retry_states(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    database = tmp_path / "custom.sqlite3"
    store = JobStore(database)
    job = Job("Engineer", "Example", "Remote", "https://www.linkedin.com/jobs/view/123", "Easy Apply")
    store.upsert(job)
    store.transition(job, "applying")
    store.transition(job, "failed", failure_reason="Test error")
    result = CliRunner().invoke(app.main, ["--mode", "pending", "--database", str(database), "--job-id", job.job_id])
    assert result.exit_code == 0
    assert f"{job.job_id} | failed | Example | Engineer" in result.output


def test_discover_alias_and_retry_options_are_forwarded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = tmp_path / "data_folder" / "plain_text_resume.yaml"
    profile.parent.mkdir()
    profile.write_text("profile")
    monkeypatch.setattr(app.ConfigValidator, "validate_config", Mock(return_value={}))
    secrets = Mock(side_effect=AssertionError("Discovery needs no LLM secret"))
    monkeypatch.setattr(app.ConfigValidator, "validate_secrets", secrets)
    run = Mock()
    monkeypatch.setattr(app, "create_and_run_bot", run)
    result = CliRunner().invoke(app.main, ["--collect"])
    assert result.exit_code == 0
    assert run.call_args.args[0]["collectMode"] is True
    assert run.call_args.args[1] is None
    secrets.assert_not_called()


def test_discovery_setup_avoids_resume_generation(tmp_path, monkeypatch):
    profile = tmp_path / "profile.yaml"
    profile.write_text("test profile")
    browser = Mock()
    manager = Mock()
    monkeypatch.setattr(app, "init_browser", Mock(return_value=browser))
    monkeypatch.setattr(app, "AIHawkJobManager", Mock(return_value=manager))
    monkeypatch.setattr(app, "AIHawkAuthenticator", Mock())
    monkeypatch.setattr(app, "JobApplicationProfile", Mock())
    app.create_and_run_bot({"uploads": {"plainTextResume": profile}, "collectMode": True}, None)
    manager.start_collecting_data.assert_called_once()
    manager.start_applying.assert_not_called()
    browser.quit.assert_called_once()
