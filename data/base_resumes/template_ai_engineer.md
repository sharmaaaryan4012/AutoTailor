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
  <li><!-- ID: EDU_UIUC_02 --> <strong>Research:</strong> Presented distributed systems research to 100+ domain experts at national symposium</li>
  <li><!-- ID: EDU_UIUC_03 --> <strong>Technical Lead:</strong> Led a 10-member team delivering production AI solutions for university research labs</li>
</ul>

<h2>Skills</h2>
<div class="skills-row"><div class="skills-category">Languages:</div><div><!-- ID: SKILLS_LANG --> Python, C++, Java, JavaScript, SQL, R</div></div>
<div class="skills-row"><div class="skills-category">Software Engineering:</div><div><!-- ID: SKILLS_SWE --> FastAPI, REST APIs, Docker, Git, CI/CD, PostgreSQL</div></div>
<div class="skills-row"><div class="skills-category">AI & Machine Learning:</div><div><!-- ID: SKILLS_AI_ML --> PyTorch, TensorFlow, scikit-learn, XGBoost, LangChain, LangGraph, ChromaDB</div></div>
<div class="skills-row"><div class="skills-category">Certifications:</div><div><!-- ID: SKILLS_CERT --> Docker Foundations (Docker, Inc.), Cloud Practitioner</div></div>

<h2>Experience</h2>
<div class="row bold"><span>Acme Technologies Inc.</span><span>San Francisco, CA</span></div>
<div class="row"><span>Machine Learning Engineer Intern</span><span>Jan 2026 &ndash; May 2026</span></div>
<ul>
  <li><!-- ID: EXP_01 --> Developed a Two-Tower neural network comprising multilayer perceptrons (MLPs) to learn entity representations, improving spatial association accuracy from 82% with XGBoost to 98%</li>
  <li><!-- ID: EXP_02 --> Engineered 28 geometric, spatial, and relational features and resolved tabular class imbalances, supporting automated data ingestion pipelines with 1,500+ weekly manual fieldwork hours avoided</li>
</ul>
<div class="row bold"><span>Apex Analytics Corporation</span><span>New York, NY</span></div>
<div class="row"><span>AI Systems Intern</span><span>Jun 2025 &ndash; Aug 2025</span></div>
<ul>
  <li><!-- ID: EXP_03 --> Developed an agentic simulation system to generate synthetic tabular and workflow data on demand</li>
  <li><!-- ID: EXP_04 --> Built domain workflows generating validated multi-entity records across 20+ schema definitions</li>
  <li><!-- ID: EXP_05 --> Evolved the system from rule-based logic to LLM-driven agent orchestration using LangGraph</li>
  <li><!-- ID: EXP_06 --> Semantically enriched a 10,000-record dataset to establish a domain-specific knowledge base for simulation</li>
</ul>
<div class="row bold"><span>Vanguard Global Systems</span><span>Austin, TX</span></div>
<div class="row"><span>Computer Vision Intern</span><span>Dec 2024 &ndash; Jan 2025</span></div>
<ul>
  <li><!-- ID: EXP_07 --> Researched and benchmarked 5 object-tracking algorithms to address motion occlusion in production video feeds</li>
  <li><!-- ID: EXP_08 --> Developed and optimized deep learning tracking solutions in C++ and Python across 1,500+ live video streams</li>
  <li><!-- ID: EXP_09 --> Presented comparative analyses projecting a 40% reduction in cloud compute costs using real-world streaming data</li>
</ul>
<div class="row bold"><span>Vanguard Global Systems</span><span>Austin, TX</span></div>
<div class="row"><span>Software Engineer Intern</span><span>Jun 2024 &ndash; Sep 2024</span></div>
<ul>
  <li><!-- ID: EXP_10 --> Developed a logistics platform demonstrator integrating public transport and enterprise routing APIs</li>
  <li><!-- ID: EXP_11 --> Implemented real-time asset location updates using toll records and integrated identity verification services</li>
  <li><!-- ID: EXP_12 --> Led a 4-member team and demonstrated the system in 10+ stakeholder sessions with technical partners</li>
</ul>

<h2>Projects</h2>
<div class="row bold"><span>{{ project_1 | default("The Open Universal Data Marketplace") }} | Product Builder</span><span>Sep 2026 &ndash; Present</span></div>
<ul>
  <li><!-- ID: PROJ_01 --> Architected a multi-service compute-to-data platform using Next.js, FastAPI, PostgreSQL, and Docker, enabling buyers to run workloads against provider-hosted data without directly exposing raw datasets</li>
  <li><!-- ID: PROJ_02 --> Selected PyTorch TabDDPM over GANs to generate 1,000-row synthetic previews of mixed-type data; designed secure execution pipelines with cryptographic attestation and egress controls</li>
</ul>
<div class="row bold"><span>{{ project_2 | default("SkyRipple") }} | Product Builder</span><span>Aug 2026 &ndash; Sep 2026</span></div>
<ul>
  <li><!-- ID: PROJ_03 --> Built an AI-powered disruption recovery platform using a Python simulation engine to model cascading delays across 500K+ historical operational records in under 20 seconds</li>
  <li><!-- ID: PROJ_04 --> Engineered a 5-agent recovery system coordinating assets, crew, and operations with deterministic validation of recovery plans, yielding $145K in modeled disruption-cost savings</li>
</ul>
