"""
filters.py — Single source of truth for all job filtering logic.

Imported by: job_alert.py, company_scraper.py, jobspy_mcp_server/server.py
Do NOT duplicate these lists/regexes in other files.

Pipeline:
  Stage 1 — 7-layer regex chain (fast, zero-dependency, unchanged)
  Stage 2 — NLI zero-shot classifier (catches indirect senior language
             that slips past regex, e.g. "shipped production code for a
             few years", "beyond the learning phase", "not for freshers")
             Runs ONLY on jobs that passed Stage 1.
             Fail-open: any error → job passes through safely.
"""

import re
import threading
import logging

logger = logging.getLogger(__name__)

# ── SENIOR TITLE KEYWORDS ─────────────────────────────────────────────────────
SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", " sr ", "lead", "staff", "principal",
    "director", "head of", "vp ", "vice president", "manager",
    "architect", "consultant", "specialist ii", "level iii",
    "level 3", "level 4", "level 5", "tech lead", "team lead",
    "engineering manager", "associate director",
]

# ── OVER-EXPERIENCE KEYWORD PHRASES ───────────────────────────────────────────
# Keyword fallback — catches phrases the regex might miss
OVEREXP_DESC_KEYWORDS = [
    # 2+ years (lower bound — entry roles cap at 0-1 yr)
    "2+ years", "2 + years", "minimum 2 years", "at least 2 years",
    "2 years of experience", "2 or more years",
    # 3+ years and above
    "3+ years", "4+ years", "5+ years", "6+ years", "7+ years",
    "8+ years", "10+ years", "3 or more years", "4 or more years",
    "minimum 3 years", "minimum 4 years", "minimum 5 years",
    "at least 3 years", "at least 4 years", "at least 5 years",
    "3 years of experience", "4 years of experience",
    "5 years of experience", "6 years of experience",
    # ranges where lower bound >= 2
    "2-3 years", "2-4 years", "2-5 years",
    "3-5 years", "4-6 years", "5-7 years", "5-8 years",
    "2 to 3 years", "2 to 4 years", "2 to 5 years",
    "3 to 5 years", "4 to 6 years", "5 to 7 years",
    # seniority signals in descriptions
    "experienced engineer", "seasoned engineer",
    "proven track record of", "extensive experience",
    "industry experience of", "hands-on experience of",
    # indirect senior signals (NLI catches most, but catch easy ones in Stage 1)
    "not suitable for freshers", "not for freshers", "not a fresher role",
    "mid-level or above", "mid level or above", "mid-level and above",
    "beyond the learning phase", "strong industry background",
    "seasoned professional", "seasoned developer",
    "deep expertise", "well-versed professional",
    "proven track record in", "solid background in",
    "production experience required", "looking for someone with industry experience",
]

# ── PRE-COMPILED REGEXES ──────────────────────────────────────────────────────

# Matches "2+ years", "3 years of experience", "4-6 years", "2 to 5 years", etc.
# Catches lower bound >= 2 in ranges like "2-4 years" or "2 to 5 years".
DIGIT_EXP_RE = re.compile(
    r'(?<!\d)'                                            # not preceded by a digit
    r'([2-9]|1[0-5])'                                    # number 2-15
    r'\s*(?:\+|[-\u2013]\s*\d+|\s+to\s+\d+)?'           # optional: +, -N, to N
    r'\s*(?:years?|yrs?)'                                # years / yrs
    r'(?:\s+of)?'                                        # optional "of"
    r'(?:\s+(?:relevant|work|professional|industry|hands.on|total))?'  # qualifier
    r'\s*(?:experience)?',                               # experience (optional)
    re.IGNORECASE,
)

# Matches "two years", "three+ years of professional experience", etc.
WORD_EXP_RE = re.compile(
    r'\b(two|three|four|five|six|seven|eight|nine|ten)'
    r'\s*(?:\+\s*)?(?:years?|yrs?)'
    r'(?:\s+of)?'
    r'(?:\s+(?:relevant|work|professional|industry|hands.on|total))?'
    r'\s*experience\b',
    re.IGNORECASE,
)

# Matches LinkedIn job_level values like "Mid-Senior level", "Director", etc.
SENIOR_LEVEL_RE = re.compile(
    r'\b(mid.senior|senior|director|executive|manager|associate director)\b',
    re.IGNORECASE,
)

# Naukri URL experience range parsers
NAUKRI_EXP_RANGE_RE  = re.compile(r'-(\d+)-to-(\d+)-year')
NAUKRI_EXP_SINGLE_RE = re.compile(r'-(\d+)-year')

