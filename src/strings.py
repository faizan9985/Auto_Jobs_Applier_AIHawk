# Personal Information Template
personal_information_template = """
Answer the following question based on the provided personal information.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."

## Example
My resume: John Doe, born on 01/01/1990, living in Milan, Italy.
Question: What is your city?
 Milan

Personal Information: {resume_section}
Question: {question}
"""

# Self Identification Template
self_identification_template = """
Answer the following question based on the provided self-identification details.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."

## Example
My resume: Male, uses he/him pronouns, not a veteran, no disability.
Question: What are your gender?
Male

Self-Identification: {resume_section}
Question: {question}
"""

# Legal Authorization Template
legal_authorization_template = """
Answer the following question based on the provided legal authorization details.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."

## Example
My resume: Authorized to work in the EU, no US visa required.
Question: Are you legally allowed to work in the EU?
Yes

Legal Authorization: {resume_section}
Question: {question}
"""

# Work Preferences Template
work_preferences_template = """
Answer the following question based on the provided work preferences.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."

## Example
My resume: Open to remote work, willing to relocate.
Question: Are you open to remote work?
Yes

Work Preferences: {resume_section}
Question: {question}
"""

# Education Details Template
education_details_template = """
Answer the following question based on the provided education details.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters.

## Example
My resume: Bachelor's degree in Computer Science with experience in Python.
Question: Do you have experience with Python?
Yes, I have experience with Python.

Education Details: {resume_section}
Question: {question}
"""

# Experience Details Template
experience_details_template = """
Answer the following question based on the provided experience details.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters.

## Example
My resume: 3 years as a software developer with leadership experience.
Question: Do you have leadership experience?
Yes, I have leadership experience; its duration is not specified.

Experience Details: {resume_section}
Question: {question}
"""

# Projects Template
projects_template = """
Answer the following question based on the provided project details.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters.

## Example
My resume: Led the development of a mobile app, repository available.
Question: Have you led any projects?
Yes, led the development of a mobile app

Projects: {resume_section}
Question: {question}
"""

# Availability Template
availability_template = """
Answer the following question based on the provided availability details.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters.
- Use periods only if the answer has multiple sentences.

## Example
My resume: Available to start immediately.
Question: When can you start?
I can start immediately.

Availability: {resume_section}
Question: {question}
"""

# Salary Expectations Template
salary_expectations_template = """
Answer the following question based on the provided salary expectations.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters.
- Use periods only if the answer has multiple sentences.

## Example
My resume: Looking for a salary in the range of 50k-60k USD.
Question: What are your salary expectations?
55000.

Salary Expectations: {resume_section}
Question: {question}
"""

# Certifications Template
certifications_template = """
Answer the following question based on the provided certifications.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters.

## Example
My resume: Certified in Project Management Professional (PMP).
Question: Do you have PMP certification?
Yes, I am PMP certified.

Certifications: {resume_section}
Question: {question}
"""

# Languages Template
languages_template = """
Answer the following question based on the provided language skills.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters. Do not add any additional languages what is not in my experience

## Example
My resume: Fluent in Italian and English.
Question: What languages do you speak?
Fluent in Italian and English.

Languages: {resume_section}
Question: {question}
"""

# Interests Template
interests_template = """
Answer the following question based on the provided interests.

## Rules
- Answer questions directly, using only facts explicitly supported by the supplied candidate profile/resume.
- Do not invent or inflate skills, experience, durations, qualifications, or preferences.
- If the answer is not supported, say "Unknown from the provided candidate data."
- Keep the answer under 140 characters.
- Use periods only if the answer has multiple sentences.

## Example
My resume: Interested in AI and data science.
Question: What are your interests?
AI and data science.

Interests: {resume_section}
Question: {question}
"""

summarize_prompt_template = """
As a seasoned HR expert, your task is to identify and outline the key skills and requirements necessary for the position of this job. Use the provided job description as input to extract all relevant information. This will involve conducting a thorough analysis of the job's responsibilities and the industry standards. You should consider both the technical and soft skills needed to excel in this role. Additionally, specify any educational qualifications, certifications, or experiences that are essential. Your analysis should also reflect on the evolving nature of this role, considering future trends and how they might affect the required competencies.

Rules:
Remove boilerplate text
Include only relevant information to match the job description against the resume

# Analysis Requirements
Your analysis should include the following sections:
Technical Skills: List all the specific technical skills required for the role based on the responsibilities described in the job description.
Soft Skills: Identify the necessary soft skills, such as communication abilities, problem-solving, time management, etc.
Educational Qualifications and Certifications: Specify the essential educational qualifications and certifications for the role.
Professional Experience: Describe the relevant work experiences that are required or preferred.
Role Evolution: Analyze how the role might evolve in the future, considering industry trends and how these might influence the required skills.

# Final Result:
Your analysis should be structured in a clear and organized document with distinct sections for each of the points listed above. Each section should contain:
This comprehensive overview will serve as a guideline for the recruitment process, ensuring the identification of the most qualified candidates.

# Job Description:
```
{text}
```

---

# Job Description Summary"""

