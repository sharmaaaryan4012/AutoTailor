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

logger = logging.getLogger(__name__)

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


def apply_patch(base_md_path: str, extracted_keywords: list[str]) -> str:
    """
    Deterministically inject extracted keywords into the skills section of the resume.

    Parameters
    ----------
    base_md_path : str
        Path to the base resume (HTML-infused Markdown).
    extracted_keywords : list[str]
        List of technical keywords extracted from the JD by Gemini.

    Returns
    -------
    str
        The updated resume content with keywords cleanly appended in canonical casing.
    """
    path = Path(base_md_path)
    if not path.exists():
        raise FileNotFoundError(f"Base resume not found: {path.resolve()}")

    content = path.read_text(encoding="utf-8")

    if not extracted_keywords:
        logger.debug("No keywords to inject — returning base resume unmodified")
        return content

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

    if not clean_kws:
        return content

    # Find the primary skill injection target:
    # Look for SKILLS_AI_ML or SKILLS_ML first, otherwise SKILLS_SWE or SKILLS_AI_SYS
    primary_target = re.search(r"<!--\s*ID:\s*(SKILLS_AI_ML|SKILLS_ML)\s*-->", content, re.IGNORECASE)
    if not primary_target:
        primary_target = re.search(r"<!--\s*ID:\s*(SKILLS_SWE|SKILLS_AI_SYS)\s*-->", content, re.IGNORECASE)

    if not primary_target:
        logger.warning("No target skills tag found in %s — returning unmodified", path.name)
        return content

    tag_name = primary_target.group(1)

    # Pattern matches the skill line containing the tag:
    # <div><!-- ID: TAG --> Existing skills...</div></div>
    line_pattern = re.compile(
        rf"(?P<prefix><div[^>]*><!--\s*ID:\s*{tag_name}\s*-->\s*)(?P<skills>.*?)(?P<suffix></div>\s*</div>)",
        re.IGNORECASE,
    )

    def _inject(match: re.Match) -> str:
        prefix = match.group("prefix")
        existing_skills = match.group("skills").strip()
        suffix = match.group("suffix")

        # Parse existing skills to avoid adding duplicates
        existing_tokens = {
            token.strip().lower() for token in re.split(r"[,;]+", existing_skills)
        }

        # Filter out keywords that already exist in this skills line
        new_kws = [kw for kw in clean_kws if kw.lower() not in existing_tokens]

        if not new_kws:
            return match.group(0)

        # Append new keywords comma-separated
        appended_str = ", ".join(new_kws)
        if existing_skills:
            updated_skills = f"{existing_skills}, {appended_str}"
        else:
            updated_skills = appended_str

        logger.info(
            "Injected %d keywords into %s [%s]: %s",
            len(new_kws), path.name, tag_name, appended_str,
        )
        return f"{prefix}{updated_skills}{suffix}"

    updated_content, count = line_pattern.subn(_inject, content, count=1)
    if count == 0:
        logger.warning("Could not match line structure for %s — content unchanged", tag_name)
        return content

    return updated_content
