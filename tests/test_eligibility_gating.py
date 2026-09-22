import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from main import ConfigError, ConfigValidator
from src.aihawk_easy_applier import AIHawkEasyApplier
from src.aihawk_job_manager import AIHawkJobManager
from src.job import Job
from src.job_store import JobStore


@pytest.fixture
def manager(tmp_path):
    manager = AIHawkJobManager(Mock())
    manager.job_store = JobStore(tmp_path / 'jobs.db')
    manager.output_file_directory = tmp_path
    manager.company_blacklist = manager.title_blacklist = manager.location_blacklist = []
    manager.apply_once_at_company = False
    manager.seen_jobs = []
    manager.easy_applier_component = Mock(spec=AIHawkEasyApplier)
    manager.easy_applier_component.job_apply.return_value = 'submitted'
    return manager


def stored(manager, status):
    job = Job('Engineer', 'Example', 'Remote', 'https://example.com/job', 'Easy Apply',
              description='Original description')
    manager.job_store.upsert(job)
    job.eligibility = {'status': status, 'reasons': ['Specific candidate mismatch'],
                       'evidence': ['Original description'], 'sponsorship_status': 'unknown'}
    manager.job_store.evaluate(job)
    manager.job_store.score(job, {'skills': ['Python']})
    return job


def test_ineligible_skips_before_browser_documents_or_failure(manager, monkeypatch):
    job = stored(manager, 'ineligible')
    before = manager.job_store.get(job.job_id)
    monkeypatch.setattr(Job, 'evaluate_eligibility', Mock(side_effect=AssertionError('Use persisted result')))
    manager.apply_jobs()
    manager.easy_applier_component.job_apply.assert_not_called()
    manager.easy_applier_component._fill_application_form.assert_not_called()
    manager.easy_applier_component._create_and_upload_resume.assert_not_called()
    manager.easy_applier_component._create_and_upload_cover_letter.assert_not_called()
    manager.driver.get.assert_not_called()
    row = manager.job_store.get(job.job_id)
    assert row['state'] == row['application_status'] == 'skipped'
    assert row['skip_reason'] == 'ineligible'
    assert row['failure_reason'] is None
    for key in ('eligibility', 'total_score', 'reasons', 'resume_path', 'cover_letter_path', 'approval'):
        assert row[key] == before[key]
    assert not (manager.output_file_directory / 'failed.json').exists()
    export = json.loads((manager.output_file_directory / 'skipped.json').read_text())[0]
    assert export['skip_reason'] == 'ineligible'
    assert export['eligibility'] == job.eligibility
    with manager.job_store.connect() as db:
        events = list(db.execute('SELECT state,metadata FROM job_events ORDER BY id'))
    assert not any(e['state'] in ('applying', 'failed') for e in events)
    assert json.loads(events[-1]['metadata'])['eligibility'] == job.eligibility


@pytest.mark.parametrize('status', ['eligible', 'needs_review'])
def test_allowed_statuses_use_persisted_result(manager, monkeypatch, status):
    job = stored(manager, status)
    monkeypatch.setattr(Job, 'evaluate_eligibility', Mock(side_effect=AssertionError('Use persisted result')))
    warning = Mock()
    monkeypatch.setattr('src.aihawk_job_manager.utils.printyellow', warning)
    manager.apply_jobs()
    manager.easy_applier_component.job_apply.assert_called_once()
    assert manager.job_store.get(job.job_id)['state'] == 'submitted'
    if status == 'needs_review':
        assert 'ELIGIBILITY REVIEW REQUIRED' in warning.call_args.args[0]
        assert job.eligibility['reasons'][0] in warning.call_args.args[0]
    else:
        warning.assert_not_called()


def test_disabled_enforcement_allows_ineligible(manager):
    job = stored(manager, 'ineligible')
    manager.enforce_eligibility_filter = False
    manager.apply_jobs()
    manager.easy_applier_component.job_apply.assert_called_once()
    row = manager.job_store.get(job.job_id)
    assert row['state'] == 'submitted'
    assert row['skip_reason'] is None
    assert json.loads(row['eligibility']) == job.eligibility
    assert manager.manual_approval_before_submit is True


