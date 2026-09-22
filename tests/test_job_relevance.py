import json
import sqlite3

import pytest
from click.testing import CliRunner

import main as app
from src.job import Job
from src.job_relevance import FAMILIES, score_job, validate_threshold
from src.job_store import JobStore


def job(description='Required: Python, SQL\nPreferred: Unity', title='Software Engineer'):
    return Job(title, 'Example', 'Remote', '', '', description=description)


def profile():
    return dict(skills=['Python', 'SQL', 'Unity'],
                experience_details=[dict(position='Software Engineer')],
                professional_experience_years=2,
                projects=[dict(name='Simulator', description='Unity simulation')],
                education_details=[dict(education_level="Bachelor's degree", year_of_completion='2026')],
                work_preferences=dict(remote_work='Yes'))


def test_full_breakdown_and_determinism():
    posting = job("Required: Python, SQL\nPreferred: Unity\n2 years experience. Bachelor's degree. Graduating 2026.")
    result = score_job(posting, profile())
    assert result == score_job(posting, profile())
    assert result['total_score'] == 100
    assert [result[k] for k in ('skill_score', 'role_score', 'project_score', 'experience_score',
                               'education_score', 'location_score')] == [45, 15, 15, 10, 10, 5]
    assert result['matched_projects'] == ['Simulator']


def test_required_skills_weight_more_and_eligibility_untouched():
    posting = job()
    posting.eligibility = {'status': 'eligible'}
    required = score_job(posting, {'skills': ['Python', 'SQL']})
    preferred = score_job(posting, {'skills': ['Unity']})
    assert required['skill_score'] == 35 > preferred['skill_score'] == 10
    assert preferred['missing_required_skills'] == ['python', 'sql']
    assert posting.eligibility == {'status': 'eligible'}


def test_no_fabricated_skills_or_experience():
    facts = dict(interests=['Python'], summary='SQL expert',
                 projects=[dict(name='Demo', description='Unity C# Python SQL')],
                 experience_details=[dict(position='Unity Developer', employment_period='2000 - Present')])
    result = score_job(job('Required: Python, SQL, C#, Unity\n5 years experience'), facts)
    assert result['matched_skills'] == []
    assert result['skill_score'] == result['experience_score'] == 0
    assert score_job(job(), {})['total_score'] == 0


def test_aliases_boundaries_and_unknown_skills():
    result = score_job(job('Required: Java, C, C++, C#, React.js, Elixir'),
                       {'skills': ['JavaScript', 'C++', 'C sharp', 'React', 'Elixir']})
    assert result['matched_skills'] == ['c#', 'c++', 'elixir', 'react']
    assert result['missing_required_skills'] == ['c', 'java']


def test_required_and_preferred_in_separate_sentences():
    result = score_job(job('Required: Python. Preferred: Unity.'), {'skills': ['Python']})
    assert result['skill_score'] == 35
    assert result['missing_required_skills'] == []


def test_placeholder_and_preferences_do_not_establish_skills():
    result = score_job(job(), {'skills': ['[Python]'], 'positions': ['Software Engineer'],
                              'interests': ['SQL', 'Unity']})
    assert result['total_score'] == 0
    assert result['matched_skills'] == []


@pytest.mark.parametrize('family', list(FAMILIES))
def test_role_families(family):
    title = FAMILIES[family][0]
    result = score_job(job(title=title), {'experience_details': [{'position': title}]})
    assert result['role_score'] == 15
    assert 0 <= result['total_score'] <= 100


def test_persistence_and_advisory_independence(tmp_path):
    store = JobStore(tmp_path / 'jobs.db')
    posting = job()
    store.upsert(posting)
    posting.eligibility = {'status': 'eligible'}
    store.evaluate(posting)
    before = store.get(posting.job_id)
    result = store.score(posting, profile())
    row = JobStore(store.path).get(posting.job_id)
    for key, value in result.items():
        assert (json.loads(row[key]) if isinstance(value, list) else row[key]) == value
    for key in ('eligibility', 'state', 'approval', 'discovered_at'):
        assert row[key] == before[key]


def test_migration_preserves_existing_record(tmp_path):
    path = tmp_path / 'old.db'
    store = JobStore(path)
    posting = job()
    store.upsert(posting)
    # Recreate the actual pre-scoring jobs schema, retaining data and events.
    with sqlite3.connect(path) as db:
        for column in score_job(posting, {}):
            db.execute(f'ALTER TABLE jobs DROP COLUMN {column}')
        db.execute('PRAGMA user_version=1')
    migrated = JobStore(path)
    assert migrated.get(posting.job_id)['state'] == 'discovered'
    assert migrated.get(posting.job_id)['total_score'] is None
    migrated.score(posting, profile())


def test_ordering_eligibility_score_date(tmp_path):
    store = JobStore(tmp_path / 'jobs.db')
    ids = []
    for index, (status, score, day) in enumerate([
        ('needs_review', 100, 1), ('eligible', 20, 3), ('eligible', 80, 2),
        ('eligible', 80, 1), ('ineligible', 100, 1)]):
        posting = job(title=str(index))
        store.upsert(posting)
        ids.append(posting.job_id)
        with store.connect() as db:
            db.execute('UPDATE jobs SET eligibility=?,total_score=?,discovered_at=? WHERE id=?',
                       (json.dumps({'status': status}), score, f'2026-01-0{day}', posting.job_id))
    assert [r['id'] for r in store.list_jobs()] == [ids[i] for i in (3, 2, 1, 0, 4)]
    assert [r['id'] for r in store.list_jobs(top=2)] == [ids[3], ids[2]]


def test_pending_top_and_threshold(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'data_folder'
    folder.mkdir()
    (folder / 'plain_text_resume.yaml').write_text('skills: [Python]')
    (folder / 'config.yaml').write_text('minimum_relevance_score: 90')
    store = JobStore(folder / 'output' / 'jobs.sqlite3')
    for title in ('Software Engineer', 'Unity Developer'):
        store.upsert(job(title=title))
    result = CliRunner().invoke(app.main, ['--mode', 'pending', '--top', '1'])
    assert result.exit_code == 0, result.output
    assert result.output.count('relevance:') == 1
    assert 'below advisory threshold' in result.output
    assert len(store.list_jobs()) == 2
    assert all(r['state'] == 'discovered' for r in store.list_jobs())


@pytest.mark.parametrize('value', [-1, 101, True, '50', float('nan')])
def test_threshold_validation(value):
    with pytest.raises(ValueError):
        validate_threshold(value)