# Positive entry-level signals — if found, always allow through
ENTRY_LEVEL_SIGNALS_RE = re.compile(
    r'\b(0[-\u2013]1\s*years?|0\s*to\s*1\s*years?|fresher|fresh\s+graduate|'
    r'new\s+grad(uate)?|entry.level|entry\s+level|'
    r'junior\s+(?:engineer|developer|sde|swe)|associate\s+engineer|'
    r'campus\s+(?:hire|recruit)|graduate\s+engineer|'
    r'no\s+experience\s+required|0\s*\+\s*years?)\b',
    re.IGNORECASE,
)

# Safe URL prefix — only allow https:// job links in email
SAFE_URL_RE = re.compile(r'^https://', re.IGNORECASE)


# ── CORE FILTER FUNCTION ──────────────────────────────────────────────────────

def is_entry_level(
    title:       str,
    description: str,
    job_level:   str  = "",
    job_url:     str  = "",
    use_ml:      bool = True,   # set False to skip Stage 2 (e.g. benchmarking)
) -> bool:
    """
    Full 2-stage entry-level classifier.

    Stage 1: 7-layer regex chain — always runs, ~0 ms.
    Stage 2: NLI semantic filter — runs only when Stage 1 passes, ~0.5 s/job.
             Catches indirect senior language regex can't detect:
             "shipped production code for a few years",
             "beyond the learning phase", "not for freshers", etc.

    Args:
        title:       Job title string
        description: Full job description text
        job_level:   LinkedIn / scraper job level field (e.g. "Mid-Senior level")
        job_url:     Job URL (used for Naukri URL-embedded experience range)
        use_ml:      If False, skip Stage 2 (regex-only mode)

    Returns True  → entry-level, include job.
    Returns False → too senior, exclude job.
    """
    title_lower = title.lower()
    desc_lower  = description.lower()
    level_lower = job_level.lower()
    url_lower   = job_url.lower()

    # ── STAGE 1: 7-layer regex chain ────────────────────────────────

    # 1. Block senior/lead titles
    if any(kw in title_lower for kw in SENIOR_TITLE_KEYWORDS):
        return False

    # 2. Block by LinkedIn job_level field
    if SENIOR_LEVEL_RE.search(level_lower):
        return False

    # 3. Block by keyword phrases in description
    if any(kw in desc_lower for kw in OVEREXP_DESC_KEYWORDS):
        return False

    # 4. Block by digit-based experience regex
    if DIGIT_EXP_RE.search(desc_lower):
        return False

    # 5. Block by word-based experience regex
    if WORD_EXP_RE.search(desc_lower):
        return False

    # 6. Block via Naukri URL experience range
    if "naukri.com" in url_lower:
        m = NAUKRI_EXP_RANGE_RE.search(url_lower)
        if m and int(m.group(1)) >= 2:
            return False
        m2 = NAUKRI_EXP_SINGLE_RE.search(url_lower)
        if m2 and int(m2.group(1)) >= 2:
            return False

    # 7. Whitelist: confirmed entry-level signals override ambiguous descriptions
    if ENTRY_LEVEL_SIGNALS_RE.search(title) or ENTRY_LEVEL_SIGNALS_RE.search(description):
        return True   # explicit entry-level signal → skip Stage 2, always allow

    # ── STAGE 2: NLI semantic filter ────────────────────────────────
    # Runs only on jobs that passed all 7 regex layers.
    # Catches indirect senior language that regex can't see.
    # Fail-open: model error → job passes through.
    if use_ml:
        if not is_entry_level_ml(title, description):
            return False

    return True


def is_safe_url(url: str) -> bool:
    """Return True only if URL starts with https:// (safe for email href)."""
    return bool(url) and bool(SAFE_URL_RE.match(url))


# ══════════════════════════════════════════════════════════════════
# STAGE 2 — NLI SEMANTIC FILTER
# ══════════════════════════════════════════════════════════════════
#
# Model : cross-encoder/nli-deberta-v3-small  (~178 MB, CPU-only)
# Why   : Best accuracy/size ratio for zero-shot NLI on CPU.
#         DeBERTa disentangled attention handles indirect phrasing
#         ("shipped production code for a few years", "beyond the
#         learning phase") far better than BART or MiniLM.
#
# Latency: ~0.4–0.7 s/job on CPU.
#          Regex eliminates ~70-80 % first, so typically ~40-80 jobs
#          reach NLI → ~30-55 s added to a nightly run. Acceptable.
#
# Failure policy: ANY exception → return True (fail-open).
#                 A bad model load NEVER blocks a valid job.

NLI_MODEL_NAME    = "cross-encoder/nli-deberta-v3-small"
NLI_THRESHOLD     = 0.65    # FIX #5: lowered from 0.72 → 0.65 (better recall on
                            # indirect phrasing; DeBERTa NLI rarely exceeds 0.90
                            # for clear entry-level text so false-positive risk is low).
                            # To recalibrate: call calibrate_nli_threshold() below
                            # with a labelled sample, pick the threshold that gives
                            # ~95 % recall (prefer letting a senior job through over
                            # blocking a valid one).
