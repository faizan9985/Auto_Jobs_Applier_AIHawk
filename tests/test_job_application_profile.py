import pytest
from dataclasses import asdict
from datetime import date
from pathlib import Path

import yaml

from src.job_application_profile import JobApplicationProfile

@pytest.fixture
def valid_yaml():
    """Valid YAML string for initializing JobApplicationProfile."""
    return """
    self_identification:
      gender: Male
      pronouns: He/Him
      veteran: No
      disability: No
      ethnicity: Asian
    legal_authorization:
      eu_work_authorization: "Yes"
      us_work_authorization: "Yes"
      requires_us_visa: "No"
      requires_us_sponsorship: "Yes"
      requires_eu_visa: "No"
      legally_allowed_to_work_in_eu: "Yes"
      legally_allowed_to_work_in_us: "Yes"
      requires_eu_sponsorship: "No"
      canada_work_authorization: "Yes"
      requires_canada_visa: "No"
      legally_allowed_to_work_in_canada: "Yes"
      requires_canada_sponsorship: "No"
      uk_work_authorization: "Yes"
      requires_uk_visa: "No"
      legally_allowed_to_work_in_uk: "Yes"
      requires_uk_sponsorship: "No"
    work_preferences:
      remote_work: "Yes"
      in_person_work: "No"
      open_to_relocation: "Yes"
      willing_to_complete_assessments: "Yes"
      willing_to_undergo_drug_tests: "Yes"
      willing_to_undergo_background_checks: "Yes"
    availability:
      notice_period: "2 weeks"
    salary_expectations:
      salary_range_usd: "80000-120000"
    """

@pytest.fixture
def missing_field_yaml():
    """YAML string missing a required field (self_identification)."""
    return """
    legal_authorization:
      eu_work_authorization: "Yes"
      us_work_authorization: "Yes"
      requires_us_visa: "No"
      requires_us_sponsorship: "Yes"
      requires_eu_visa: "No"
      legally_allowed_to_work_in_eu: "Yes"
      legally_allowed_to_work_in_us: "Yes"
      requires_eu_sponsorship: "No"
      canada_work_authorization: "Yes"
      requires_canada_visa: "No"
      legally_allowed_to_work_in_canada: "Yes"
      requires_canada_sponsorship: "No"
      uk_work_authorization: "Yes"
      requires_uk_visa: "No"
      legally_allowed_to_work_in_uk: "Yes"
      requires_uk_sponsorship: "No"
    work_preferences:
      remote_work: "Yes"
      in_person_work: "No"
      open_to_relocation: "Yes"
      willing_to_complete_assessments: "Yes"
      willing_to_undergo_drug_tests: "Yes"
      willing_to_undergo_background_checks: "Yes"
    availability:
      notice_period: "2 weeks"
    salary_expectations:
      salary_range_usd: "80000-120000"
    """

@pytest.fixture
def invalid_type_yaml():
    """YAML string with an invalid type for a field."""
    return """
    self_identification:
      gender: Male
      pronouns: He/Him
      veteran: No
      disability: No
      ethnicity: Asian
    legal_authorization:
      eu_work_authorization: "Yes"
      us_work_authorization: "Yes"
      requires_us_visa: "No"
      requires_us_sponsorship: "Yes"
      requires_eu_visa: "No"
      legally_allowed_to_work_in_eu: "Yes"
      legally_allowed_to_work_in_us: "Yes"
      requires_eu_sponsorship: "No"
      canada_work_authorization: "Yes"
      requires_canada_visa: "No"
      legally_allowed_to_work_in_canada: "Yes"
      requires_canada_sponsorship: "No"
      uk_work_authorization: "Yes"
      requires_uk_visa: "No"
      legally_allowed_to_work_in_uk: "Yes"
      requires_uk_sponsorship: "No"
    work_preferences:
      remote_work: 12345  # Invalid type, expecting a string
      in_person_work: "No"
      open_to_relocation: "Yes"
      willing_to_complete_assessments: "Yes"
      willing_to_undergo_drug_tests: "Yes"
      willing_to_undergo_background_checks: "Yes"
    availability:
      notice_period: "2 weeks"
    salary_expectations:
      salary_range_usd: "80000-120000"
    """

