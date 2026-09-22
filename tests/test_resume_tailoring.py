import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from src.aihawk_easy_applier import AIHawkEasyApplier
from src.aihawk_job_manager import AIHawkJobManager
from src.job import Job
from src.job_store import JobStore
from src.resume_tailoring import ResumeTailor, select_facts


@pytest.fixture
def source():
    return {'personal_information': {'name': 'Sample Candidate', 'email': 'sample@example.com'},
            'summary': 'Software developer with project experience.',
            'skills': ['SQL', 'Python', 'Unity'],
            'experience_details': [{'position': 'Intern', 'company': 'Example',
                'employment_period': '2025 - 2026', 'key_responsibilities': [
                    {'responsibility': 'Maintained SQL reports.'},
                    {'responsibility': 'Built Unity simulation with Python tooling.'}]}],
            'projects': [{'name': 'Reports', 'description': 'SQL reports'},
                         {'name': 'Simulator', 'description': 'Unity simulation with Python tooling'}],
            'education_details': [{'education_level': 'Bachelor', 'year_of_completion': '2026'}],
            'interests': ['Rust'], 'legal_authorization': {'us_work_authorization': 'Yes'}}


@pytest.fixture
def setup(tmp_path, source):
    path = tmp_path / 'source.yaml'
    path.write_text(yaml.safe_dump(source), encoding='utf-8')
    store = JobStore(tmp_path / 'jobs.db')
    job = Job('Unity Developer', 'Company', 'Remote', 'https://example.com/job', 'Easy Apply',
              description='Unity simulation Python required. C# preferred. 5 years experience.')
    store.upsert(job)
    return ResumeTailor(store, path, tmp_path / 'resumes'), job


def test_verbatim_facts_and_deterministic_prioritization(source, setup):
    _, job = setup
    original = deepcopy(source)
    selected = select_facts(source, job, max_projects=1, max_bullets=1)
    assert source == original
    assert selected == select_facts(source, job, max_projects=1, max_bullets=1)
    for fact in selected['facts']:
        value = source
        for part in fact['source_path']:
            value = value[part]
        assert fact['value'] == value
    values = [f['value'] for f in selected['facts']]
    assert 'Simulator' in values and 'Reports' not in values
    assert 'Built Unity simulation with Python tooling.' in values
    assert 'Maintained SQL reports.' not in values
    assert {'Intern', 'Example', '2025 - 2026', 'Bachelor', '2026'} <= set(values)
    assert 'C#' not in selected['matched_skills']
    assert not any('5 years' in str(v) or 'Rust' == v for v in values)
    assert ['projects', 0, 'name'] in selected['omitted']


def test_persisted_metadata_and_cache(setup):
    tailor, job = setup
    before = tailor.source_path.read_bytes()
    first = tailor.prepare(job)
    second = ResumeTailor(tailor.store, tailor.source_path, tailor.output_directory).prepare(job)
    assert first == second
    assert tailor.source_path.read_bytes() == before
    assert Path(first['resume_path']).read_bytes().startswith(b'%PDF')
    assert first['approval_status'] == 'pending'
    assert first['job_id'] == job.job_id
    assert len(first['source_hash']) == 64
    assert json.loads(first['matched_skills']) == ['Python', 'Unity']
    assert json.loads(first['selected_experience_bullets'])[0]['source_path'][-2:] == [1, 'responsibility']
    assert json.loads(first['selected_projects'])[0]['source_path'][1] == 1
    assert json.loads(first['source_facts'])['skills'] == ['SQL', 'Python', 'Unity']
    assert json.loads(first['omitted_items'])
    with tailor.store.connect() as db:
        assert db.execute('SELECT count(*) FROM resume_tailorings').fetchone()[0] == 1


@pytest.mark.parametrize('change', ['source', 'description', 'explicit'])
def test_regeneration_invalidation(setup, source, change):
    tailor, job = setup
    first = tailor.prepare(job)
    if change == 'source':
        source['skills'].append('Docker')
        tailor.source_path.write_text(yaml.safe_dump(source))
    if change == 'description':
        job.description = 'SQL reporting'
    second = tailor.prepare(job, regenerate=change == 'explicit')
    assert first['id'] != second['id']
    assert first['resume_path'] != second['resume_path']
    assert Path(first['resume_path']).is_file()
    assert second['approval_status'] == 'pending'


