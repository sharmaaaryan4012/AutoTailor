"""
src/ai_tailor/patch_applier.py
-------------------------------
Deterministic keyword injection into resume skills section.

Contract:
  - Leaves ALL experience and project bullets untouched (zero risk of LLM hallucination).
  - Appends missing technical keywords to the targeted skills row (<!-- ID: SKILLS_AI_ML -->
    or <!-- ID: SKILLS_SWE --> in AI Engineering; <!-- ID: SKILLS_ML --> or <!-- ID: SKILLS_AI_SYS --> in DS).
  - Cross-references all keywords against a master canonical dictionary to enforce standard
    industry casing regardless of extraction casing (e.g. pytorch -> PyTorch, fastapi -> FastAPI).
  - Deduplicates keywords against already present skills.
"""

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_PROJECTS_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "projects.yaml"


def _load_projects_db() -> dict:
    if not _PROJECTS_YAML_PATH.exists():
        logger.warning("projects.yaml not found at %s", _PROJECTS_YAML_PATH)
        return {}
    with open(_PROJECTS_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        return data.get("projects", data)


PROJECTS_DB = _load_projects_db()

CERTIFICATIONS: dict[str, str] = {
    "AI_ENGINEERING": "Docker Foundations (Docker, Inc.), DevOps Professional Certificate (LinkedIn)",
    "DATA_SCIENCE": "Intermediate Machine Learning, Intro to Machine Learning",
}

# ---------------------------------------------------------------------------
# Master Canonical Casing Dictionary
# ---------------------------------------------------------------------------

CANONICAL_KEYWORDS: dict[str, str] = {
    # Programming Languages
    "python": "Python",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "c": "C",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "sql": "SQL",
    "nosql": "NoSQL",
    "r": "R",
    "rust": "Rust",
    "go": "Go",
    "golang": "Go",
    "scala": "Scala",
    "julia": "Julia",
    "bash": "Bash",
    "shell": "Shell",

    # Machine Learning & Deep Learning Frameworks
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "keras": "Keras",
    "jax": "JAX",
    "flax": "Flax",
    "haiku": "Haiku",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",

    # Inference, Serving & Runtimes
    "vllm": "vLLM",
    "triton": "Triton",
    "triton inference server": "Triton Inference Server",
    "tensorrt": "TensorRT",
    "tensorrt-llm": "TensorRT-LLM",
    "onnx": "ONNX",
    "onnx runtime": "ONNX Runtime",
    "onnxruntime": "ONNX Runtime",
    "tgi": "TGI",
    "ollama": "Ollama",
    "llama.cpp": "llama.cpp",
    "deepsparse": "DeepSparse",

    # LLM, Agentic & Embedding Frameworks
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "llamaindex": "LlamaIndex",
    "semantic kernel": "Semantic Kernel",
    "autogen": "AutoGen",
    "crewai": "CrewAI",
    "dspy": "DSPy",
    "huggingface": "Hugging Face",
    "hugging face": "Hugging Face",
    "transformers": "Transformers",
    "diffusers": "Diffusers",
    "peft": "PEFT",
    "lora": "LoRA",
    "qlora": "QLoRA",

    # Vector Databases & Retrieval
    "chromadb": "ChromaDB",
    "chroma": "ChromaDB",
    "pinecone": "Pinecone",
    "weaviate": "Weaviate",
    "milvus": "Milvus",
    "qdrant": "Qdrant",
    "faiss": "FAISS",

    # Data Processing, Engines & Orchestration
    "pandas": "Pandas",
    "polars": "Polars",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "spark": "Spark",
    "pyspark": "PySpark",
    "apache spark": "Apache Spark",
    "hadoop": "Hadoop",
    "flink": "Flink",
    "apache flink": "Apache Flink",
    "dask": "Dask",
    "ray": "Ray",
    "kafka": "Kafka",
    "apache kafka": "Apache Kafka",
    "airflow": "Airflow",
    "apache airflow": "Apache Airflow",
    "prefect": "Prefect",
    "dagster": "Dagster",
    "dbt": "dbt",

    # Web & API Frameworks
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "rest": "REST",
    "restful": "RESTful",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "websockets": "WebSockets",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "react": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",

    # Databases & Storage
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "cassandra": "Cassandra",
    "snowflake": "Snowflake",
    "bigquery": "BigQuery",
    "redshift": "Redshift",
    "dynamodb": "DynamoDB",

    # Cloud, DevOps & Systems
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "helm": "Helm",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "git": "Git",
    "github actions": "GitHub Actions",
    "gitlab ci": "GitLab CI",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "linux": "Linux",
    "cuda": "CUDA",
    "ebpf": "eBPF",
    "nccl": "NCCL",
    "cudnn": "cuDNN",
    "opencl": "OpenCL",
    "opengl": "OpenGL",
    "mlflow": "MLflow",
    "wandb": "Weights & Biases",
    "weights & biases": "Weights & Biases",
    "dvc": "DVC",
    "kubeflow": "Kubeflow",
}


def canonicalize_keyword(keyword: str) -> str:
    """
    Cross-reference an extracted keyword against the master dictionary to enforce
    canonical industry casing.
    """
    cleaned = keyword.strip()
    return CANONICAL_KEYWORDS.get(cleaned.lower(), cleaned)


def _build_projects_html(selected_projects: list[str], projects_db: dict) -> str:
    """
    Build raw HTML for the selected projects adhering strictly to the 10-line vertical budget:
      - 2 projects: Project 1 (header + 4 bullets), Project 2 (header + 4 bullets) -> 5 + 5 = 10 lines
      - 3 projects: Project 1 (header + 3 bullets), Project 2 (header + 2 bullets), Project 3 (header + 2 bullets) -> 4 + 3 + 3 = 10 lines
    Bullets are formatted with <ul> and <li> tags immediately following the header, joined with a newline.
    """
    db = projects_db.get("projects", projects_db)

    # Clean and deduplicate selected projects matching available DB keys
    clean_projects: list[str] = []
    for p in (selected_projects or []):
        key = str(p).strip().upper()
        if key in db and key not in clean_projects:
            clean_projects.append(key)

    # Determine layout allocation based on project count
    if len(clean_projects) >= 3:
        chosen = clean_projects[:3]
        layout = ["bullets_3", "bullets_2", "bullets_2"]
    else:
        chosen = clean_projects[:]
        fallback_order = ["TOUDM", "SKYRIPPLE", "PLANSIGHT", "DEX", "NETRESCUE", "PACKETLENS"]
        for fb in fallback_order:
            if len(chosen) == 2:
                break
            if fb in db and fb not in chosen:
                chosen.append(fb)
        layout = ["bullets_4", "bullets_4"]

    project_blocks: list[str] = []
    for proj_key, bullet_field in zip(chosen, layout):
        proj_data = db[proj_key]
        header = proj_data["header"]
        bullets = proj_data.get(bullet_field, [])
        li_lines = "\n".join(f"  <li>{b}</li>" for b in bullets)
        block = f"{header}\n<ul>\n{li_lines}\n</ul>"
        project_blocks.append(block)

    return "\n".join(project_blocks)


def apply_patch(
    base_md_path: str,
    extracted_keywords: list[str],
    selected_projects: list[str] | None = None,
    track: str = "AI_ENGINEERING",
) -> str:
    """
    Deterministically inject extracted keywords into the skills section of the resume,
    dynamically update certifications based on the track, and inject pre-computed project blocks.

    Parameters
    ----------
    base_md_path : str
        Path to the base resume (HTML-infused Markdown).
    extracted_keywords : list[str]
        List of technical keywords extracted from the JD by Gemini.
    selected_projects : list[str] | None
        List of 2 or 3 project IDs selected by Gemini or specified by caller.
    track : str
        Classification track ('AI_ENGINEERING' or 'DATA_SCIENCE') for dynamic certification selection.

    Returns
    -------
    str
        The updated resume content with keywords, certifications, and project blocks injected.
    """
    path = Path(base_md_path)
    if not path.exists():
        raise FileNotFoundError(f"Base resume not found: {path.resolve()}")

    content = path.read_text(encoding="utf-8")

    # 1. Deterministic Keyword Injection (if keywords provided)
    if extracted_keywords:
        # Clean, canonicalize, and deduplicate incoming keywords preserving order
        seen_lower: set[str] = set()
        clean_kws: list[str] = []
        for k in extracted_keywords:
            if not k or not k.strip():
                continue
            canonical = canonicalize_keyword(k)
            if canonical.lower() not in seen_lower:
                seen_lower.add(canonical.lower())
                clean_kws.append(canonical)

        if clean_kws:
            # Find the primary skill injection target:
            # Look for SKILLS_AI_ML or SKILLS_ML first, otherwise SKILLS_SWE or SKILLS_AI_SYS
            primary_target = re.search(r"<!--\s*ID:\s*(SKILLS_AI_ML|SKILLS_ML)\s*-->", content, re.IGNORECASE)
            if not primary_target:
                primary_target = re.search(r"<!--\s*ID:\s*(SKILLS_SWE|SKILLS_AI_SYS)\s*-->", content, re.IGNORECASE)

            if primary_target:
                tag_name = primary_target.group(1)

                # Pattern matches the entire skill row containing the category and tag:
                # <div class="skills-row"><div class="skills-category">Category:</div><div><!-- ID: TAG --> Existing skills...</div></div>
                row_pattern = re.compile(
                    rf'(?P<row_prefix><div class="skills-row">\s*<div class="skills-category">\s*(?P<category>[^<]+?)\s*</div>\s*<div>\s*<!--\s*ID:\s*{tag_name}\s*-->\s*)(?P<skills>.*?)(?P<row_suffix></div>\s*</div>)',
                    re.IGNORECASE,
                )
                # Fallback pattern if row structure differs
                line_pattern = re.compile(
                    rf"(?P<prefix><div[^>]*><!--\s*ID:\s*{tag_name}\s*-->\s*)(?P<skills>.*?)(?P<suffix></div>\s*</div>)",
                    re.IGNORECASE,
                )

                def _inject(match: re.Match) -> str:
                    if "row_prefix" in match.groupdict() and match.group("row_prefix"):
                        prefix = match.group("row_prefix")
                        suffix = match.group("row_suffix")
                        category_text = match.group("category").strip()
                    else:
                        prefix = match.group("prefix")
                        suffix = match.group("suffix")
                        category_text = tag_name.replace("SKILLS_", "").replace("_", " ").title() + ":"

                    existing_skills = match.group("skills").strip()

                    # Existing tokens in the current line (case-insensitive)
                    existing_tokens = {
                        token.strip().lower() for token in re.split(r"[,;]+", existing_skills) if token.strip()
                    }

                    # Collect all skills across the entire Skills section to prevent cross-category repetition
                    skills_section_match = re.search(r"<h2>\s*Skills\s*</h2>(.*?)(?=\n<h2|\Z)", content, re.DOTALL | re.IGNORECASE)
                    section_tokens: set[str] = set()
                    if skills_section_match:
                        raw_text = re.sub(r"<!--.*?-->", " ", skills_section_match.group(1))
                        raw_text = re.sub(r"<[^>]+>", " ", raw_text)
                        for tok in re.split(r"[,;:\n\(\)]+", raw_text):
                            cleaned_tok = tok.strip().lower()
                            if cleaned_tok:
                                section_tokens.add(cleaned_tok)

                    current_skills = existing_skills
                    new_kws: list[str] = []

                    for kw in clean_kws:
                        kw_clean = kw.strip()
                        kw_lower = kw_clean.lower()

                        # Task 2: Fix Skill Repetition
                        # Check if keyword (case-insensitive) already exists in current line or skills section
                        if (
                            kw_lower in existing_tokens
                            or re.search(rf"\b{re.escape(kw_lower)}\b", existing_skills.lower())
                            or kw_lower in section_tokens
                        ):
                            logger.debug("Skipping duplicate skill '%s' (already exists in resume)", kw_clean)
                            continue

                        # Task 3: Prevent Skill Line Wrapping
                        # Calculate the new projected line length of the visual text
                        projected_skills = f"{current_skills}, {kw_clean}" if current_skills else kw_clean
                        projected_visual_text = f"{category_text} {projected_skills}".strip()

                        if len(projected_visual_text) > 115:
                            logger.info(
                                "Skipping skill '%s' to prevent wrapping: projected length (%d) > 115 chars [Category: %s]",
                                kw_clean, len(projected_visual_text), category_text,
                            )
                            continue

                        # Fits within 115 characters without wrapping
                        current_skills = projected_skills
                        existing_tokens.add(kw_lower)
                        section_tokens.add(kw_lower)
                        new_kws.append(kw_clean)

                    if not new_kws:
                        return match.group(0)

                    appended_str = ", ".join(new_kws)
                    logger.info(
                        "Injected %d keywords into %s [%s] (%d visual chars): %s",
                        len(new_kws), path.name, tag_name, len(f"{category_text} {current_skills}"), appended_str,
                    )
                    return f"{prefix}{current_skills}{suffix}"

                pattern_to_use = row_pattern if row_pattern.search(content) else line_pattern
                updated_content, count = pattern_to_use.subn(_inject, content, count=1)
                if count > 0:
                    content = updated_content
                else:
                    logger.warning("Could not match line structure for %s — skills line unchanged", tag_name)
            else:
                logger.warning("No target skills tag found in %s — skills unchanged", path.name)

    # 2. Dynamic Certifications Injection based on track
    normalized_track = "DATA_SCIENCE" if "DATA" in (track or "").upper() else "AI_ENGINEERING"
    certs_to_inject = CERTIFICATIONS.get(normalized_track, CERTIFICATIONS["AI_ENGINEERING"])
    cert_pattern = re.compile(
        r"(?P<prefix><div[^>]*><!--\s*ID:\s*SKILLS_CERT\s*-->\s*)(?P<certs>.*?)(?P<suffix></div>\s*</div>)",
        re.IGNORECASE,
    )
    if cert_pattern.search(content):
        content = cert_pattern.sub(rf"\g<prefix>{certs_to_inject}\g<suffix>", content, count=1)
        logger.info("Injected %s certifications into %s: %s", normalized_track, path.name, certs_to_inject)
    else:
        logger.warning("<!-- ID: SKILLS_CERT --> not found in %s — certs unchanged", path.name)

    # 3. Modular Project Bank Injection
    projects_marker = "<!-- ID: PROJECTS_START -->"
    projects_html = _build_projects_html(selected_projects or [], PROJECTS_DB)

    if projects_marker in content:
        pattern = re.compile(
            rf"({re.escape(projects_marker)})(.*?)(?=(?:\n<h2|\n{{%\s*endif|\n</body>|\Z))",
            re.DOTALL | re.IGNORECASE,
        )
        content = pattern.sub(rf"\1\n{projects_html}", content, count=1)
        logger.info("Injected dynamic projects HTML into %s below %s", path.name, projects_marker)
    else:
        # Fallback if PROJECTS_START marker is missing but <h2>Projects</h2> is present
        h2_match = re.search(
            r"(<h2[^>]*>\s*Projects\s*</h2>)(.*?)(?=(?:\n<h2|\n{{%\s*endif|\n</body>|\Z))",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if h2_match:
            content = (
                content[:h2_match.start(1)]
                + f"{h2_match.group(1)}\n{projects_marker}\n{projects_html}"
                + content[h2_match.end():]
            )
            logger.info("Injected %s and dynamic projects HTML into %s below <h2>Projects</h2>", projects_marker, path.name)
        else:
            logger.warning("Neither '%s' nor '<h2>Projects</h2>' found in %s", projects_marker, path.name)

    return content