def test_initialize_with_valid_yaml(valid_yaml):
    """Test initializing JobApplicationProfile with valid YAML."""
    profile = JobApplicationProfile(valid_yaml)

    # Check that the profile fields are correctly initialized
    assert profile.self_identification.gender == "Male"
    assert profile.self_identification.pronouns == "He/Him"
    assert profile.legal_authorization.eu_work_authorization == "Yes"
    assert profile.work_preferences.remote_work == "Yes"
    assert profile.availability.notice_period == "2 weeks"
    assert profile.salary_expectations.salary_range_usd == "80000-120000"

def test_initialize_with_missing_field(missing_field_yaml):
    """Test initializing JobApplicationProfile with missing required fields."""
    with pytest.raises(KeyError) as excinfo:
        JobApplicationProfile(missing_field_yaml)
    assert "self_identification" in str(excinfo.value)

def test_initialize_with_invalid_yaml():
    """Test initializing JobApplicationProfile with invalid YAML."""
    invalid_yaml_str = """
    self_identification:
      gender: Male
      pronouns: He/Him
      veteran: No
      disability: No
      ethnicity: Asian
    legal_authorization:
      eu_work_authorization: "Yes"
      us_work_authorization: "Yes"
      requires_us_visa: "No"
      requires_us_sponsorship: "Yes"
      requires_eu_visa: "No"
      legally_allowed_to_work_in_eu: "Yes"
      legally_allowed_to_work_in_us: "Yes"
      requires_eu_sponsorship: "No"
      canada_work_authorization: "Yes"
      requires_canada_visa: "No"
      legally_allowed_to_work_in_canada: "Yes"
      requires_canada_sponsorship: "No"
      uk_work_authorization: "Yes"
      requires_uk_visa: "No"
      legally_allowed_to_work_in_uk: "Yes"
      requires_uk_sponsorship: "No"
    work_preferences:
      remote_work: "Yes"
      in_person_work: "No"
    availability:
      notice_period: "2 weeks"
    salary_expectations:
      salary_range_usd: "80000-120000"
    """  # Missing fields in work_preferences

    with pytest.raises(TypeError):
        JobApplicationProfile(invalid_yaml_str)

def test_str_representation(valid_yaml):
    """Test the string representation of JobApplicationProfile."""
    profile = JobApplicationProfile(valid_yaml)
    profile_str = str(profile)

    assert "Self Identification:" in profile_str
    assert "Legal Authorization:" in profile_str
    assert "Work Preferences:" in profile_str
    assert "Availability:" in profile_str
    assert "Salary Expectations:" in profile_str
    assert "Male" in profile_str
    assert "80000-120000" in profile_str


def eligibility_yaml(valid_yaml, section):
    data = yaml.safe_load(valid_yaml)
    data["candidate_eligibility"] = section
    return yaml.safe_dump(data)


def test_complete_eligibility_profile(valid_yaml):
    facts = {
        "current_visa_status": "F-1",
        "graduation_date": "2030-05-15",
        "earliest_start_date": "2030-06-01",
        "opt_eligible": True,
        "stem_opt_eligible": False,
        "requires_future_h1b_sponsorship": True,
        "currently_authorized_to_work_in_us": False,
        "work_authorization_start_date": "2030-06-01",
        "work_authorization_end_date": "2031-05-31",
        "willing_to_relocate": False,
        "target_countries": ["United States", "Canada"],
        "is_us_citizen": False,
        "is_us_permanent_resident": False,
        "currently_enrolled": True,
        "returning_to_school_after_internship": False,
    }
    profile = JobApplicationProfile(eligibility_yaml(valid_yaml, facts))
    expected = {
        key: date.fromisoformat(value) if key.endswith("_date") else value
        for key, value in facts.items()
    }
    assert asdict(profile.candidate_eligibility) == expected
    # Storing facts must not change the text used by existing answer chains.
    assert str(profile) == str(JobApplicationProfile(valid_yaml))
    assert profile.legal_authorization.legally_allowed_to_work_in_us == "Yes"
    assert profile.work_preferences.open_to_relocation == "Yes"


