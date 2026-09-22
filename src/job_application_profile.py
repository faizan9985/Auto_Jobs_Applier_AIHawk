from dataclasses import dataclass
from datetime import date
import re
from typing import List, Optional

import yaml

from loguru import logger


@dataclass
class SelfIdentification:
    gender: str
    pronouns: str
    veteran: str
    disability: str
    ethnicity: str


@dataclass
class LegalAuthorization:
    eu_work_authorization: str
    us_work_authorization: str
    requires_us_visa: str
    legally_allowed_to_work_in_us: str
    requires_us_sponsorship: str
    requires_eu_visa: str
    legally_allowed_to_work_in_eu: str
    requires_eu_sponsorship: str
    canada_work_authorization: str
    requires_canada_visa: str
    legally_allowed_to_work_in_canada: str
    requires_canada_sponsorship: str
    uk_work_authorization: str
    requires_uk_visa: str 
    legally_allowed_to_work_in_uk: str
    requires_uk_sponsorship: str



@dataclass
class WorkPreferences:
    remote_work: str
    in_person_work: str
    open_to_relocation: str
    willing_to_complete_assessments: str
    willing_to_undergo_drug_tests: str
    willing_to_undergo_background_checks: str


@dataclass
class Availability:
    notice_period: str


@dataclass
class SalaryExpectations:
    salary_range_usd: str


@dataclass
class CandidateEligibility:
    """Optional, user-provided facts; None means unspecified, never ineligible.

    These facts are stored for future screening and do not drive application
    answers or filtering. No values are derived from other profile sections.
    """

    current_visa_status: Optional[str] = None
    graduation_date: Optional[date] = None
    earliest_start_date: Optional[date] = None
    opt_eligible: Optional[bool] = None
    stem_opt_eligible: Optional[bool] = None
    requires_future_h1b_sponsorship: Optional[bool] = None
    currently_authorized_to_work_in_us: Optional[bool] = None
    work_authorization_start_date: Optional[date] = None
    work_authorization_end_date: Optional[date] = None
    willing_to_relocate: Optional[bool] = None
    target_countries: Optional[List[str]] = None

    def __post_init__(self):
        for name in (
            "graduation_date", "earliest_start_date",
            "work_authorization_start_date", "work_authorization_end_date",
        ):
            value = getattr(self, name)
            if value is None or type(value) is date:
                continue
            if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                try:
                    setattr(self, name, date.fromisoformat(value))
                    continue
                except ValueError:
                    pass
            raise ValueError(f"candidate_eligibility.{name} must be a valid YYYY-MM-DD date or null.")

        for name in (
            "opt_eligible", "stem_opt_eligible", "requires_future_h1b_sponsorship",
            "currently_authorized_to_work_in_us", "willing_to_relocate",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"candidate_eligibility.{name} must be a YAML boolean or null.")

        if self.current_visa_status is not None and not isinstance(self.current_visa_status, str):
            raise TypeError("candidate_eligibility.current_visa_status must be a string or null.")
        if self.target_countries is not None and (
            not isinstance(self.target_countries, list)
            or any(not isinstance(country, str) or not country.strip() for country in self.target_countries)
        ):
            raise TypeError("candidate_eligibility.target_countries must be a list of nonempty strings or null.")


