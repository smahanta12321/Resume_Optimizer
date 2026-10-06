"""Curated vocabulary used to *recognize* skill terms in JD text.

Recognizing a term in a JD says nothing about the candidate. Matching against
profile evidence happens separately (Milestone 4). Aliases are exact
alternative names only. Related-but-different concepts get their own entries
so they are never treated as equivalent.

Ambiguous short names (Go, R, C, React, Excel, Swift, ...) use case-sensitive,
context-limited patterns to avoid matching ordinary English words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Optional

from src.schemas.profile import SkillCategory

# A term must not be glued to other word characters (or to + # for C++/C#).
_LEFT = r"(?<![\w+#])"
_RIGHT = r"(?![\w+#])"
# Positions where a bare language name such as "Go" or "R" is clearly listed as a skill.
_LIST_CONTEXT = r"(?:(?<=,\s)|(?<=[,/(])|(?<=\band\s)|(?<=\bor\s)|(?<=\bin\s)|(?<=:\s))"


@dataclass(frozen=True)
class SkillTerm:
    name: str
    category: SkillCategory
    aliases: tuple[str, ...] = ()
    pattern: Optional[str] = None  # custom regex; replaces alias matching
    case_sensitive: bool = False
    _compiled: Optional[re.Pattern] = field(default=None, compare=False, repr=False)

    def regex(self) -> re.Pattern:
        if self.pattern:
            body = self.pattern
        else:
            names = sorted({self.name, *self.aliases}, key=len, reverse=True)
            body = _LEFT + "(?:" + "|".join(re.escape(n).replace(r"\ ", r"[\s-]+") for n in names) + ")" + _RIGHT
        return re.compile(body, 0 if self.case_sensitive else re.IGNORECASE)


L, F, T, P, C, S = (SkillCategory.LANGUAGE, SkillCategory.FRAMEWORK, SkillCategory.TOOL,
                    SkillCategory.PLATFORM, SkillCategory.CONCEPT, SkillCategory.SOFT)


def _t(name: str, cat: SkillCategory, *aliases: str, pattern: Optional[str] = None,
       case_sensitive: bool = False) -> SkillTerm:
    return SkillTerm(name, cat, tuple(aliases), pattern, case_sensitive)


TAXONOMY: tuple[SkillTerm, ...] = (
    # languages
    _t("Python", L), _t("Java", L), _t("JavaScript", L, "JS"), _t("TypeScript", L, "TS", case_sensitive=True),
    _t("SQL", L), _t("Scala", L), _t("Kotlin", L), _t("Ruby", L), _t("PHP", L), _t("Bash", L, "shell scripting"),
    _t("C++", L, pattern=r"(?<![\w+#])C\+\+(?![\w+#])"),
    _t("C#", L, pattern=r"(?<![\w+#])C#(?![\w+#])"),
    _t("C", L, pattern=_LIST_CONTEXT + r"C(?![\w+#.&/-])", case_sensitive=True),
    _t("Go", L, pattern=r"\bGolang\b|" + _LIST_CONTEXT + r"Go(?![\w'+#-])", case_sensitive=True),
    _t("R", L, pattern=_LIST_CONTEXT + r"R(?![\w&'+#-])|\bR programming\b", case_sensitive=True),
    _t("Rust", L, pattern=r"\bRust\b", case_sensitive=True),
    _t("Swift", L, pattern=r"\bSwift\b(?!\s+(?:delivery|response|action))", case_sensitive=True),
    _t("HTML", L, "HTML5"), _t("CSS", L, "CSS3"),
    # ML / AI
    _t("Machine Learning", C, "ML", pattern=r"(?i:\bmachine[\s-]+learning\b)|\bML\b", case_sensitive=True),
    _t("Deep Learning", C), _t("Natural Language Processing", C, "NLP"), _t("Computer Vision", C),
    _t("Large Language Models", C, "LLM", "LLMs", "large language model"),
    _t("Generative AI", C, "GenAI", "Gen AI"),
    _t("Retrieval-Augmented Generation", C, "RAG", "retrieval augmented generation"),
    _t("Prompt Engineering", C), _t("Fine-tuning", C, "fine tuning", "finetuning"),
    _t("MLOps", C), _t("Reinforcement Learning", C), _t("Statistics", C, "statistical analysis"),
    _t("A/B Testing", C, "AB testing", "A/B tests"), _t("Time Series Analysis", C, "time series"), _t("Forecasting", C),
    _t("Recommender Systems", C, "recommendation systems"), _t("Transformers", C, "transformer models"),
    _t("Vector Databases", C, "vector database", "vector DB", "vector store"),
    _t("Embeddings", C, "embedding models"), _t("Feature Engineering", C), _t("Data Visualization", C),
    _t("PyTorch", F), _t("TensorFlow", F), _t("Keras", F), _t("scikit-learn", F, "sklearn", "scikit learn"),
    _t("pandas", F), _t("NumPy", F), _t("Hugging Face", F, "HuggingFace"), _t("LangChain", F),
    _t("LlamaIndex", F), _t("XGBoost", F), _t("LightGBM", F), _t("spaCy", F), _t("NLTK", F), _t("OpenCV", F),
    _t("MLflow", T), _t("Kubeflow", T), _t("Weights & Biases", T, "W&B", "wandb"),
    _t("FAISS", T), _t("Pinecone", T), _t("Weaviate", T), _t("Chroma", T, "ChromaDB"), _t("Milvus", T),
    _t("OpenAI API", T, "OpenAI"), _t("Anthropic API", T, "Claude API"),
    # data
    _t("Apache Spark", F, "Spark"), _t("PySpark", F), _t("Hadoop", F), _t("Hive", T), _t("Apache Kafka", T, "Kafka"),
    _t("Apache Airflow", T, "Airflow"), _t("dbt", T), _t("Snowflake", P), _t("Databricks", P),
    _t("BigQuery", P), _t("Redshift", P), _t("ETL", C), _t("ELT", C), _t("Data Pipelines", C, "data pipeline"), _t("Data Warehousing", C, "data warehouse"),
    _t("PostgreSQL", T, "Postgres"), _t("MySQL", T), _t("MongoDB", T), _t("Redis", T),
    _t("Elasticsearch", T, "Elastic Search"), _t("OpenSearch", T), _t("Cassandra", T), _t("DynamoDB", T),
    _t("Tableau", T), _t("Power BI", T, "PowerBI"), _t("Looker", T),
    _t("Excel", T, pattern=r"\b(?:MS |Microsoft )?Excel\b(?!\s+(?:at|in)\b)", case_sensitive=True),
    # cloud / devops
    _t("AWS", P, "Amazon Web Services"), _t("Azure", P, "Microsoft Azure"),
    _t("Google Cloud", P, "GCP", "Google Cloud Platform"), _t("Docker", T), _t("Kubernetes", T, "k8s"),
    _t("Terraform", T), _t("Ansible", T), _t("Jenkins", T), _t("GitHub Actions", T), _t("Git", T),
    _t("CI/CD", C, "CI / CD", "continuous integration"), _t("Linux", P), _t("SageMaker", P, "Amazon SageMaker"),
    _t("Vertex AI", P), _t("Microservices", C, "microservice architecture"),
    _t("REST APIs", C, "REST", "RESTful", "REST API", "RESTful APIs"), _t("GraphQL", T),
    # web frameworks
    _t("FastAPI", F), _t("Flask", F), _t("Django", F), _t("Spring Boot", F), _t("Node.js", F, "NodeJS"),
    _t("React", F, pattern=r"\bReact(?:\.js|JS)?\b(?!\s+(?:to|quickly)\b)", case_sensitive=True),
    _t("Angular", F, "AngularJS"), _t("Vue.js", F, "Vue", "VueJS"), _t(".NET", F, pattern=r"(?<![\w])\.NET\b"),
    _t("Streamlit", F),
    # ways of working / soft
    _t("Agile", C), _t("Scrum", C), _t("JIRA", T), _t("Communication", S, "communication skills"),
    _t("Leadership", S), _t("Stakeholder Management", S), _t("Mentoring", S, "mentorship"),
    _t("Problem Solving", S, "problem-solving"),
)

DOMAIN_TERMS: tuple[SkillTerm, ...] = tuple(
    _t(name, C, *aliases) for name, *aliases in (
        ("FinTech", "financial technology"), ("Banking",), ("Financial Services",), ("Insurance", "insurtech"),
        ("Healthcare", "healthtech", "health tech"), ("E-commerce", "ecommerce", "e commerce"), ("Retail",),
        ("SaaS",), ("B2B",), ("B2C",), ("EdTech", "education technology"), ("Telecom", "telecommunications"),
        ("Automotive",), ("Manufacturing",), ("Logistics", "supply chain"), ("Gaming",), ("AdTech", "advertising technology"),
        ("Cybersecurity", "cyber security", "information security"), ("Pharma", "pharmaceutical", "life sciences"),
        ("Travel",),
    )
)


@lru_cache(maxsize=1)
def _compiled_taxonomy() -> tuple[tuple[SkillTerm, re.Pattern], ...]:
    return tuple((t, t.regex()) for t in TAXONOMY)


def profile_terms(skills: Iterable[tuple[str, SkillCategory, list[str]]]) -> list[SkillTerm]:
    """Extra terms from the user's own profile skills (name, category, aliases) not already known.

    Short names (<= 2 chars) are matched case-sensitively to avoid hitting ordinary words.
    """
    known = {n.casefold() for t in TAXONOMY for n in (t.name, *t.aliases)}
    out = []
    for name, category, aliases in skills:
        if name.casefold() in known:
            continue
        out.append(_t(name, category, *aliases, case_sensitive=len(name) <= 2))
    return out


@dataclass(frozen=True)
class TermHit:
    term: SkillTerm
    start: int
    end: int


def find_terms(text: str, extra: Iterable[SkillTerm] = (), terms: Optional[Iterable[SkillTerm]] = None) -> list[TermHit]:
    """All non-overlapping term hits in ``text``, preferring the longest match at each position."""
    if terms is None:
        compiled = [*_compiled_taxonomy(), *((t, t.regex()) for t in extra)]
    else:
        compiled = [(t, t.regex()) for t in terms]
    hits = [TermHit(t, m.start(), m.end()) for t, rx in compiled for m in rx.finditer(text) if m.end() > m.start()]
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    chosen: list[TermHit] = []
    for h in hits:
        if chosen and h.start < chosen[-1].end:
            continue
        chosen.append(h)
    return chosen


def lookup(name: str, extra: Iterable[SkillTerm] = ()) -> Optional[SkillTerm]:
    """Return the term whose name or alias equals ``name`` (case-insensitive), if any."""
    key = name.strip().casefold()
    for t in (*TAXONOMY, *extra):
        if key in {n.casefold() for n in (t.name, *t.aliases)}:
            return t
    return None


# Related-but-different terms: (hub, spokes). Evidence of a related term can make a
# requirement "partial" but never "supported". Relations are hub<->spoke only, so
# two spokes (e.g. PyTorch and TensorFlow) are never treated as related.
_RELATED_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Machine Learning", ("Deep Learning", "scikit-learn", "XGBoost", "LightGBM", "MLOps", "Feature Engineering")),
    ("Deep Learning", ("PyTorch", "TensorFlow", "Keras", "Transformers")),
    ("Natural Language Processing", ("spaCy", "NLTK", "Transformers", "Hugging Face", "Large Language Models")),
    ("Computer Vision", ("OpenCV",)),
    ("Large Language Models", ("Generative AI", "Prompt Engineering", "Fine-tuning", "Retrieval-Augmented Generation",
                               "LangChain", "LlamaIndex", "OpenAI API", "Anthropic API", "Hugging Face")),
    ("Retrieval-Augmented Generation", ("Vector Databases", "Embeddings", "LangChain", "LlamaIndex")),
    ("Vector Databases", ("FAISS", "Pinecone", "Weaviate", "Chroma", "Milvus", "Elasticsearch")),
    ("MLOps", ("MLflow", "Kubeflow", "Weights & Biases", "SageMaker", "Vertex AI")),
    ("SQL", ("PostgreSQL", "MySQL", "BigQuery", "Snowflake", "Redshift")),
    ("Data Warehousing", ("Snowflake", "BigQuery", "Redshift", "dbt")),
    ("ETL", ("ELT", "Data Pipelines", "Apache Airflow", "dbt")),
    ("Apache Spark", ("PySpark", "Databricks", "Hadoop")),
    ("Docker", ("Kubernetes",)),
    ("Microservices", ("Docker", "Kubernetes", "REST APIs")),
    ("REST APIs", ("FastAPI", "Flask", "Django", "Spring Boot")),
    ("CI/CD", ("Jenkins", "GitHub Actions")),
    ("AWS", ("SageMaker", "Redshift", "DynamoDB")),
    ("Google Cloud", ("BigQuery", "Vertex AI")),
    ("JavaScript", ("TypeScript", "Node.js", "React", "Angular", "Vue.js")),
    ("Data Visualization", ("Tableau", "Power BI", "Looker")),
    ("Statistics", ("A/B Testing",)),
    ("Time Series Analysis", ("Forecasting",)),
    ("Agile", ("Scrum", "JIRA")),
    ("Elasticsearch", ("OpenSearch",)),
)


@lru_cache(maxsize=1)
def _related_map() -> dict[str, frozenset[str]]:
    rel: dict[str, set[str]] = {}
    for hub, spokes in _RELATED_GROUPS:
        for spoke in spokes:
            rel.setdefault(hub.casefold(), set()).add(spoke)
            rel.setdefault(spoke.casefold(), set()).add(hub)
    return {k: frozenset(v) for k, v in rel.items()}


def related_terms(name: str) -> frozenset[str]:
    """Canonical names of terms related to (but not the same as) ``name``."""
    return _related_map().get(name.casefold(), frozenset())
