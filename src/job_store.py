"""SQLite job inventory and authoritative application state (no browser I/O)."""

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from src.job import Job


STATES = {"discovered", "evaluated", "needs_review", "approved", "skipped",
          "deferred", "applying", "submitted", "failed"}
PENDING = ("discovered", "evaluated", "needs_review")
TRANSITIONS = {
    "discovered": {"evaluated", "needs_review", "skipped", "applying"},
    "evaluated": {"evaluated", "needs_review", "skipped", "applying"},
    "needs_review": {"evaluated", "needs_review", "skipped", "applying"},
    "applying": {"approved", "submitted", "skipped", "deferred", "failed"},
    "approved": {"submitted", "failed"},
    "failed": set(), "deferred": set(), "skipped": set(), "submitted": set(),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def identity(job):
    raw = job.link.strip()
    parts = urlsplit(raw if "://" in raw else "https://" + raw) if raw else None
    linkedin_id = job.linkedin_job_id
    host = (parts.hostname or "").lower() if parts else ""
    if parts and (host == "linkedin.com" or host.endswith(".linkedin.com")):
        match = re.search(r"/jobs/view/(?:[^/?]*-)?(\d+)(?:/|$)", parts.path)
        linkedin_id = linkedin_id or (match.group(1) if match else
                                      parse_qs(parts.query).get("currentJobId", [None])[0])
    if linkedin_id:
        normalized = f"https://www.linkedin.com/jobs/view/{linkedin_id}"
    elif parts:
        query = [(k, v) for k, v in parse_qsl(parts.query)
                 if not k.lower().startswith("utm_") and k.lower() not in
                 {"trk", "trackingid", "refid", "ref", "lipi"}]
        normalized = urlunsplit(("https", parts.netloc.lower(), parts.path.rstrip("/"),
                                urlencode(sorted(query)), ""))
    else:
        normalized = None
    composite = "|".join(" ".join(value.casefold().split())
                         for value in (job.company, job.title, job.location))
    fallback = hashlib.sha256(composite.encode()).hexdigest()
    return linkedin_id, normalized, fallback


class JobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] > 3:
                raise ValueError("Job database schema is newer than this application supports")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    linkedin_job_id TEXT UNIQUE,
                    normalized_url TEXT UNIQUE,
                    fallback_key TEXT UNIQUE,
                    company TEXT NOT NULL, title TEXT NOT NULL, location TEXT NOT NULL,
                    job_url TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    apply_method TEXT NOT NULL DEFAULT '', recruiter_link TEXT NOT NULL DEFAULT '',
                    discovered_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'linkedin',
                    eligibility TEXT,
                    state TEXT NOT NULL DEFAULT 'discovered' CHECK(state IN
                        ('discovered','evaluated','needs_review','approved','skipped',
                         'deferred','applying','submitted','failed')),
                    application_status TEXT, approval_status TEXT, approval TEXT,
                    resume_path TEXT NOT NULL DEFAULT '', cover_letter_path TEXT NOT NULL DEFAULT '',
                    application_answers TEXT NOT NULL DEFAULT '[]',
                    submitted_at TEXT, failure_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_state_idx ON jobs(state);
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    state TEXT NOT NULL, occurred_at TEXT NOT NULL, metadata TEXT NOT NULL
                );
            """)
            columns = {r['name'] for r in db.execute('PRAGMA table_info(jobs)')}
            for name in ('total_score', 'skill_score', 'role_score', 'project_score',
                         'experience_score', 'education_score', 'location_score'):
                if name not in columns:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {name} REAL')
            for name in ('matched_skills', 'missing_required_skills', 'matched_projects', 'reasons'):
                if name not in columns:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {name} TEXT')
            if 'skip_reason' not in columns:
                db.execute('ALTER TABLE jobs ADD COLUMN skip_reason TEXT')
            db.execute('PRAGMA user_version = 3')

    @contextmanager
    def connect(self):
        """Commit or roll back and always release the local connection."""
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def upsert(self, job):
        """Refresh discovery fields, preserving application state and nonempty descriptions."""
        linkedin_id, normalized, fallback = identity(job)
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = None
            for column, value in (("id", job.job_id), ("linkedin_job_id", linkedin_id),
                                  ("normalized_url", normalized), ("fallback_key", fallback)):
                if value:
                    row = db.execute(f"SELECT * FROM jobs WHERE {column} = ?", (value,)).fetchone()
                    if row:
                        break
            if row is None and normalized is None:
                # A later tile can temporarily omit its URL. Reuse a single
                # unambiguous composite match, but never merge distinct IDs.
                matches = []
                for candidate in db.execute("SELECT * FROM jobs"):
                    probe = Job(candidate['title'], candidate['company'], candidate['location'], '', '')
                    if identity(probe)[2] == fallback:
                        matches.append(candidate)
                if len(matches) == 1:
                    row = matches[0]
            if row:
                job.job_id = row["id"]
                description = job.description or row["description"]
                db.execute("""UPDATE jobs SET linkedin_job_id=COALESCE(?,linkedin_job_id),
                    normalized_url=COALESCE(?,normalized_url),
                    fallback_key=CASE WHEN ? IS NOT NULL THEN NULL ELSE fallback_key END,
                    company=?,title=?,location=?,job_url=?,description=?,apply_method=?,
                    last_seen_at=? WHERE id=?""",
                    (linkedin_id, normalized, normalized, job.company, job.title, job.location,
                     job.link or row["job_url"], description, job.apply_method, now, job.job_id))
            else:
                job.job_id = str(uuid4())
                db.execute("""INSERT INTO jobs
                    (id,linkedin_job_id,normalized_url,fallback_key,company,title,location,job_url,
                     description,apply_method,discovered_at,last_seen_at,source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (job.job_id, linkedin_id, normalized, None if normalized else fallback,
                     job.company, job.title, job.location, job.link, job.description or "",
                     job.apply_method, now, now, job.source))
                self._event(db, job.job_id, "discovered", {})
        return self.get(job.job_id)

    @staticmethod
    def _event(db, job_id, state, metadata):
        db.execute("INSERT INTO job_events(job_id,state,occurred_at,metadata) VALUES (?,?,?,?)",
                   (job_id, state, utc_now(), json.dumps(metadata)))

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def list_jobs(self, states=PENDING, job_ids=(), top=None):
        if not states:
            return []
        query = "SELECT * FROM jobs WHERE state IN (" + ",".join("?" for _ in states) + ")"
        params = list(states)
        if job_ids:
            query += " AND id IN (" + ",".join("?" for _ in job_ids) + ")"
            params.extend(job_ids)
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(query, params)]
        def priority(row):
            status = (json.loads(row['eligibility'] or 'null') or {}).get('status')
            return ({'eligible': 0, 'needs_review': 1, 'ineligible': 3}.get(status, 2),
                    -(row['total_score'] if row['total_score'] is not None else -1),
                    row['discovered_at'], row['id'])
        return sorted(rows, key=priority)[:top]

    def score(self, job, resume):
        """Persist relevance only, preserving eligibility, state and approval."""
        from src.job_relevance import score_job
        result = score_job(job, resume)
        values = {k: json.dumps(v) if isinstance(v, list) else v for k, v in result.items()}
        with self.connect() as db:
            cursor = db.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE id=?',
                                (*values.values(), job.job_id))
            if not cursor.rowcount:
                raise KeyError(job.job_id)
        return result

    def rescore(self, resume, states=PENDING, job_ids=()):
        for row in self.list_jobs(states, job_ids):
            self.score(self.to_job(row), resume)

    @staticmethod
    def to_job(row):
        return Job(title=row["title"], company=row["company"], location=row["location"],
                   link=row["job_url"], apply_method=row["apply_method"], description=row["description"],
                   recruiter_link=row["recruiter_link"], pdf_path=row["resume_path"],
                   cover_letter_path=row["cover_letter_path"], job_id=row["id"],
                   linkedin_job_id=row["linkedin_job_id"], source=row["source"],
                   eligibility=json.loads(row["eligibility"]) if row["eligibility"] else None,
                   application_status=row["application_status"],
                   approval=json.loads(row["approval"]) if row["approval"] else None,
                   application_answers=json.loads(row["application_answers"]))

    def evaluate(self, job):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job.job_id,)).fetchone()
            state = row["state"]
            if state in PENDING:
                state = "evaluated" if job.eligibility["status"] == "eligible" else "needs_review"
            db.execute("UPDATE jobs SET eligibility=?,description=?,state=? WHERE id=?",
                       (json.dumps(job.eligibility), job.description or "", state, job.job_id))
            self._event(db, job.job_id, state, {"eligibility": job.eligibility})

    def skip_ineligible(self, job_id, expected_state):
        """Atomically gate a selected job without claiming it or replacing evidence.

        Retry states are accepted only when explicitly selected by the caller.
        This narrow transition cannot skip submitted jobs or non-ineligible jobs.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            eligibility = json.loads(row['eligibility'] or 'null') or {}
            if (row['state'] != expected_state or row['state'] not in
                    (*PENDING, 'failed', 'deferred', 'applying', 'approved') or
                    eligibility.get('status') != 'ineligible'):
                raise ValueError('Job state or eligibility changed before gating')
            db.execute("""UPDATE jobs SET state='skipped', application_status='skipped',
                          skip_reason='ineligible', failure_reason=NULL WHERE id=?""", (job_id,))
            self._event(db, job_id, 'skipped', {'skip_reason': 'ineligible',
                                              'eligibility': eligibility,
                                              'application_status': 'skipped'})

    def transition(self, job, state, failure_reason=None, retry=False, expected_state=None):
        if state not in STATES:
            raise ValueError(f"Unknown job state: {state}")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job.job_id,)).fetchone()
            if row is None:
                raise KeyError(job.job_id)
            old = row["state"]
            if expected_state is not None and old != expected_state:
                raise ValueError(f"Job state changed: expected {expected_state}, found {old}")
            intentional_retry = retry and state == "applying" and old in {"failed", "deferred", "applying", "approved"}
            if state not in TRANSITIONS[old] and not intentional_retry:
                raise ValueError(f"Invalid job transition: {old} -> {state}")
            approval = job.approval
            db.execute("""UPDATE jobs SET state=?, application_status=?, approval_status=?,approval=?,
                resume_path=?,cover_letter_path=?,application_answers=?,recruiter_link=?,
                eligibility=?,description=?,submitted_at=CASE WHEN ?='submitted' THEN ? ELSE submitted_at END,
                failure_reason=? WHERE id=?""",
                (state, job.application_status or state, approval.get("decision") if approval else None,
                 json.dumps(approval) if approval else None, job.pdf_path, job.cover_letter_path,
                 json.dumps(job.application_answers), job.recruiter_link, json.dumps(job.eligibility), job.description or "",
                 state, utc_now(), failure_reason, job.job_id))
            self._event(db, job.job_id, state, {"approval": approval, "failure_reason": failure_reason,
                                               "application_status": job.application_status})

    def has_submitted_company(self, company):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM jobs WHERE state='submitted' AND lower(trim(company))=?",
                              (company.strip().lower(),)).fetchone() is not None

    def import_json(self, directory):
        """Explicit, repeatable import; historical submissions take precedence."""
        count = 0
        for filename, state in (("success", "submitted"), ("failed", "failed"),
                                ("skipped_by_user", "skipped"), ("skipped", "skipped"),
                                ("deferred_for_review", "deferred"), ("aborted", "deferred"),
                                ("data", "discovered")):
            path = Path(directory) / f"{filename}.json"
            if not path.exists():
                continue
            for record in json.loads(path.read_text(encoding="utf-8")):
                job = Job(record.get("job_title", ""), record.get("company", ""),
                          record.get("job_location", ""), record.get("link", ""),
                          record.get("apply_method", ""), description=record.get("description", ""),
                          source="legacy_json")
                row = self.upsert(job)
                # Never let an old JSON log roll back newer SQLite state.
                if row["state"] != "discovered":
                    continue
                job.eligibility = record.get("eligibility")
                job.approval = record.get("approval")
                job.pdf_path = record.get("pdf_path", "")
                job.cover_letter_path = record.get("cover_letter_path", "")
                job.application_answers = record.get("application_answers", [])
                with self.connect() as db:
                    db.execute("""UPDATE jobs SET state=?, application_status=?, eligibility=?,
                        approval=?,approval_status=?,resume_path=?,cover_letter_path=?,application_answers=?,
                        submitted_at=?,failure_reason=? WHERE id=?""",
                        (state, record.get("application_status", state), json.dumps(job.eligibility),
                         json.dumps(job.approval), job.approval.get("decision") if job.approval else None,
                         job.pdf_path, job.cover_letter_path, json.dumps(job.application_answers),
                         record.get("submitted_at"), record.get("failure_reason"), job.job_id))
                    self._event(db, job.job_id, state, {"imported_from": str(path)})
                count += 1
        return count
