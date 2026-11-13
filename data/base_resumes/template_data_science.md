<div class="header">
  <h1>{{ candidate_name | default("John Doe") }}</h1>
  <p>{{ phone | default("+1 (555) 019-2834") }} &bull; <a href="mailto:{{ email | default('john.doe@university.edu') }}">{{ email | default("john.doe@university.edu") }}</a> &bull; <a href="https://{{ website | default('johndoe.dev') }}">{{ website | default("johndoe.dev") }}</a> &bull; <a href="https://{{ linkedin_url | default('linkedin.com/in/johndoe') }}">LinkedIn @ {{ linkedin_url | default("linkedin.com/in/johndoe") }}</a></p>
</div>

<h2>Education</h2>
<div class="row bold"><span>{{ university_1 | default("Top Tier University, School of Management") }}</span><span>{{ grad_date_1 | default("June 2027") }}</span></div>
<div class="row"><span>{{ degree_1 | default("Master in Management") }}</span><span></span></div>
<ul>
  <li><!-- ID: EDU_NU_01 --> <strong>The Garage (Startup Incubator):</strong> Pursuing commercialization of {{ project_2 | default("Distributed Systems Platform") }} through incubator program</li>
</ul>
<div class="row bold"><span>{{ university_2 | default("Premier University, College of Engineering") }}</span><span>{{ grad_date_2 | default("May 2026") }}</span></div>
<div class="row"><span>{{ degree_2 | default("Bachelor of Science in Mathematics & Computer Science") }}</span><span>{{ gpa_2 | default("GPA: 3.80/4.00") }}</span></div>
<ul>
  <li><!-- ID: EDU_UIUC_01 --> <strong>Academic Fellowship:</strong> Selected as 1 of 25 for premier academic-corporate fellowship program</li>
  <li><!-- ID: EDU_UIUC_02 --> <strong>Research:</strong> Presented statistical forecasting research to 100+ domain experts at national symposium</li>
  <li><!-- ID: EDU_UIUC_03 --> <strong>Technical Lead:</strong> Led a 10-member team delivering 8 quantitative AI solutions; received department Spotlight Award</li>
</ul>

<h2>Skills</h2>
<div class="skills-row"><div class="skills-category">Languages & Data:</div><div><!-- ID: SKILLS_LANG_DATA --> Python, SQL, C++, R, Pandas, NumPy, SciPy</div></div>
<div class="skills-row"><div class="skills-category">Machine Learning:</div><div><!-- ID: SKILLS_ML --> PyTorch, TensorFlow, scikit-learn, XGBoost, Random Forest, Neural Networks</div></div>
<div class="skills-row"><div class="skills-category">AI & Data Systems:</div><div><!-- ID: SKILLS_AI_SYS --> LangChain, LangGraph, FastAPI, PostgreSQL, ChromaDB</div></div>
<div class="skills-row"><div class="skills-category">Certifications:</div><div><!-- ID: SKILLS_CERT --> Intermediate Machine Learning, Intro to Machine Learning</div></div>

<h2>Experience</h2>
<div class="row bold"><span>Acme Technologies Inc.</span><span>Chicago, IL</span></div>
<div class="row"><span>Data Science Intern</span><span>Jan 2026 &ndash; May 2026</span></div>
<ul>
  <li><!-- ID: EXP_01 --> Developed a Two-Tower neural network comprising multilayer perceptrons (MLPs) to learn spatial representations, improving association accuracy from 82% with XGBoost to 98%</li>
  <li><!-- ID: EXP_02 --> Engineered 28 geometric, spatial, and relational features and resolved class imbalances, supporting automated data ingestion with 1,500+ weekly manual fieldwork hours avoided</li>
</ul>
<div class="row bold"><span>Apex Analytics Corporation</span><span>New York, NY</span></div>
<div class="row"><span>Artificial Intelligence Intern</span><span>Jun 2025 &ndash; Aug 2025</span></div>
<ul>
  <li><!-- ID: EXP_03 --> Developed an agentic simulation system to generate synthetic healthcare data on demand</li>
  <li><!-- ID: EXP_04 --> Built healthcare and insurance workflows generating compliant data across 20+ entity schemas</li>
  <li><!-- ID: EXP_05 --> Evolved the system from rule-based logic to LLM-driven agent orchestration using LangGraph</li>
  <li><!-- ID: EXP_06 --> Derived domain-specific relationships from a 10,000-record dataset to build a knowledge base for simulation</li>
</ul>
<div class="row bold"><span>Vanguard Global Systems</span><span>Austin, TX</span></div>
<div class="row"><span>Artificial Intelligence Intern</span><span>Dec 2024 &ndash; Jan 2025</span></div>
<ul>
  <li><!-- ID: EXP_07 --> Benchmarked 5 object-tracking algorithms to evaluate vehicle tracking under motion occlusion</li>
  <li><!-- ID: EXP_08 --> Evaluated FairMOT and developed C++ solutions for vehicle tracking across 1,500+ live video cameras</li>
  <li><!-- ID: EXP_09 --> Compared algorithm performance using real-world traffic footage, projecting a 40% reduction in compute costs</li>
</ul>
<div class="row bold"><span>Vanguard Global Systems</span><span>Austin, TX</span></div>
<div class="row"><span>Software Engineer Intern</span><span>Jun 2024 &ndash; Sep 2024</span></div>
<ul>
  <li><!-- ID: EXP_10 --> Developed a fleet-management demonstrator integrating government logistics APIs through open platforms</li>
  <li><!-- ID: EXP_11 --> Implemented truck-location updates using toll records and integrated identity verification</li>
  <li><!-- ID: EXP_12 --> Led a 4-member team and demonstrated the system in 10+ sessions for internal and external stakeholders</li>
</ul>

<h2>Projects</h2>
<div class="row bold"><span>{{ project_1 | default("The Open Universal Data Marketplace") }} | Product Builder</span><span>Sep 2026 &ndash; Present</span></div>
<ul>
  <li><!-- ID: PROJ_01 --> Selected Tabular Denoising Diffusion Probabilistic Models (TabDDPM) over GANs to generate mixed continuous and discrete data for 1,000-row previews without exposing raw datasets</li>
  <li><!-- ID: PROJ_02 --> Designed a multi-service data platform integrating PyTorch, FastAPI, Flask, and PostgreSQL 16, with synthetic-data generation supporting privacy-aware discovery and evaluation before purchase</li>
</ul>
<div class="row bold"><span>{{ project_2 | default("SkyRipple") }} | Product Builder</span><span>Aug 2026 &ndash; Sep 2026</span></div>
<ul>
  <li><!-- ID: PROJ_03 --> Developed a Python simulation pipeline using 500K+ historical flight records to model cascading delays, asset rotations, and network-wide disruption costs</li>
  <li><!-- ID: PROJ_04 --> Designed a 5-agent recovery framework to optimize aircraft, crew, gate, and passenger trade-offs under operational constraints, evaluating recovery scenarios that yielded $145K in savings</li>
</ul>