def test_missing_or_modified_cache_requires_explicit_regeneration(setup):
    tailor, job = setup
    first = tailor.prepare(job)
    Path(first['resume_path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='explicitly regenerate'):
        tailor.prepare(job)
    assert tailor.prepare(job, regenerate=True)['id'] != first['id']


def make_applier(monkeypatch):
    monkeypatch.setattr(AIHawkEasyApplier, '_load_questions_from_json', lambda _: [])
    monkeypatch.setattr('src.aihawk_easy_applier.time.sleep', lambda _: None)
    applier = AIHawkEasyApplier(Mock(), None, [], Mock(), Mock())
    applier.gpt_answerer.resume_or_cover.return_value = 'resume'
    applier.driver.find_elements.return_value = [Mock()]
    return applier


def test_exact_pdf_upload_approval_and_metadata(setup, monkeypatch, capsys):
    tailor, job = setup
    record = tailor.prepare(job)
    job.tailoring_id = record['id']
    job.tailored_resume_path = record['resume_path']
    job.tailored_resume_hash = record['pdf_hash']
    applier = make_applier(monkeypatch)
    applier._handle_upload_fields(Mock(), job)
    applier.driver.find_elements.return_value[0].send_keys.assert_called_once_with(record['resume_path'])
    applier.resume_generator_manager.pdf_base64.assert_not_called()
    assert job.pdf_path == record['resume_path']
    manager = AIHawkJobManager(Mock())
    manager.job_store = tailor.store
    tailor.store.transition(job, 'applying')
    applier.approval_callback = manager._persist_approval
    applier.current_job = job
    applier._unfollow_company = Mock()
    applier.driver.find_element.return_value.text = 'Submit application'
    monkeypatch.setattr('builtins.input', lambda _: 'approve')
    assert applier._next_or_submit() == 'submitted'
    assert record['resume_path'] in capsys.readouterr().out
    with tailor.store.connect() as db:
        row = db.execute('SELECT * FROM resume_tailorings WHERE id=?', (record['id'],)).fetchone()
        assert row['approval_status'] == 'approve'


def test_unuploaded_tailored_resume_cannot_submit(setup, monkeypatch):
    tailor, job = setup
    record = tailor.prepare(job)
    job.tailored_resume_path = record['resume_path']
    job.tailored_resume_hash = record['pdf_hash']
    applier = make_applier(monkeypatch)
    applier.current_job = job
    applier.driver.find_element.return_value.text = 'Submit application'
    with pytest.raises(ValueError, match='must be uploaded'):
        applier._next_or_submit()
    applier.driver.find_element.return_value.click.assert_not_called()


def test_fixed_resume_mode(setup, monkeypatch, tmp_path):
    tailor, job = setup
    config = yaml.safe_load(Path('data_folder_example/config.yaml').read_text())
    config.update(tailor_resume_per_job=False, outputFileDirectory=tmp_path,
                  uploads={'plainTextResume': tailor.source_path})
    manager = AIHawkJobManager(Mock())
    manager.set_parameters(config)
    assert manager.resume_tailor is None
    fixed = tmp_path / 'fixed.pdf'
    fixed.write_bytes(b'%PDF fixed')
    applier = make_applier(monkeypatch)
    applier.resume_path = fixed
    applier._handle_upload_fields(Mock(), job)
    assert job.pdf_path == str(fixed.resolve())
    applier.resume_generator_manager.pdf_base64.assert_not_called()


def test_migration_from_schema_three(setup):
    tailor, job = setup
    before = tailor.store.get(job.job_id)
    with tailor.store.connect() as db:
        db.execute('DROP TABLE resume_tailorings')
        db.execute('PRAGMA user_version=3')
    migrated = JobStore(tailor.store.path)
    assert migrated.get(job.job_id) == before
    with migrated.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert db.execute('SELECT count(*) FROM resume_tailorings').fetchone()[0] == 0


@pytest.mark.parametrize('status', ['eligible', 'ineligible'])
def test_manager_tailors_only_after_eligibility_gate(setup, status):
    tailor, job = setup
    job.eligibility = {'status': status, 'reasons': [], 'evidence': []}
    tailor.store.evaluate(job)
    manager = AIHawkJobManager(Mock())
    manager.job_store = tailor.store
    manager.output_file_directory = tailor.output_directory.parent
    manager.resume_tailor = tailor
    manager.company_blacklist = manager.title_blacklist = manager.location_blacklist = []
    manager.seen_jobs = []
    manager.apply_once_at_company = False
    manager.easy_applier_component = Mock()
    def apply(prepared):
        assert prepared.tailoring_id
        assert Path(prepared.tailored_resume_path).is_file()
        return 'deferred_for_review'
    manager.easy_applier_component.job_apply.side_effect = apply
    manager.apply_jobs()
    with tailor.store.connect() as db:
        count = db.execute('SELECT count(*) FROM resume_tailorings').fetchone()[0]
    assert count == (1 if status == 'eligible' else 0)
    if status == 'ineligible':
        manager.easy_applier_component.job_apply.assert_not_called()


def test_cli_regeneration_forwarded(tmp_path, monkeypatch):
    import main as app
    from click.testing import CliRunner
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'data_folder'
    folder.mkdir()
    (folder / 'plain_text_resume.yaml').write_text('skills: [Python]')
    store = JobStore(folder / 'output' / 'jobs.sqlite3')
    store.upsert(Job('Engineer', 'Example', 'Remote', 'https://example.com/job', 'Easy Apply'))
    monkeypatch.setattr(app.ConfigValidator, 'validate_config', Mock(return_value={}))
    monkeypatch.setattr(app.ConfigValidator, 'validate_secrets', Mock(return_value='test'))
    run = Mock()
    monkeypatch.setattr(app, 'create_and_run_bot', run)
    result = CliRunner().invoke(app.main, ['--mode', 'apply', '--regenerate-resume'])
    assert result.exit_code == 0, result.output
    assert run.call_args.args[0]['regenerate_resume'] is True


@pytest.mark.parametrize('value', [None, True, False, 'false'])
def test_tailoring_config_is_boolean_default_true(tmp_path, value):
    from main import ConfigValidator, ConfigError
    config = yaml.safe_load(Path('data_folder_example/config.yaml').read_text())
    if value is None:
        config.pop('tailor_resume_per_job')
    else:
        config['tailor_resume_per_job'] = value
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(config))
    if value == 'false':
        with pytest.raises(ConfigError, match='tailor_resume_per_job'):
            ConfigValidator.validate_config(path)
    else:
        assert ConfigValidator.validate_config(path)['tailor_resume_per_job'] is (True if value is None else value)


def test_renderer_rejects_unsupported_glyph_instead_of_changing_fact(setup, source):
    tailor, job = setup
    source['personal_information']['name'] = 'Candidate \U0001f680'
    tailor.source_path.write_text(yaml.safe_dump(source), encoding='utf-8')
    with pytest.raises(ValueError, match='no substitution'):
        tailor.prepare(job)