@pytest.mark.parametrize('state,option', [('failed', 'retry_failed'), ('deferred', 'include_deferred'),
                                        ('applying', 'retry_interrupted'), ('approved', 'retry_interrupted')])
def test_selected_retries_are_gated(manager, state, option):
    job = stored(manager, 'ineligible')
    manager.job_store.transition(job, 'applying')
    if state != 'applying':
        manager.job_store.transition(job, state)
    setattr(manager, option, True)
    manager.apply_jobs()
    assert manager.job_store.get(job.job_id)['state'] == 'skipped'
    manager.easy_applier_component.job_apply.assert_not_called()


def test_gate_cannot_overwrite_concurrent_state_or_submission(manager):
    job = stored(manager, 'ineligible')
    old = manager.job_store.get(job.job_id)['state']
    manager.job_store.transition(job, 'applying')
    with pytest.raises(ValueError):
        manager.job_store.skip_ineligible(job.job_id, expected_state=old)
    manager.job_store.transition(job, 'submitted')
    with pytest.raises(ValueError):
        manager.job_store.skip_ineligible(job.job_id, expected_state='submitted')


def test_schema_two_migration(manager):
    job = stored(manager, 'ineligible')
    with manager.job_store.connect() as db:
        db.execute('ALTER TABLE jobs DROP COLUMN skip_reason')
        db.execute('PRAGMA user_version=2')
    store = JobStore(manager.job_store.path)
    assert json.loads(store.get(job.job_id)['eligibility']) == job.eligibility
    assert store.get(job.job_id)['skip_reason'] is None
    with store.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 4


def test_missing_persisted_result_is_evaluated_and_allowed(manager):
    job = Job('Engineer', 'Example', 'Remote', 'https://example.com/job', 'Easy Apply')
    manager.job_store.upsert(job)
    manager.apply_jobs()
    manager.easy_applier_component.job_apply.assert_called_once()
    assert json.loads(manager.job_store.get(job.job_id)['eligibility'])['status'] == 'needs_review'


def test_unselected_failed_job_is_not_changed(manager):
    job = stored(manager, 'ineligible')
    manager.job_store.transition(job, 'applying')
    manager.job_store.transition(job, 'failed', failure_reason='Previous failure')
    before = manager.job_store.get(job.job_id)
    manager.apply_jobs()
    assert manager.job_store.get(job.job_id) == before


def test_gate_rechecks_persisted_eligibility(manager):
    job = stored(manager, 'eligible')
    with pytest.raises(ValueError):
        manager.job_store.skip_ineligible(job.job_id, expected_state='evaluated')
    assert manager.job_store.get(job.job_id)['state'] == 'evaluated'


@pytest.mark.parametrize('value', [None, True, False, 'false', 0])
def test_config_default_and_boolean_validation(tmp_path, value):
    config = yaml.safe_load(Path('data_folder_example/config.yaml').read_text())
    if value is None:
        config.pop('enforce_eligibility_filter')
    else:
        config['enforce_eligibility_filter'] = value
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(config))
    if value is not None and type(value) is not bool:
        with pytest.raises(ConfigError, match='enforce_eligibility_filter'):
            ConfigValidator.validate_config(path)
        with pytest.raises(ValueError, match='enforce_eligibility_filter'):
            AIHawkJobManager(Mock()).set_parameters(config)
    else:
        parsed = ConfigValidator.validate_config(path)
        assert parsed['enforce_eligibility_filter'] is (True if value is None else value)
        parsed['outputFileDirectory'] = tmp_path
        result = AIHawkJobManager(Mock())
        result.set_parameters(parsed)
        assert result.enforce_eligibility_filter is parsed['enforce_eligibility_filter']
        assert result.manual_approval_before_submit is True
