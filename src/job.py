from dataclasses import asdict, dataclass, field
from typing import Optional

from src.job_application_profile import CandidateEligibility
from src.job_eligibility import EligibilityResult, JobEligibilityEvaluator

from loguru import logger


@dataclass
class Job:
    title: str
    company: str
    location: str
    link: str
    apply_method: str
    description: str = ""
    summarize_job_description: str = ""
    pdf_path: str = ""
    recruiter_link: str = ""
    eligibility: Optional[dict] = None
    cover_letter_path: str = ""
    application_status: Optional[str] = None
    approval: Optional[dict] = None
    application_answers: list = field(default_factory=list)
    job_id: Optional[str] = None
    linkedin_job_id: Optional[str] = None
    source: str = "linkedin"
    tailoring_id: Optional[str] = None
    tailored_resume_path: str = ""
    tailored_resume_hash: str = ""

    def evaluate_eligibility(self, candidate_eligibility=None):
        """Attach advisory metadata only; never decide whether to apply."""
        reasons = []
        if not isinstance(self.description, str) or not self.description.strip():
            reasons.append("Job description is unavailable.")
        if not isinstance(candidate_eligibility, CandidateEligibility):
            reasons.append("Candidate eligibility profile is unavailable.")
        result = (EligibilityResult(reasons=reasons) if reasons else
                  JobEligibilityEvaluator().evaluate(self.description, candidate_eligibility))
        self.eligibility = asdict(result)
        return self.eligibility

    def set_summarize_job_description(self, summarize_job_description):
        logger.debug(f"Setting summarized job description: {summarize_job_description}")
        self.summarize_job_description = summarize_job_description

    def set_job_description(self, description):
        logger.debug(f"Setting job description: {description}")
        self.description = description

    def set_recruiter_link(self, recruiter_link):
        logger.debug(f"Setting recruiter link: {recruiter_link}")
        self.recruiter_link = recruiter_link

    def formatted_job_information(self):
        """
        Formats the job information as a markdown string.
        """
        logger.debug(f"Formatting job information for job: {self.title} at {self.company}")
        job_information = f"""
        # Job Description
        ## Job Information 
        - Position: {self.title}
        - At: {self.company}
        - Location: {self.location}
        - Recruiter Profile: {self.recruiter_link or 'Not available'}
        
        ## Description
        {self.description or 'No description provided.'}
        """
        formatted_information = job_information.strip()
        logger.debug(f"Formatted job information: {formatted_information}")
        return formatted_information
