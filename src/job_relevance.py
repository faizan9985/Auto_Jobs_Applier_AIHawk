"""Deterministic evidence-based ranking. Never makes eligibility decisions.

Resume YAML is user-attested evidence, not independently verified. Only explicit
skill lists establish skills; projects/titles never imply additional skills.
"""
import re


WEIGHTS = dict(required=35, preferred=10, role=15, project=15,
               experience=10, education=10, location=5)
ALIASES = {
    "javascript": ("javascript", "js"), "typescript": ("typescript", "ts"),
    "react": ("react", "react.js", "reactjs"),
    "node.js": ("node.js", "nodejs"), "c#": ("c#", "c sharp"),
    "c++": ("c++",), "python": ("python",), "java": ("java",),
    "unity": ("unity", "unity3d"), "unreal engine": ("unreal engine", "unreal"),
    **{s: (s,) for s in ("sql", "html", "css", "git", "docker", "aws", "azure",
                        "opengl", "vulkan", "hlsl", "glsl", "blender", "webgl",
                        "three.js", "c", "rust", "go", "kubernetes")},
}
FAMILIES = {
    "software": ("software engineer", "software developer", "software engineering"),
    "frontend": ("frontend", "front-end", "front end"),
    "fullstack": ("full-stack", "full stack", "fullstack"),
    "xr": ("xr", "ar", "vr", "augmented reality", "virtual reality", "mixed reality"),
    "unity": ("unity", "unity3d"),
    "graphics": ("graphics", "3d", "rendering"),
    "simulation": ("simulation", "visualization", "visualisation"),
    "digital_twin": ("digital twin",),
    "new_grad": ("new grad", "new-grad", "new graduate", "graduate software"),
    "post_grad_intern": ("post-graduate", "postgraduate", "post graduate", "graduate intern"),
}


def contains(text, phrase):
    return bool(re.search(r"(?<![\w+#.])" + re.escape(phrase) + r"(?![\w+#])", text, re.I))


def clean(value):
    return value.strip() if isinstance(value, str) and not re.search(r"\[.*?\]", value) else ""


def families(text):
    return {key for key, names in FAMILIES.items() if any(contains(text, n) for n in names)}


def skill_list(value):
    if isinstance(value, dict):
        return [s for group in value.values() for s in skill_list(group)]
    if isinstance(value, list):
        return [clean(s) for s in value if clean(s)]
    return []


def validate_threshold(value):
    if type(value) not in (int, float) or not 0 <= value <= 100:
        raise ValueError("minimum_relevance_score must be a number from 0 to 100")
    return value


