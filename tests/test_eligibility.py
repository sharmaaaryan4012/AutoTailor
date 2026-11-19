import pytest
from src.filtering.eligibility import check_title_ineligibility, evaluate_eligibility, explain_eligibility, is_us_location

def test_experienced_and_research_titles_rejected():
    disallowed_titles = [
        "Applied Scientist II - AMZ10564086",
        "AI Engineering Specialist",
        "Software Engineer 2",
        "Software Engineer II",
        "Data Scientist II",
        "Data Scientist 2",
        "Research Scientist",
        "Research Scientist - Neutral Atoms - Quantum AI",
        "Machine Learning Researcher",
        "Quantitative Researcher",
        "Research Fellow",
        "Roblox - Data Scientist - PhD Early Career - Safety",
        "Wyetech - Software Engineer 0 or 1",
        "Senior Software Engineer",
        "Lead AI Engineer",
        "Principal Machine Learning Engineer",
    ]
    for title in disallowed_titles:
        res = check_title_ineligibility(title)
        assert res is not None, f"Expected {title!r} to be rejected by title check"
        assert res["status"] in ("HARD_REJECT", "INELIGIBLE")

def test_entry_level_and_new_grad_titles_allowed():
    allowed_titles = [
        "Software Engineer 1",
        "Software Engineer I",
        "Software Development Engineer 1 - Security Platform",
        "Junior Software Developer",
        "New Grad Software Engineer",
        "Machine Learning Engineer - New Grad",
        "AI Engineer",
        "Applied AI Engineer",
        "Associate Data Scientist",
        "Data Scientist 1",
        "Data Scientist I",
        "Robotics Software Engineer New Grad",
    ]
    for title in allowed_titles:
        res = check_title_ineligibility(title)
        assert res is None, f"Expected {title!r} to pass title check, got {res}"

def test_fiserv_full_text_experience_rejection():
    jd_text = """
    Job Title: AI Engineering Specialist
    What you must have?
    3+ years of software engineering experience using Python or a similar programming language.
    2+ years of experience developing APIs, microservices, and systems integrations.
    1+ year of hands-on experience with pipelines, workflow automation, and CI/CD practices.
    Bachelor's degree in Computer Science, Software Engineering, or a related field.
    """
    res = explain_eligibility(jd_text, title="AI Engineering Specialist")
    assert res["status"] == "HARD_REJECT"

def test_amazon_experience_rejection():
    jd_text = """
    Employer will accept a Bachelor's degree and five years of progressive post-baccalaureate research or work experience.
    Must have one year of research or work experience in programming.
    """
    res = explain_eligibility(jd_text, title="Applied Scientist II")
    assert res["status"] == "HARD_REJECT"

def test_genuine_new_grad_passes():
    jd_text = """
    We are seeking a New Grad Software Engineer to join our team in 2026.
    Requirements:
    Bachelor's or Master's degree in Computer Science or related STEM field.
    0-2 years of experience or relevant internship experience.
    Proficiency in Python and Git.
    """
    res = explain_eligibility(jd_text, title="Software Engineer 1")
    assert res["status"] == "PASS"

def test_uk_location_rejected():
    assert is_us_location("London, UK") is False
    assert is_us_location("Manchester, England") is False
    assert is_us_location("Toronto, ON, Canada") is False
    assert is_us_location("San Francisco, CA") is True
    assert is_us_location("Remote - US") is True