@pytest.mark.parametrize("section", [None, {}, {"current_visa_status": "F-1"}])
def test_missing_optional_eligibility_fields(valid_yaml, section):
    facts = asdict(JobApplicationProfile(eligibility_yaml(valid_yaml, section)).candidate_eligibility)
    assert facts.pop("current_visa_status") == (section or {}).get("current_visa_status")
    assert all(value is None for value in facts.values())


def test_legacy_profile_without_eligibility(valid_yaml):
    assert all(value is None for value in asdict(JobApplicationProfile(valid_yaml).candidate_eligibility).values())


DATE_FIELDS = [
    "graduation_date", "earliest_start_date",
    "work_authorization_start_date", "work_authorization_end_date",
]


@pytest.mark.parametrize("field", DATE_FIELDS)
@pytest.mark.parametrize("value", ["2030-02-29", "2030-13-01", "05/15/2030", "2030-5-1", "", True, 20300515, "2030-05-15T00:00:00"])
def test_invalid_eligibility_dates(valid_yaml, field, value):
    with pytest.raises(ValueError, match=field):
        JobApplicationProfile(eligibility_yaml(valid_yaml, {field: value}))


@pytest.mark.parametrize("field", DATE_FIELDS)
@pytest.mark.parametrize("literal", ['"2032-02-29"', '2032-02-29'])
def test_quoted_and_unquoted_eligibility_dates(valid_yaml, field, literal):
    source = valid_yaml + f"\n    candidate_eligibility:\n      {field}: {literal}\n"
    assert getattr(JobApplicationProfile(source).candidate_eligibility, field) == date(2032, 2, 29)


@pytest.mark.parametrize("literal", ["2030-02-29", "2030-13-01", "2030-05-15T00:00:00Z"])
def test_invalid_unquoted_date_values(valid_yaml, literal):
    with pytest.raises(ValueError, match="date"):
        JobApplicationProfile(valid_yaml + f"\n    candidate_eligibility:\n      graduation_date: {literal}\n")


BOOLEAN_FIELDS = [
    "opt_eligible", "stem_opt_eligible", "requires_future_h1b_sponsorship",
    "currently_authorized_to_work_in_us", "willing_to_relocate",
]


@pytest.mark.parametrize("field", BOOLEAN_FIELDS)
@pytest.mark.parametrize("value", [True, False, None])
def test_eligibility_booleans(valid_yaml, field, value):
    profile = JobApplicationProfile(eligibility_yaml(valid_yaml, {field: value}))
    assert getattr(profile.candidate_eligibility, field) is value


@pytest.mark.parametrize("field", BOOLEAN_FIELDS)
@pytest.mark.parametrize("value", ["true", "false", "Yes", "No", 1, 0, [], {}])
def test_eligibility_booleans_reject_coercion(valid_yaml, field, value):
    with pytest.raises(TypeError, match=field):
        JobApplicationProfile(eligibility_yaml(valid_yaml, {field: value}))


@pytest.mark.parametrize("section", [False, [], "F-1"])
def test_eligibility_requires_mapping(valid_yaml, section):
    with pytest.raises(TypeError, match="candidate_eligibility"):
        JobApplicationProfile(eligibility_yaml(valid_yaml, section))


@pytest.mark.parametrize("countries", ["United States", [1], [None], [" "]])
def test_target_countries_requires_string_list(valid_yaml, countries):
    with pytest.raises(TypeError, match="target_countries"):
        JobApplicationProfile(eligibility_yaml(valid_yaml, {"target_countries": countries}))


def test_visa_status_requires_string(valid_yaml):
    with pytest.raises(TypeError, match="current_visa_status"):
        JobApplicationProfile(eligibility_yaml(valid_yaml, {"current_visa_status": True}))


def test_example_eligibility_placeholders_are_unspecified():
    example = Path(__file__).resolve().parents[1] / "data_folder_example" / "plain_text_resume.yaml"
    profile = JobApplicationProfile(example.read_text(encoding="utf-8"))
    assert all(value is None for value in asdict(profile.candidate_eligibility).values())
