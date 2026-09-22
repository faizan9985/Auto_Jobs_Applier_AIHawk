"""Deterministic selection of user-attested facts and local PDF rendering.

No generated text, skill inference, date arithmetic, or external resume builder.
Source YAML remains authoritative; selected leaves retain their source paths.
"""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape

import yaml
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from src.job_store import utc_now


VERSION = 'deterministic-v1'
STOPWORDS = {'the', 'and', 'with', 'for', 'from', 'that', 'this', 'using', 'will', 'our', 'you'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, (*path, index))
    elif value is not None and str(value).strip():
        yield {'source_path': list(path), 'value': value}


def tokens(text):
    return set(re.findall(r'[a-z0-9][a-z0-9+#.\-]*', str(text).lower())) - STOPWORDS


def select_facts(source, job, max_projects=3, max_bullets=4):
    """Return exact source leaves, ordered by overlap, plus omitted leaf paths."""
    target = tokens(job.title + ' ' + (job.description or ''))
    selected = []
    def rank(value):
        return len(tokens(' '.join(str(f['value']) for f in leaves(value))) & target)
    def add(value, path):
        selected.extend(f for f in leaves(value, path)
                        if not re.search(r'\[.*?\]', str(f['value'])))
    personal = source.get('personal_information') or {}
    for key in ('name', 'surname', 'city', 'country', 'email', 'phone_prefix', 'phone', 'linkedin', 'github'):
        if key in personal:
            add(personal[key], ('personal_information', key))
    for key in ('summary', 'professional_summary'):
        if key in source:
            add(source[key], (key,))
    for key in ('skills', 'technical_skills'):
        facts = list(leaves(source.get(key), (key,)))
        for fact in sorted(facts, key=lambda f: -rank(f['value'])):
            add(fact['value'], tuple(fact['source_path']))
    for index, entry in enumerate(source.get('experience_details') or []):
        base = ('experience_details', index)
        for key in ('position', 'company', 'employment_period', 'location', 'industry'):
            if key in entry:
                add(entry[key], (*base, key))
        bullets = entry.get('key_responsibilities') or []
        order = sorted(range(len(bullets)), key=lambda i: -rank(bullets[i]))
        for i in order[:max_bullets]:
            add(bullets[i], (*base, 'key_responsibilities', i))
        for key in ('skills_acquired', 'skills', 'technologies'):
            for fact in sorted(leaves(entry.get(key), (*base, key)), key=lambda f: -rank(f['value'])):
                add(fact['value'], tuple(fact['source_path']))
    projects = source.get('projects') or []
    for index in sorted(range(len(projects)), key=lambda i: -rank(projects[i]))[:max_projects]:
        add(projects[index], ('projects', index))
    for key in ('education_details', 'certifications', 'languages', 'achievements'):
        if key in source:
            add(source[key], (key,))
    # Validate each selected leaf against its original location, before rendering.
    for fact in selected:
        original = source
        for part in fact['source_path']:
            original = original[part]
        if original != fact['value']:
            raise ValueError('Selected fact differs from source')
    paths = {tuple(f['source_path']) for f in selected}
    omitted = [f['source_path'] for f in leaves(source) if tuple(f['source_path']) not in paths]
    skills = [str(f['value']) for f in selected if any(k in f['source_path'] for k in
              ('skills', 'technical_skills', 'skills_acquired', 'technologies'))]
    matched = sorted({s for s in skills if re.search(r'(?<![\w+#.])' + re.escape(s) + r'(?![\w+#])',
                                                    job.title + ' ' + (job.description or ''), re.I)})
    return dict(facts=selected, omitted=omitted, matched_skills=matched,
                matched_keywords=sorted(set().union(*(tokens(f['value']) for f in selected)) & target)
                if selected else [])


def render_pdf(selection, path):
    """Render source strings verbatim, escaping markup; layout never adds claims."""
    font_name = 'TailoredVera'
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf')))
    supported = pdfmetrics.getFont(font_name).face.charToGlyph
    for fact in selection['facts']:
        if any(ord(char) not in supported for char in str(fact['value']) if not char.isspace()):
            raise ValueError('Source contains characters unsupported by the resume font; no substitution is allowed')
    styles = getSampleStyleSheet()
    styles['BodyText'].fontName = styles['Heading2'].fontName = font_name
    story = []
    previous_group = None
    for fact in selection['facts']:
        parts = fact['source_path']
        group = tuple(parts[:2]) if len(parts) > 1 and isinstance(parts[1], int) else (parts[0],)
        if group != previous_group:
            story += [Spacer(1, 8)]
            if previous_group is None or group[0] != previous_group[0]:
                story.append(Paragraph(escape(str(parts[0]).replace('_', ' ').title()), styles['Heading2']))
            previous_group = group
        story.append(Paragraph(escape(str(fact['value'])).replace('\n', '<br/>'), styles['BodyText']))
    if not story:
        raise ValueError('No usable source resume facts; cannot generate a resume')
    SimpleDocTemplate(str(path), title='Resume', author='', pageCompression=1).build(story)


class ResumeTailor:
    def __init__(self, store, source_path, output_directory):
        self.store = store
        self.source_path = Path(source_path)
        self.output_directory = Path(output_directory)

    def prepare(self, job, regenerate=False):
        source = yaml.safe_load(self.source_path.read_text(encoding='utf-8'))
        if not isinstance(source, dict):
            raise ValueError('Resume source must be a YAML mapping')
        source_hash = digest(source)
        job_hash = digest({'title': job.title, 'description': job.description or ''})
        with self.store.connect() as db:
            cached = db.execute('''SELECT * FROM resume_tailorings WHERE job_id=? AND source_hash=?
                AND job_hash=? ORDER BY generated_at DESC, rowid DESC LIMIT 1''',
                (job.job_id, source_hash, job_hash)).fetchone()
        if cached and not regenerate:
            path = Path(cached['resume_path'])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != cached['pdf_hash']:
                raise ValueError('Cached resume is missing or modified; explicitly regenerate it')
            return dict(cached)
        selection = select_facts(source, job)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        record_id = str(uuid4())
        path = (self.output_directory / f'resume-{record_id}.pdf').resolve()
        render_pdf(selection, path)
        record = dict(id=record_id, job_id=job.job_id, source_hash=source_hash,
                      job_hash=job_hash, algorithm_version=VERSION, resume_path=str(path),
                      pdf_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
                      source_facts=canonical(source), selected_facts=canonical(selection['facts']),
                      matched_keywords=canonical(selection['matched_keywords']),
                      matched_skills=canonical(selection['matched_skills']),
                      selected_experience_bullets=canonical([f for f in selection['facts']
                                                            if 'key_responsibilities' in f['source_path']]),
                      selected_projects=canonical([f for f in selection['facts'] if f['source_path'][0] == 'projects']),
                      omitted_items=canonical(selection['omitted']), generated_at=utc_now(),
                      approval_status='pending')
        with self.store.connect() as db:
            db.execute('INSERT INTO resume_tailorings (' + ','.join(record) + ') VALUES (' +
                       ','.join('?' for _ in record) + ')', tuple(record.values()))
        return record
