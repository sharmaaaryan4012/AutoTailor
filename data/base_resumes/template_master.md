<div class="header">
  <h1>{{ candidate_name | default("Aaryan Sharma") }}</h1>
  <p>{{ phone | default("+1 (312) 871-2883") }} &bull; <a href="mailto:{{ email | default('aaryan.sharma@kellogg.northwestern.edu') }}">{{ email | default("aaryan.sharma@kellogg.northwestern.edu") }}</a> &bull; <a href="https://{{ website | default('saaryan.com') }}">{{ website | default("saaryan.com") }}</a> &bull; <a href="https://{{ linkedin_url | default('linkedin.com/in/sharmaaaryan') }}">LinkedIn @ {{ linkedin_url | default("linkedin.com/in/sharmaaaryan") }}</a></p>
</div>

<h2>Education</h2>
<div class="row bold"><span>{{ university_1 | default("Northwestern University, Kellogg School of Management") }}</span><span>{{ grad_date_1 | default("June 2027") }}</span></div>
<div class="row"><span>{{ degree_1 | default("Master in Management") }}</span><span></span></div>
<ul>
  <li><!-- ID: EDU_NU_01 --> <strong>The Garage (Startup Incubator):</strong> Pursuing commercialization of {{ project_2 | default("SkyRipple") }} through the Tinker program</li>
</ul>
<div class="row bold"><span>{{ university_2 | default("University of Illinois Urbana-Champaign, Grainger College of Engineering") }}</span><span>{{ grad_date_2 | default("May 2026") }}</span></div>
<div class="row"><span>{{ degree_2 | default("Bachelor of Science in Mathematics & Computer Science") }}</span><span>{{ gpa_2 | default("GPA: 3.60/4.00") }}</span></div>
<ul>
  <li><!-- ID: EDU_UIUC_01 --> <strong>City Scholars:</strong> Selected as 1 of 25 for the college's premier academic-corporate fellowship in Chicago</li>
  <li><!-- ID: EDU_UIUC_02 --> <strong>Research:</strong> Presented election forecasting research to 100+ experts at the DIMACS 2024 conference</li>
  <li><!-- ID: EDU_UIUC_03 --> <strong>Technical Lead:</strong> Led a 10-member team delivering 8 AI solutions; received the ATLAS Spotlight Award (1 of 96)</li>
</ul>

<h2>Skills</h2>
<div class="skills-row"><div class="skills-category">Languages:</div><div><!-- ID: SKILLS_LANG --> Python, C++, Java, JavaScript, SQL, R</div></div>
<div class="skills-row"><div class="skills-category">Software Engineering:</div><div><!-- ID: SKILLS_SWE --> FastAPI, REST APIs, Docker, Git, CI/CD, PostgreSQL</div></div>
<div class="skills-row"><div class="skills-category">AI & Machine Learning:</div><div><!-- ID: SKILLS_AI_ML --> PyTorch, TensorFlow, scikit-learn, XGBoost, LangChain, LangGraph, ChromaDB</div></div>
<div class="skills-row"><div class="skills-category">Certifications:</div><div><!-- ID: SKILLS_CERT --> Docker Foundations (Docker, Inc.), DevOps Professional Certificate (LinkedIn)</div></div>

<h2>Experience</h2>
<div class="row bold"><span>HERE Technologies</span><span>Chicago, IL</span></div>
<div class="row"><span>Data Science Intern</span><span>Jan 2026 &ndash; May 2026</span></div>
<ul>
  <li><!-- ID: HERE_01 --> Developed a Two-Tower neural network comprising three multilayer perceptrons (MLPs) to learn road-sign and supporting-structure representations, improving spatial association accuracy from 82% with XGBoost to 98%</li>
  <li><!-- ID: HERE_02 --> Engineered 28 geometric, spatial, and relational features and addressed a ~1:10 positive-to-negative class imbalance, supporting automated map updates with 1,500+ weekly fieldwork hours avoided across Europe</li>
</ul>
<div class="row bold"><span>Onix Networking</span><span>Pune, India</span></div>
<div class="row"><span>Artificial Intelligence Intern</span><span>Jun 2025 &ndash; Aug 2025</span></div>
<ul>
  <li><!-- ID: ONIX_01 --> Developed an agentic simulation system within Kingfisher to generate synthetic healthcare data on demand</li>
  <li><!-- ID: ONIX_02 --> Built healthcare and insurance workflows generating FHIR-compliant data across 20+ entities</li>
  <li><!-- ID: ONIX_03 --> Evolved the system from rule-based logic to LLM-driven agent orchestration using LangGraph</li>
  <li><!-- ID: ONIX_04 --> Semantically enriched a 10,000-record HMS dataset to establish a domain-specific knowledge base for simulation</li>
</ul>
<div class="row bold"><span>NEC Corporation</span><span>Noida, India</span></div>
<div class="row"><span>Artificial Intelligence Intern</span><span>Dec 2024 &ndash; Jan 2025</span></div>
<ul>
  <li><!-- ID: NEC_AI_01 --> Researched and benchmarked 5 object-tracking algorithms to address motion occlusion in NEC Mi-Eye</li>
  <li><!-- ID: NEC_AI_02 --> Developed and optimized FairMOT-based C++ solutions for vehicle tracking across 1,500+ Delhi traffic cameras</li>
  <li><!-- ID: NEC_AI_03 --> Presented comparative analyses projecting a 40% reduction in compute costs using real-world traffic footage</li>
</ul>
<div class="row bold"><span>NEC Corporation</span><span>Noida, India</span></div>
<div class="row"><span>Software Engineer Intern</span><span>Jun 2024 &ndash; Sep 2024</span></div>
<ul>
  <li><!-- ID: NEC_SWE_01 --> Developed a fleet-management demonstrator integrating government logistics APIs through India's ULIP</li>
  <li><!-- ID: NEC_SWE_02 --> Implemented truck-location updates using FASTag toll records and integrated driver-license verification</li>
  <li><!-- ID: NEC_SWE_03 --> Led a 4-member team and demonstrated the system in 10+ sessions for internal and government stakeholders</li>
</ul>

<h2>Projects</h2>
<!-- ID: PROJECTS_START -->