NLI_MAX_CHARS     = 1500    # truncate desc — requirements are front/back loaded
NLI_MIN_DESC_CHARS = 80     # FIX #6: skip NLI if description is too short to judge

# Three independent hypotheses — catches different framings of seniority.
# multi_label=True means each is scored independently; ANY hit → reject.
_SENIOR_HYPOTHESES = [
    "This job requires at least 2 years of professional work experience.",
    "This position is not suitable for fresh graduates or candidates with less than 2 years experience.",
    "This role expects a candidate with a demonstrated track record in industry.",
]

# Singleton loader — thread-safe, loads model exactly once per process
_nli_pipeline  = None
_nli_available = None   # None = untested | True = loaded | False = failed
_nli_lock      = threading.Lock()


def _load_nli_model():
    """
    Lazy-loads the NLI pipeline exactly once per process.
    Thread-safe via double-checked locking.
    After first resolution, repeated calls are O(1).
    """
    global _nli_pipeline, _nli_available

    if _nli_available is True:
        return _nli_pipeline
    if _nli_available is False:
        return None

    with _nli_lock:
        if _nli_available is not None:   # recheck after acquiring lock
            return _nli_pipeline
        try:
            # FIX #3: sentencepiece is required by DeBERTa's tokenizer but is
            # not pulled in automatically by transformers on all platforms.
            # Importing it first gives a clear, actionable error message.
            try:
                import sentencepiece  # noqa: F401
            except ImportError:
                raise ImportError(
                    "sentencepiece is required for the NLI model tokenizer. "
                    "Run: pip install sentencepiece"
                )
            from transformers import pipeline as hf_pipeline
            logger.info(f"[NLI] Loading {NLI_MODEL_NAME} ...")
            _nli_pipeline = hf_pipeline(
                "zero-shot-classification",
                model=NLI_MODEL_NAME,
                device=-1,       # force CPU — portable across machines
                truncation=True,
            )
            _nli_available = True
            logger.info("[NLI] Model loaded successfully.")
        except Exception as exc:
            _nli_available = False
            logger.warning(
                f"[NLI] Could not load model ({exc}). "
                "Stage 2 disabled — only regex chain will run. "
                "Install with: pip install transformers torch sentencepiece"
            )
    return _nli_pipeline  # FIX #4: explicit return after with-block (was implicit None)


def is_entry_level_ml(title: str, description: str) -> bool:
    """
    Stage 2 NLI semantic filter.

    Returns True  → job looks entry-level (pass through).
    Returns False → model is confident this is a senior role (block).
    Returns True  → on ANY exception (fail-open — never blocks a job).

    Called only from is_entry_level() after all 7 regex layers pass.
    Can also be called standalone for testing / debugging.
    """
    model = _load_nli_model()
    if model is None:
        return True   # Model unavailable → pass through

    # FIX #6: skip NLI when description is too short to make a reliable judgment.
    # Hirist and some Naukri RSS jobs arrive with empty descriptions — NLI on
    # an empty string wastes ~0.5 s and produces noise scores near 0.33 (random).
    if len(description.strip()) < NLI_MIN_DESC_CHARS:
        return True   # not enough text → pass through (title-only block handled by Stage 1)

    try:
        desc = description.strip()
        if len(desc) > NLI_MAX_CHARS:
            # Keep head + tail: requirements appear in both sections
            half = NLI_MAX_CHARS // 2
            desc = desc[:half] + " ... " + desc[-half:]

        text   = f"Job Title: {title}\n\n{desc}"
        result = model(
            text,
            candidate_labels=_SENIOR_HYPOTHESES,
            multi_label=True,
        )

        scores_by_label = dict(zip(result["labels"], result["scores"]))
        for hypothesis, score in scores_by_label.items():
            if score >= NLI_THRESHOLD:
                logger.debug(
                    f"[NLI] BLOCKED '{title}' | "
                    f"score={score:.3f} | '{hypothesis[:55]}...'"
                )
                return False

        return True

    except Exception as exc:
        logger.warning(f"[NLI] Inference error for '{title}': {exc}. Passing through.")
        return True   # Fail open


def warmup_nli_model() -> bool:
    """
    Pre-loads and JIT-warms the NLI model.
    Call once at the top of run_job_alert() so the first real job
    doesn't pay the model-load cost during processing.

    Returns True if model loaded OK, False if unavailable.
    """
    model = _load_nli_model()
    if model is not None:
        try:
            model(
                "Software Engineer, 0-1 years experience welcome.",
                _SENIOR_HYPOTHESES[:1],
            )
            logger.info("[NLI] Warm-up inference complete.")
        except Exception:
            pass
    return _nli_available is True
