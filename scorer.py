"""
scorer.py — Semantic scoring engine for JobPilot.

Replaces pure keyword matching with a 3-component weighted score:

  Component          Weight  Why
  ─────────────────  ──────  ──────────────────────────────────────────────────
  Semantic score      45 %   SentenceTransformer cosine similarity to resume.
                             Understands context — "builds LLM pipelines"
                             scores high even without exact keyword hits.
  Keyword score       35 %   Existing regex skill-match (fast, high precision).
                             Kept as a hard gate AND a scoring component.
  Recency score       20 %   Exponential decay — jobs posted today score 100,
                             jobs 7 days old score ~50. Newer = still open.

  final = 0.45*semantic + 0.35*keyword + 0.20*recency   (all components 0–100)

Why SentenceTransformers over OpenAI embeddings?
  - Zero API cost, works fully offline, no latency jitter or rate limits.
  - all-MiniLM-L6-v2: 90 MB download, ~200 ms for 200 jobs on CPU (batched).
  - Quality is excellent for relevance ranking (not NLI classification).
  - Falls back gracefully to 0.0 per job if not installed — system still works
    on keyword + recency alone.

Install: pip install sentence-transformers
"""

import threading
import logging
import numpy as np
import pandas as pd
from datetime import datetime, date

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# RESUME ANCHOR — update whenever your skills or target roles change.
# More detail here = better separation between relevant and irrelevant jobs.
# ══════════════════════════════════════════════════════════════════════════════

RESUME_TEXT = """
Deepak Gautam — Software Engineer / AI Engineer / Machine Learning Engineer /
Full Stack Developer / Backend Developer / Data Engineer.

Technical skills: Python, TypeScript, JavaScript, C#, SQL, C++.
Frameworks: React, Next.js, Node.js, FastAPI, TensorFlow, Keras, scikit-learn,
pandas, LangChain. Cloud and DevOps: Azure, Docker, Git, GitHub Actions, Vercel,
Supabase. Concepts: RAG pipelines, LLM applications, Generative AI, GPT models,
REST API design, System Design, Agile, Machine Learning, Deep Learning.

Target roles: Software Engineer, Full Stack Developer, Machine Learning Engineer,
AI Engineer, Backend Developer Python, Data Engineer.

Job preferences: Entry-level or 0-1 year experience roles. Locations: Gurugram,
Bangalore, Mumbai, Pune, Chennai India or Remote or Singapore. Interested in
AI-powered product engineering, intelligent backend systems, LLM integrations,
data pipelines, full-stack web applications, and cloud-native development.
""".strip()


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

EMBED_MODEL_NAME    = "all-MiniLM-L6-v2"  # 90 MB; best speed/quality for CPU
EMBED_BATCH_SIZE    = 64                   # jobs per encoding batch
EMBED_MAX_CHARS     = 2000                 # chars per job text before tokenization

# Score weights — must sum to 1.0
W_SEMANTIC = 0.45
W_KEYWORD  = 0.35
W_RECENCY  = 0.20

# Recency: exponential decay half-life in days
# score = 100 × 0.5^(days_old / HALF_LIFE)
# 0 days → 100,  7 days → ~50,  14 days → 25,  21 days → 12.5
RECENCY_HALF_LIFE_DAYS = 7.0

# Score for jobs where date_posted is missing or unparseable (neutral, not zero —
# we don't want to unfairly penalise scrapers that don't expose dates).
RECENCY_UNKNOWN_SCORE = 40.0


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON MODEL LOADER  (thread-safe, loads exactly once per process)
# ══════════════════════════════════════════════════════════════════════════════

_embed_model      = None
_resume_embedding = None        # pre-computed; reused for every scoring run
_embed_available  = None        # None = untested | True = loaded | False = failed
_embed_lock       = threading.Lock()