@dataclass
class JobApplicationProfile:
    self_identification: SelfIdentification
    legal_authorization: LegalAuthorization
    work_preferences: WorkPreferences
    availability: Availability
    salary_expectations: SalaryExpectations
    candidate_eligibility: CandidateEligibility

    def __init__(self, yaml_str: str):
        logger.debug("Initializing JobApplicationProfile with provided YAML string")
        try:
            data = yaml.safe_load(yaml_str)
            logger.debug(f"YAML data successfully parsed: {data}")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file: {e}")
            raise ValueError("Error parsing YAML file.") from e
        except ValueError as e:
            # PyYAML validates unquoted ISO dates while constructing values.
            raise ValueError(f"Invalid YAML value (check date fields for valid YYYY-MM-DD dates): {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error occurred while parsing the YAML file: {e}")
            raise RuntimeError("An unexpected error occurred while parsing the YAML file.") from e

        if not isinstance(data, dict):
            logger.error(f"YAML data must be a dictionary, received: {type(data)}")
            raise TypeError("YAML data must be a dictionary.")

        # Process self_identification
        try:
            logger.debug("Processing self_identification")
            self.self_identification = SelfIdentification(**data['self_identification'])
            logger.debug(f"self_identification processed: {self.self_identification}")
        except KeyError as e:
            logger.error(f"Required field {e} is missing in self_identification data.")
            raise KeyError(f"Required field {e} is missing in self_identification data.") from e
        except TypeError as e:
            logger.error(f"Error in self_identification data: {e}")
            raise TypeError(f"Error in self_identification data: {e}") from e
        except AttributeError as e:
            logger.error(f"Attribute error in self_identification processing: {e}")
            raise AttributeError("Attribute error in self_identification processing.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing self_identification: {e}")
            raise RuntimeError("An unexpected error occurred while processing self_identification.") from e

        # Process legal_authorization
        try:
            logger.debug("Processing legal_authorization")
            self.legal_authorization = LegalAuthorization(**data['legal_authorization'])
            logger.debug(f"legal_authorization processed: {self.legal_authorization}")
        except KeyError as e:
            logger.error(f"Required field {e} is missing in legal_authorization data.")
            raise KeyError(f"Required field {e} is missing in legal_authorization data.") from e
        except TypeError as e:
            logger.error(f"Error in legal_authorization data: {e}")
            raise TypeError(f"Error in legal_authorization data: {e}") from e
        except AttributeError as e:
            logger.error(f"Attribute error in legal_authorization processing: {e}")
            raise AttributeError("Attribute error in legal_authorization processing.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing legal_authorization: {e}")
            raise RuntimeError("An unexpected error occurred while processing legal_authorization.") from e

        # Process work_preferences
        try:
            logger.debug("Processing work_preferences")
            self.work_preferences = WorkPreferences(**data['work_preferences'])
            logger.debug(f"Work_preferences processed: {self.work_preferences}")
        except KeyError as e:
            logger.error(f"Required field {e} is missing in work_preferences data.")
            raise KeyError(f"Required field {e} is missing in work_preferences data.") from e
        except TypeError as e:
            logger.error(f"Error in work_preferences data: {e}")
            raise TypeError(f"Error in work_preferences data: {e}") from e
        except AttributeError as e:
            logger.error(f"Attribute error in work_preferences processing: {e}")
            raise AttributeError("Attribute error in work_preferences processing.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing work_preferences: {e}")
            raise RuntimeError("An unexpected error occurred while processing work_preferences.") from e

        # Process availability
        try:
            logger.debug("Processing availability")
            self.availability = Availability(**data['availability'])
            logger.debug(f"Availability processed: {self.availability}")
        except KeyError as e:
            logger.error(f"Required field {e} is missing in availability data.")
            raise KeyError(f"Required field {e} is missing in availability data.") from e
        except TypeError as e:
            logger.error(f"Error in availability data: {e}")
            raise TypeError(f"Error in availability data: {e}") from e
        except AttributeError as e:
            logger.error(f"Attribute error in availability processing: {e}")
            raise AttributeError("Attribute error in availability processing.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing availability: {e}")
            raise RuntimeError("An unexpected error occurred while processing availability.") from e

        # Process salary_expectations
        try:
            logger.debug("Processing salary_expectations")
            self.salary_expectations = SalaryExpectations(**data['salary_expectations'])
            logger.debug(f"salary_expectations processed: {self.salary_expectations}")
        except KeyError as e:
            logger.error(f"Required field {e} is missing in salary_expectations data.")
            raise KeyError(f"Required field {e} is missing in salary_expectations data.") from e
        except TypeError as e:
            logger.error(f"Error in salary_expectations data: {e}")
            raise TypeError(f"Error in salary_expectations data: {e}") from e
        except AttributeError as e:
            logger.error(f"Attribute error in salary_expectations processing: {e}")
            raise AttributeError("Attribute error in salary_expectations processing.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing salary_expectations: {e}")
            raise RuntimeError("An unexpected error occurred while processing salary_expectations.") from e

        eligibility = data.get('candidate_eligibility')
        if eligibility is None:
            eligibility = {}
        if not isinstance(eligibility, dict):
            raise TypeError("candidate_eligibility must be a mapping or null.")
        self.candidate_eligibility = CandidateEligibility(**eligibility)

        logger.debug("JobApplicationProfile initialization completed successfully.")

    def __str__(self):
        logger.debug("Generating string representation of JobApplicationProfile")

        def format_dataclass(obj):
            return "\n".join(f"{field.name}: {getattr(obj, field.name)}" for field in obj.__dataclass_fields__.values())

        formatted_str = (f"Self Identification:\n{format_dataclass(self.self_identification)}\n\n"
                         f"Legal Authorization:\n{format_dataclass(self.legal_authorization)}\n\n"
                         f"Work Preferences:\n{format_dataclass(self.work_preferences)}\n\n"
                         f"Availability: {self.availability.notice_period}\n\n"
                         f"Salary Expectations: {self.salary_expectations.salary_range_usd}\n\n")
        logger.debug(f"String representation generated: {formatted_str}")
        return formatted_str
