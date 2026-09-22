"""Offline regression tests: real answer chains, with provider responses stubbed."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import strings
from src.aihawk_easy_applier import AIHawkEasyApplier
from src.llm.llm_manager import GPTAnswerer


def make_answerer(*responses):
    answerer = GPTAnswerer.__new__(GPTAnswerer)
    answerer.resume = SimpleNamespace(
        education_details="BS Computer Science",
        experience_details="3 years of Python experience; 0 years of Java experience",
        projects="Unity project, duration not specified",
    )
    answerer.job_application_profile = "Requires future US sponsorship: Yes"
    prompts = []
    replies = iter(responses)

    def provider(prompt):
        prompts.append(prompt.to_string())
        return next(replies)

    answerer.llm_cheap = provider
    return answerer, prompts


@pytest.mark.parametrize("reply", ["0", "3", "1.5", " 0.5 "])
def test_numeric_preserves_supported_numbers_including_zero(reply):
    answerer, prompts = make_answerer(reply)
    answerer.resume.experience_details = f"{reply.strip()} years of Python experience"
    assert answerer.answer_question_numeric("Years of Python?") == reply.strip()
    assert answerer.resume.experience_details in prompts[0]
    assert answerer.resume.projects in prompts[0]


@pytest.mark.parametrize("reply", [
    "UNKNOWN", "", "Probably 3", "2-3", "-1", "No evidence; perhaps 2 years",
    "Graduated in 2023", "NaN", "Infinity", "3 years",
])
def test_unknown_or_malformed_experience_does_not_fabricate_number(reply):
    answerer, _ = make_answerer(reply)
    assert answerer.answer_question_numeric("Years of Java?") == "0"


def test_unknown_skill_prompt_does_not_transfer_related_experience():
    answerer, prompts = make_answerer("UNKNOWN")
    assert answerer.answer_question_numeric("Years of C++?") == "0"
    assert "Years of C++?" in prompts[0]
    assert "Do not infer skills or durations" in prompts[0]
    assert "return UNKNOWN" in prompts[0]
    assert "3 years of Python" in prompts[0]


@pytest.mark.parametrize("reply", ["0 years", "None", "No", "3 years"])
def test_supported_options_including_negative_answers_are_preserved(reply):
    answerer, prompts = make_answerer(reply)
    options = ["Select an option", "None", "No", "0 years", "3 years"]
    assert answerer.answer_question_from_options("Experience?", options) == reply
    assert answerer.job_application_profile in prompts[0]


@pytest.mark.parametrize("reply", ["UNKNOWN", "Perhaps 3 years", "2 years"])
def test_unsupported_option_is_not_fuzzy_matched_to_positive_claim(reply):
    answerer, _ = make_answerer(reply)
    with pytest.raises(ValueError, match="No supported answer"):
        answerer.answer_question_from_options("Years of Java?", ["1 year", "3 years"])


@pytest.mark.parametrize("section", [
    "education_details", "experience_details", "projects", "certifications", "languages",
])
def test_textual_experience_uses_candidate_evidence_and_no_inference(section):
    answerer, prompts = make_answerer(
        section.replace("_", " "), "Unknown from the provided candidate data."
    )
    setattr(answerer.resume, section, "No verified Java experience recorded")
    assert answerer.answer_question_textual_wide_range("Years of Java?") == (
        "Unknown from the provided candidate data."
    )
    assert "No verified Java experience recorded" in prompts[1]
    assert "Do not invent or inflate" in prompts[1]
    assert "answer as if you have the experience" not in prompts[1]


def test_known_textual_experience_is_preserved():
    answerer, _ = make_answerer("Experience Details", "3 years of Python experience")
    assert answerer.answer_question_textual_wide_range("Years of Python?") == (
        "3 years of Python experience"
    )


def test_old_cached_claims_are_ignored_without_deleting_them(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old_answer = {"type": "numeric", "question": "years of java?", "answer": "3"}
    cache = tmp_path / "answers.json"
    cache.write_text(json.dumps([old_answer]))
    applier = AIHawkEasyApplier.__new__(AIHawkEasyApplier)
    assert applier._load_questions_from_json() == []
    applier._save_questions_to_json({
        "type": "numeric", "question": "years of java?", "answer": "0",
    })
    assert [item["answer"] for item in applier._load_questions_from_json()] == ["0"]
    assert json.loads(cache.read_text())[0] == old_answer


def test_prompts_do_not_require_unsupported_positive_claims():
    assert '"0" is absolutely forbidden' not in strings.numeric_question_template
    assert "Do not guess" in strings.numeric_question_template
    assert "return UNKNOWN" in strings.options_template
    assert "3 years of leadership experience" not in strings.experience_details_template
    assert "Never change candidate facts" in strings.try_to_fix_template


def test_radio_selection_does_not_match_a_larger_experience_number():
    applier = AIHawkEasyApplier.__new__(AIHawkEasyApplier)
    radios = [Mock(text="13 years"), Mock(text="3 years")]
    applier._select_radio(radios, "3 years")
    radios[0].find_element.assert_not_called()
    radios[1].find_element.return_value.click.assert_called_once()


def test_unknown_radio_answer_does_not_default_to_last_option():
    applier = AIHawkEasyApplier.__new__(AIHawkEasyApplier)
    radios = [Mock(text="1 year"), Mock(text="3 years")]
    with pytest.raises(ValueError, match="No radio option"):
        applier._select_radio(radios, "UNKNOWN")
    for radio in radios:
        radio.find_element.assert_not_called()