def _load_embed_model():
    """
    Lazy-load the SentenceTransformer model and pre-encode the resume text.
    Thread-safe via double-checked locking — O(1) after first call.
    Returns the model instance, or None if unavailable.
    """
    global _embed_model, _resume_embedding, _embed_available

    if _embed_available is True:
        return _embed_model
    if _embed_available is False:
        return None

    with _embed_lock:
        if _embed_available is not None:   # re-check inside lock
            return _embed_model
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"[EMBED] Loading {EMBED_MODEL_NAME} ...")
            _embed_model = SentenceTransformer(EMBED_MODEL_NAME)

            # Encode the resume once — reused for every job comparison.
            # normalize_embeddings=True: L2-normalise so dot product = cosine similarity.
            _resume_embedding = _embed_model.encode(
                RESUME_TEXT,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            _embed_available = True
            logger.info("[EMBED] Model loaded and resume encoded successfully.")

        except ImportError:
            _embed_available = False
            logger.warning(
                "[EMBED] sentence-transformers not installed — semantic scoring disabled. "
                "Install: pip install sentence-transformers"
            )
        except Exception as exc:
            _embed_available = False
            logger.warning(f"[EMBED] Could not load model ({exc}) — semantic scoring disabled.")

    return _embed_model


def warmup_embed_model() -> bool:
    """
    Pre-load and JIT-warm the embedding model.
    Called in a background daemon thread at startup so the first real job
    batch doesn't pay the one-time load cost (~10–15 s on first run ever,
    <1 s on subsequent runs once model is cached on disk).
    Returns True if model loaded OK, False otherwise.
    """
    model = _load_embed_model()
    if model is not None:
        try:
            model.encode(
                "Software engineer entry level Python React LLM",
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            logger.info("[EMBED] Warm-up inference complete.")
        except Exception:
            pass
    return _embed_available is True


# ══════════════════════════════════════════════════════════════════════════════
# SEMANTIC SCORING
# ══════════════════════════════════════════════════════════════════════════════

def compute_semantic_scores(df: pd.DataFrame) -> pd.Series:
    """
    Batch-encode all job texts and return cosine similarity to resume (0–100).

    Title is concatenated twice so the model gives it more weight relative to
    the description — a job titled "ML Engineer" should rank higher than one
    that mentions ML once in a 2000-word description.

    Falls back to pd.Series(0.0) silently if model is unavailable.
    """
    model = _load_embed_model()
    if model is None:
        return pd.Series(0.0, index=df.index)

    try:
        titles = (
            df.get("title",       pd.Series("", index=df.index))
              .fillna("").astype(str)
        )
        descs = (
            df.get("description", pd.Series("", index=df.index))
              .fillna("").astype(str)
              .str[:EMBED_MAX_CHARS]
        )
        # title × 2 + description gives title roughly 2× the weight of desc
        texts = (titles + " " + titles + " " + descs).tolist()

        # Batch-encode all jobs in one call — SentenceTransformers handles
        # internal micro-batching efficiently.
        job_embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=EMBED_BATCH_SIZE,
            show_progress_bar=False,
        )  # shape: (n_jobs, embedding_dim)

        # Cosine similarity: both vectors are L2-normalised, so dot = cosine.
        # _resume_embedding shape: (embedding_dim,) → matmul → (n_jobs,)
        scores = (job_embeddings @ _resume_embedding) * 100.0
        scores = np.clip(scores, 0.0, 100.0).round(1)

        return pd.Series(scores, index=df.index)

    except Exception as exc:
        logger.warning(f"[EMBED] Batch scoring failed ({exc}) — returning zeros.")
        return pd.Series(0.0, index=df.index)


# ══════════════════════════════════════════════════════════════════════════════
# RECENCY SCORING
# ══════════════════════════════════════════════════════════════════════════════

def compute_recency_scores(df: pd.DataFrame) -> pd.Series:
    """
    Convert date_posted to a 0–100 recency score using exponential decay.
    score = 100 × 0.5^(days_old / RECENCY_HALF_LIFE_DAYS)

    Missing/unparseable dates → RECENCY_UNKNOWN_SCORE (neutral, not zero).
    """
    today    = date.today()
    scores   = []
    date_col = df.get("date_posted", pd.Series("", index=df.index)).fillna("")

    for val in date_col:
        try:
            s = str(val).strip()
            if not s or s in ("N/A", "nan", "None", ""):
                scores.append(RECENCY_UNKNOWN_SCORE)
                continue
            # Handle ISO datetime ("2025-03-01T00:00:00") and plain date ("2025-03-01")
            s        = s.split("T")[0][:10]
            d        = datetime.strptime(s, "%Y-%m-%d").date()
            days_old = max(0, (today - d).days)
            score    = 100.0 * (0.5 ** (days_old / RECENCY_HALF_LIFE_DAYS))
            scores.append(round(min(100.0, score), 1))
        except Exception:
            scores.append(RECENCY_UNKNOWN_SCORE)

    return pd.Series(scores, index=df.index)


# ══════════════════════════════════════════════════════════════════════════════
# COMPOSITE FINAL SCORE
# ══════════════════════════════════════════════════════════════════════════════

def compute_final_scores(
    df:             pd.DataFrame,
    keyword_scores: pd.Series,
) -> pd.Series:
    """
    Weighted composite: 0.45×semantic + 0.35×keyword + 0.20×recency (0–100).

    Args:
        df:             DataFrame with 'title', 'description', 'date_posted'.
        keyword_scores: Pre-computed keyword match scores (0–100), index-aligned to df.

    Why pass keyword_scores in rather than recomputing them here?
        batch_skill_scores() is already called in process() as a hard gate
        before this function is called. Passing the result avoids running the
        same vectorised regex pass twice.

    Returns:
        pd.Series of final scores (0–100), 1 decimal place, aligned to df.index.
    """
    semantic = compute_semantic_scores(df)
    recency  = compute_recency_scores(df)

    # Use .values on keyword_scores to avoid pandas index-alignment surprises
    # when df was reset_index'd after fuzzy_dedup or filtering.
    final = (
        W_SEMANTIC * semantic.values
        + W_KEYWORD  * keyword_scores.values
        + W_RECENCY  * recency.values
    )
    final = np.clip(np.round(final, 1), 0.0, 100.0)
    return pd.Series(final, index=df.index)