def score_job(job, resume):
    """Return weighted points (0–100) and evidence, using no clock or network.

    Unknown evidence earns zero. Unlabelled skill mentions are treated as required
    conservatively. The finite vocabulary is extended by explicit candidate skills.
    """
    resume = resume or {}
    experience = resume.get("experience_details") or []
    projects = resume.get("projects") or []
    education = resume.get("education_details") or []
    explicit = skill_list(resume.get("skills")) + skill_list(resume.get("technical_skills"))
    for item in experience + projects:
        for key in ("skills_acquired", "skills", "technologies"):
            explicit += skill_list(item.get(key))
    vocabulary = dict(ALIASES)
    candidate = set()
    for skill in explicit:
        canonical = next((k for k, names in ALIASES.items() if skill.casefold() in names), skill.casefold())
        vocabulary.setdefault(canonical, (canonical,))
        candidate.add(canonical)
    required, preferred = set(), set()
    section = "required"
    for line in re.split(r"[\n;]|(?<=[.!?])\s+(?=[A-Z])", job.description or ""):
        if re.search(r"preferred|nice.to.have|bonus|desirable", line, re.I):
            section = "preferred"
        elif re.search(r"required|requirements|must.have|minimum|basic qualifications", line, re.I):
            section = "required"
        elif re.search(r"responsibilities|about us|benefits", line, re.I):
            section = "required"
        found = {k for k, names in vocabulary.items() if any(contains(line, n) for n in names)}
        (preferred if section == "preferred" else required).update(found)
    preferred -= required
    def points(matches, targets, weight):
        return weight * len(matches & targets) / len(targets) if targets else 0
    required_points = points(candidate, required, WEIGHTS['required'])
    preferred_points = points(candidate, preferred, WEIGHTS['preferred'])
    title_families = families(job.title)
    candidate_titles = " ".join(clean(e.get("position")) for e in experience)
    project_texts = [(clean(p.get("name")), clean(p.get("description"))) for p in projects]
    candidate_domains = families(candidate_titles + " " + " ".join(explicit) + " " +
                                 " ".join(text for _, text in project_texts))
    role = points(candidate_domains, title_families, WEIGHTS['role'])
    job_domains = families(job.title + " " + (job.description or ""))
    matched_projects = [name for name, text in project_texts if name and
                        (families(text) & job_domains or
                         any(contains(text, alias) for s in candidate & (required | preferred)
                             for alias in vocabulary[s]))]
    project = WEIGHTS['project'] if matched_projects else 0
    # Explicit years only: project duration and education never become employment years.
    years = resume.get("professional_experience_years")
    demands = re.findall(r"(\d+)\+?\s*(?:years|yrs)\b", job.description or "", re.I)
    experience_score = 0
    if demands and type(years) in (int, float) and years >= 0:
        experience_score = WEIGHTS['experience'] * min(1, years / max(1, max(map(int, demands))))
    elif not demands:
        levels = ("senior", "junior", "entry", "intern", "lead", "principal")
        matching_levels = [level for level in levels if contains(job.title, level)]
        if matching_levels and any(contains(candidate_titles, level) for level in matching_levels):
            experience_score = WEIGHTS['experience']
    text = job.title + " " + (job.description or "")
    degree_patterns = {"bachelor": r"bachelor|b\.s\.|bsc", "master": r"master|m\.s\.|msc",
                       "doctor": r"ph\.?d|doctor"}
    degree_matches = [key for key, pattern in degree_patterns.items() if re.search(pattern, text, re.I)]
    degree_text = " ".join(clean(e.get("education_level")) for e in education)
    degree = 5 if degree_matches and any(re.search(degree_patterns[k], degree_text, re.I)
                                         for k in degree_matches) else 0
    grad_years = re.findall(r"(?:graduat\w*|class of)[^\n.]{0,40}?\b(20\d{2})\b", text, re.I)
    candidate_years = {str(e.get("year_of_completion", "")) for e in education}
    graduation = str((resume.get("candidate_eligibility") or {}).get("graduation_date", ""))[:4]
    if graduation:
        candidate_years.add(graduation)
    grad = 5 if set(grad_years) & candidate_years else 0
    prefs = resume.get("work_preferences") or {}
    city = clean((resume.get("personal_information") or {}).get("city"))
    yes = lambda value: value is True or (isinstance(value, str) and value.casefold() == "yes")
    remote = contains(job.location, "remote")
    location = WEIGHTS['location'] if ((remote and yes(prefs.get("remote_work"))) or
        (not remote and yes(prefs.get("in_person_work")) and city and contains(job.location, city))) else 0
    result = dict(skill_score=round(required_points + preferred_points, 2), role_score=round(role, 2),
                  project_score=project, experience_score=round(experience_score, 2),
                  education_score=degree + grad, location_score=location)
    result['total_score'] = round(sum(result.values()), 2)
    result.update(matched_skills=sorted(candidate & (required | preferred)),
                  missing_required_skills=sorted(required - candidate), matched_projects=matched_projects,
                  reasons=[f"Required skills: {required_points:.2f}/35; preferred: {preferred_points:.2f}/10",
                           f"Role/domain matches: {', '.join(sorted(candidate_domains & title_families)) or 'none'}",
                           f"Projects: {len(matched_projects)}; experience: {experience_score:.2f}/10",
                           f"Education degree: {degree}/5; graduation: {grad}/5; location: {location}/5",
                           "Unknown evidence earns zero; no eligibility decision is made."])
    if not required and not preferred:
        result['reasons'].append("No recognized skill requirements; skill coverage is unknown.")
    return result