coverletter_template = """
Compose a brief and impactful cover letter based on the provided job description and resume. The letter should be no longer than three paragraphs and should be written in a professional, yet conversational tone. Avoid using any placeholders, and ensure that the letter flows naturally and is tailored to the job.

Analyze the job description to identify key qualifications and requirements. Introduce the candidate succinctly, aligning their career objectives with the role. Highlight relevant skills and experiences from the resume that directly match the job’s demands, using specific examples to illustrate these qualifications. Reference notable aspects of the company, such as its mission or values, that resonate with the candidate’s professional goals. Conclude with a strong statement of why the candidate is a good fit for the position, expressing a desire to discuss further.

Please write the cover letter in a way that directly addresses the job role and the company’s characteristics, ensuring it remains concise and engaging without unnecessary embellishments. The letter should be formatted into paragraphs and should not include a greeting or signature.

## Rules:
- Use only candidate claims explicitly supported by the resume; do not invent or inflate skills, experience, qualifications, or durations.
- Provide only the text of the cover letter.
- Do not include any introductions, explanations, or additional information.
- The letter should be formatted into paragraph.

## Job Description:
```
{job_description}
```
## My resume:
```
{resume}
```
"""

numeric_question_template = """
Answer the numeric question using only verified facts in the supplied candidate data.

## Rules
- Return only a nonnegative number when the answer is determinable; 0 is allowed.
- For years of experience, use an explicitly stated duration or calculate from dates
  that explicitly establish experience with the requested skill. Do not round up
  or double-count overlapping periods; preserve fractional years when supported.
- Do not infer skills or durations from related technologies, degrees, grades,
  job titles, or undated projects. Academic/project experience is not professional
  experience unless the supplied data explicitly establishes that it is.
- If the requested number cannot be determined, return UNKNOWN. Do not guess.
- Examples illustrate the rules; they are not facts about the candidate.

## Examples
Candidate: Explicitly has 0 years of Java experience. Question: Years of Java? Answer: 0
Candidate: Explicitly has 3 years of Python experience. Question: Years of Python? Answer: 3
Candidate: Has a CS degree and Python projects. Question: Years of Java? Answer: UNKNOWN
Candidate: Has an undated Unity project. Question: Years of Unity? Answer: UNKNOWN

## Candidate data
{resume_educations}
{resume_jobs}
{resume_projects}

## Question
{question}
"""

options_template = """The following is a resume and an answered question about the resume, the answer is one of the options.

## Rules
- Use only facts explicitly supported by the supplied candidate profile/resume.
- Do not infer or inflate skills, experience, durations, or qualifications.
- Never choose a placeholder such as 'Select an option'. 'None', 'No', and zero-experience options are valid when supported.
- If no option is supported, return UNKNOWN rather than choosing an unsupported claim.
- Return exactly one supported option, or UNKNOWN if none is supported.

## Example
My resume: I'm a software engineer with 10 years of experience on swift, python, C, C++.
Question: How many years of experience do you have on python?
Options: [1-2, 3-5, 6-10, 10+]
10+

-----

## My resume:
```
{resume}
```

## Candidate profile:
{profile}

## Question:
{question}

## Options:
{options}

## """

try_to_fix_template = """\
The objective is to fix the text of a form input on a web page.

## Rules
- Use the error to fix the original text.
- The error "Please enter a valid answer" usually means the text is too large, shorten the reply to less than a tweet.
- Never change candidate facts or increase experience to meet form constraints. If the verified answer is not accepted, return UNKNOWN.

-----

## Form Question
{question}

## Input
{input} 

## Error
{error}  

## Fixed Input
"""

func_summarize_prompt_template = """
        Following are two texts, one with placeholders and one without, the second text uses information from the first text to fill the placeholders.
        
        ## Rules
        - A placeholder is a string like "[[placeholder]]". E.g. "[[company]]", "[[job_title]]", "[[years_of_experience]]"...
        - The task is to remove the placeholders from the text.
        - If there is no information to fill a placeholder, remove the placeholder, and adapt the text accordingly.
        - No placeholders should remain in the text.
        
        ## Example
        Text with placeholders: "I'm a software engineer engineer with 10 years of experience on [placeholder] and [placeholder]."
        Text without placeholders: "I'm a software engineer with 10 years of experience."
        
        -----
        
        ## Text with placeholders:
        {text_with_placeholders}
        
        ## Text without placeholders:"""
