import os
import sys
import time
import html as html_module
import re
import smtplib
import warnings
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date as date_type
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jobspy import scrape_jobs
from database import init_db, save_job, make_hash, get_stats, get_followup_jobs, get_weekly_stats, get_all_seen_hashes
from company_scraper import fetch_all_company_jobs
from filters import is_entry_level as _filter_is_entry_level, is_safe_url, warmup_nli_model

# Fix unicode/emoji encoding for Task Scheduler
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

warnings.filterwarnings("ignore", category=FutureWarning)

# ── CONFIG ───────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

GMAIL_USER     = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
TO_EMAIL       = os.getenv("TO_EMAIL")

import scorer  # noqa: E402  — semantic scoring engine (scorer.py)


# ── RESUME SKILLS ────────────────────────────────────────
MY_SKILLS = [
    "python", "c#", "javascript", "typescript", "sql", "c++",
    "react", "next.js", "node.js", "fastapi", "tensorflow",
    "keras", "scikit-learn", "pandas", "langchain",
    "azure", "docker", "git", "github actions", "vercel", "supabase",
    "rag", "rest api", "system design", "agile", "llm",
    "generative ai", "gpt", "ai", "machine learning",
]


# ── ROLES ────────────────────────────────────────────────
ROLES = [
    "software engineer",
    "machine learning engineer",
    "AI engineer",
    "backend developer python",
    "data engineer",
]

# FAANG_SEARCHES: do NOT embed location names ("India", "Hyderabad") in the
# search term — jobspy passes them to the country_indeed parser and may mis-
# interpret them as country strings (causing "Invalid country: bolivia" errors
# from fuzzy-matching). Location is handled separately via FAANG_LOCATIONS.
FAANG_SEARCHES = [
    "software engineer Google",
    "SDE Amazon entry level",
    "software engineer Microsoft",
    "software engineer Goldman Sachs",
]

ALL_ROLES = ROLES


# ── LOCATIONS ────────────────────────────────────────────
INDIA_LOCATIONS = [
    {"location": "Gurugram, India",  "country_indeed": "india", "sites": ["indeed", "google"], "hours_old": 72},
    {"location": "Bangalore, India", "country_indeed": "india", "sites": ["indeed", "google"], "hours_old": 72},
    {"location": "Mumbai, India",    "country_indeed": "india", "sites": ["indeed", "google"], "hours_old": 72},
    {"location": "Pune, India",      "country_indeed": "india", "sites": ["indeed", "google"], "hours_old": 72},
    {"location": "Chennai, India",   "country_indeed": "india", "sites": ["indeed", "google"], "hours_old": 72},
]

FOREIGN_LOCATIONS = [
    {"location": "Remote",     "country_indeed": "usa",       "sites": ["indeed", "google", "linkedin"], "hours_old": 24},
    {"location": "Singapore",  "country_indeed": "singapore", "sites": ["indeed", "google", "linkedin"], "hours_old": 24},
]
FAANG_LOCATIONS = [
    {"location": "Bangalore, India", "country_indeed": "india", "sites": ["indeed", "google", "linkedin"], "hours_old": 72},
    {"location": "Hyderabad, India", "country_indeed": "india", "sites": ["indeed", "google", "linkedin"], "hours_old": 72},
]
LINKEDIN_INDIA_LOCATIONS = [
    {"location": "Gurugram, India",  "country_indeed": "india", "sites": ["linkedin"], "hours_old": 72},
    {"location": "Bangalore, India", "country_indeed": "india", "sites": ["linkedin"], "hours_old": 72},
    {"location": "Mumbai, India",    "country_indeed": "india", "sites": ["linkedin"], "hours_old": 72},
    {"location": "Pune, India",      "country_indeed": "india", "sites": ["linkedin"], "hours_old": 72},
    {"location": "Chennai, India",   "country_indeed": "india", "sites": ["linkedin"], "hours_old": 72},
    {"location": "Hyderabad, India", "country_indeed": "india", "sites": ["linkedin"], "hours_old": 72},
]


# ── SALARY MINIMUMS ──────────────────────────────────────
MIN_SALARY_USD  = 22000
MIN_SALARY_INR  = 1200000
MIN_SKILL_SCORE = 5


# ── SEARCH CONFIG ────────────────────────────────────────
RESULTS_PER_SEARCH = 10
MAX_WORKERS        = 8   # concurrent HTTP threads — tune down if rate-limited
# All filter constants and regexes live in filters.py — do not duplicate here.

# Thread-safe print lock — prevents interleaved output from parallel workers
_print_lock = threading.Lock()
def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


# ══ SCRAPE CACHE ────────────────────────────────────────────
# File-based cache so repeated test runs don't re-scrape within the TTL.
# Key = MD5 of (role, location, sites, hours_old). Value = {ts, rows_json}.
# Descriptions are truncated to 2 KB before caching to keep the file small.
import json as _json
import hashlib as _hlib

_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".scrape_cache.json")
_CACHE_TTL  = 3600       # seconds — cache valid for 1 hour
_cache_lock = threading.Lock()


def _scrape_key(role: str, loc_config: dict, fetch_linkedin_desc: bool) -> str:
    raw = "|".join([
        role.lower(),
        loc_config["location"].lower(),
        ",".join(sorted(loc_config["sites"])),
        str(loc_config.get("hours_old", 24)),
        str(fetch_linkedin_desc),
    ])
    return _hlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> pd.DataFrame | None:
    """Return cached DataFrame if key exists and is not expired, else None."""
    with _cache_lock:
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = _json.load(f)
        except Exception:
            return None
        entry = cache.get(key)
        if not entry or time.time() - entry["ts"] > _CACHE_TTL:
            return None
        try:
            return pd.read_json(entry["data"], orient="records")
        except Exception:
            return None


def _cache_set(key: str, df: pd.DataFrame) -> None:
    """Store a scrape result. Truncates descriptions and evicts expired entries."""
    with _cache_lock:
        try:
            try:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    cache = _json.load(f)
            except Exception:
                cache = {}
            # Truncate descriptions before storing (keeps file manageable)
            d = df.copy()
            if "description" in d.columns:
                d["description"] = d["description"].fillna("").astype(str).str[:2000]
            cache[key] = {"ts": time.time(), "data": d.to_json(orient="records")}
            # Evict expired entries so the file doesn't grow unbounded
            now = time.time()
            cache = {k: v for k, v in cache.items() if now - v["ts"] <= _CACHE_TTL}
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                _json.dump(cache, f)
        except Exception:
            pass  # cache write failure is always non-fatal


# ══ FUZZY DEDUP ────────────────────────────────────────────
# MD5 dedup only catches exact URL/title/company matches.
# Fuzzy dedup catches near-duplicates: "Python Engineer" vs "Engineer (Python)"
# at the same company. Operates on the current batch only (not DB — too slow).
# Sorted by final_score first so the better-scored duplicate is always kept.

def fuzzy_dedup(df: pd.DataFrame, threshold: int = 88) -> pd.DataFrame:
    """
    Remove near-duplicate jobs using token_sort_ratio on title+company.
    Requires: pip install rapidfuzz   (skipped gracefully if not installed).
    threshold=88: catches obvious rewrites; raise to 92 to be more conservative.
    """
    try:
        from rapidfuzz.fuzz import token_sort_ratio
    except ImportError:
        return df  # optional dep — skip silently

    if len(df) < 2:
        return df

    # Sort descending so the highest-scoring duplicate is always kept
    score_col = "final_score" if "final_score" in df.columns else "skill_score"
    df = df.sort_values(score_col, ascending=False).reset_index(drop=True)

    # Build fingerprints: "title company"
    fp = (
        df.get("title",   pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
        + " "
        + df.get("company", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    ).tolist()

    keep, dropped = [], 0
    for i, sig in enumerate(fp):
        if any(token_sort_ratio(sig, fp[j]) >= threshold for j in keep):
            dropped += 1
        else:
            keep.append(i)

    if dropped:
        tprint(f"🔀 Fuzzy dedup: removed {dropped} near-duplicate jobs")
    return df.iloc[keep].reset_index(drop=True)


# ── SKILL MATCHING ───────────────────────────────────────
# Pre-compile one word-boundary regex per skill at import time.
# Using \b for ALL skills fixes loose matches like "python" hitting "cpython".
# Patterns are compiled once and reused across every batch call.
_SKILL_PATTERNS: list[tuple[str, re.Pattern]] = [
    (skill, re.compile(rf'\b{re.escape(skill)}\b', re.IGNORECASE))
    for skill in MY_SKILLS
]
_SKILL_COUNT = len(MY_SKILLS)


def batch_skill_scores(df: pd.DataFrame) -> pd.Series:
    """
    Vectorized skill scorer — processes all rows at once instead of row-by-row.

    Strategy:
      1. Concatenate title + description into one text column (vectorized).
      2. For each skill regex, run Series.str.contains() across all rows at once.
      3. Sum the boolean columns → hit count per row → percentage.

    Returns a float Series (0.0–100.0) aligned with df's index.
    """
    # Build combined text column — fillna prevents NaN from breaking str ops
    text = (
        df.get("title",       pd.Series("", index=df.index)).fillna("").astype(str)
        + " "
        + df.get("description", pd.Series("", index=df.index)).fillna("").astype(str)
    ).str.lower()

    # One boolean column per skill, then sum → hit count per row
    hits = sum(
        text.str.contains(pattern, regex=True, na=False).astype(int)
        for _, pattern in _SKILL_PATTERNS
    )

    return (hits / _SKILL_COUNT * 100).round(1)


def skill_match_score(job) -> tuple[float, list[str]]:
    """
    Single-row scorer kept for backwards compatibility (MCP server, manual calls).
    Returns (score_float, matched_skills_list).
    """
    text = (
        str(job.get("title", "")) + " " + str(job.get("description", ""))
    ).lower()
    matched = [
        skill for skill, pattern in _SKILL_PATTERNS
        if pattern.search(text)
    ]
    return round(len(matched) / _SKILL_COUNT * 100, 1), matched


def salary_ok(job):
    min_amt  = job.get("min_amount")
    currency = str(job.get("currency", "USD")).upper()
    region   = str(job.get("region", "")).lower()
    try:
        if pd.isna(min_amt):
            # FIX: allow undisclosed salary for ALL regions, not just India.
            # Most foreign/remote jobs on Indeed & Google don't include salary.
            # Blocking them here eliminated ALL foreign results every run.
            return True
        if currency == "INR":
            return float(min_amt) >= MIN_SALARY_INR
        return float(min_amt) >= MIN_SALARY_USD
    except (TypeError, ValueError):
        return True  # undisclosed → allow through, skill score will rank them lower


def is_entry_level(job) -> bool:
    """Thin wrapper — delegates to filters.is_entry_level (single source of truth)."""
    return _filter_is_entry_level(
        title       = str(job.get("title", "")),
        description = str(job.get("description", "")),
        job_level   = str(job.get("job_level", "")),
        job_url     = str(job.get("job_url", "")),
    )


def not_seen_filter(df: pd.DataFrame, seen_hashes: set) -> pd.DataFrame:
    """
    Vectorized dedup — removes jobs whose hash is already in the DB.

    Old approach: df.apply(row-by-row) calling make_hash() per row (slow).
    New approach:
      1. Build the three key columns as string Series (vectorized fillna + astype).
      2. Concatenate them with '|' separator (vectorized string add).
      3. Lower + strip (vectorized).
      4. Compute MD5 via a single .map(hashlib.md5) call — far fewer Python
         object creations than calling make_hash() once per row.
      5. Use .isin(seen_hashes) for a vectorized set lookup — O(n) not O(n*k).
    """
    import hashlib as _hashlib

    urls      = df.get("job_url", pd.Series("", index=df.index)).fillna("").astype(str)
    titles    = df.get("title",   pd.Series("", index=df.index)).fillna("").astype(str)
    companies = df.get("company", pd.Series("", index=df.index)).fillna("").astype(str)

    # Build raw fingerprint strings vectorized, then hash each with MD5
    raw = (urls + "|" + titles + "|" + companies).str.lower().str.strip()
    hashes = raw.map(lambda s: _hashlib.md5(s.encode()).hexdigest())

    mask   = ~hashes.isin(seen_hashes)
    before = len(df)
    df     = df[mask]
    tprint(f"🔁 Removed {before - len(df)} already-seen | ✨ New: {len(df)}")
    return df


def fetch_jobs_for_location(role, loc_config, fetch_linkedin_desc=False, retries=2):
    """Scrape jobs with cache + simple retry on network errors. Thread-safe."""
    # Check cache first — avoids redundant HTTP requests during repeated test runs
    cache_key = _scrape_key(role, loc_config, fetch_linkedin_desc)
    cached    = _cache_get(cache_key)
    if cached is not None and not cached.empty:
        tprint(f"     💾 Cache hit: {role} @ {loc_config['location']}")
        return cached

    for attempt in range(retries + 1):
        try:
            df = scrape_jobs(
                search_term                = role,
                location                   = loc_config["location"],
                site_name                  = loc_config["sites"],
                country_indeed             = loc_config["country_indeed"],
                results_wanted             = RESULTS_PER_SEARCH,
                hours_old                  = loc_config.get("hours_old", 24),
                linkedin_fetch_description = fetch_linkedin_desc,
                verbose                    = 0,
            )
            if not df.empty:
                _cache_set(cache_key, df)   # persist for next run within TTL
            return df
        except Exception as e:
            if attempt < retries:
                tprint(f"     ⚠️ Retry {attempt+1}/{retries} ({e})")
                time.sleep(5)
            else:
                tprint(f"     ❌ Failed after {retries+1} attempts: {e}")
                return pd.DataFrame()


# ── CONCURRENT WORKER ────────────────────────────────────
def _run_search(task):
    """
    Worker executed in thread pool.
    task = (role, loc_config, region_tag, fetch_linkedin_desc)
    Returns (region_tag, df).
    """
    role, loc_config, region_tag, fetch_linkedin_desc = task
    tprint(f"  -> {region_tag}: {role} @ {loc_config['location']}")
    df = fetch_jobs_for_location(role, loc_config, fetch_linkedin_desc=fetch_linkedin_desc)
    if not df.empty:
        df["searched_role"] = role
        df["region"]        = region_tag
        tprint(f"     + {len(df)} results ({role} @ {loc_config['location']})")
    return region_tag, df


# ── MAIN FETCH ───────────────────────────────────────────
def fetch_top_jobs():
    india_dfs   = []
    foreign_dfs = []
    run_start   = time.time()

    seen_hashes = get_all_seen_hashes()
    tprint(f"🗃️  Loaded {len(seen_hashes)} seen job hashes from DB")

    # Build task lists upfront
    regular_tasks = []
    seen_foreign  = set()
    for role in ALL_ROLES:
        for loc in INDIA_LOCATIONS:
            regular_tasks.append((role, loc, "india", False))
        for loc in FOREIGN_LOCATIONS:
            key = (role, loc["location"])
            if key not in seen_foreign:
                seen_foreign.add(key)
                regular_tasks.append((role, loc, "foreign", False))
    for role in FAANG_SEARCHES:
        for loc in FAANG_LOCATIONS:
            regular_tasks.append((role, loc, "india", False))

    linkedin_tasks = [
        (role, loc, "india", True)
        for role in ALL_ROLES
        for loc in LINKEDIN_INDIA_LOCATIONS
    ]

    # Sections 1+2 — Indeed/Google/FAANG in parallel
    t0 = time.time()
    tprint(f"\n🔍 [1-2/4] {len(regular_tasks)} Indeed/Google/FAANG searches "
           f"({MAX_WORKERS} threads)...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run_search, t): t for t in regular_tasks}
        for future in as_completed(futures):
            try:
                region_tag, df = future.result()
                if not df.empty:
                    (india_dfs if region_tag == "india" else foreign_dfs).append(df)
            except Exception as exc:
                tprint(f"     ❌ Worker error: {exc}")
    tprint(f"⏱️  Sections 1-2 done in {(time.time()-t0)/60:.1f} min")

    # Section 3 — LinkedIn with smaller pool (rate-limit friendly)
    t0 = time.time()
    tprint(f"\n🔵 [3/4] {len(linkedin_tasks)} LinkedIn searches (4 threads)...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_search, t): t for t in linkedin_tasks}
        for future in as_completed(futures):
            try:
                _, df = future.result()
                if not df.empty:
                    india_dfs.append(df)
            except Exception as exc:
                tprint(f"     ❌ LinkedIn worker error: {exc}")
    tprint(f"⏱️  Section 3 done in {(time.time()-t0)/60:.1f} min")

    def process(dfs):
        if not dfs:
            return pd.DataFrame()
        combined = pd.concat(dfs, ignore_index=True)
        combined = combined.drop_duplicates(subset=["job_url"], keep="first")
        combined = combined[combined.apply(salary_ok, axis=1)]
        combined = combined[combined.apply(is_entry_level, axis=1)]

        # ── STEP 1: Keyword score (fast, vectorized — same as before) ──────
        # Kept as a hard gate: jobs with zero keyword overlap are not relevant.
        combined["keyword_score"] = batch_skill_scores(combined)
        combined["skill_score"]   = combined["keyword_score"]  # DB backward compat
        combined = combined[combined["keyword_score"] >= MIN_SKILL_SCORE]

        if combined.empty:
            return combined

        # ── STEP 2: Semantic score (SentenceTransformer cosine similarity) ──
        # Understands context — "builds LLM pipelines" scores high even without
        # exact keywords. Falls back to 0.0 per job if model is unavailable.
        combined["semantic_score"] = scorer.compute_semantic_scores(combined)

        # ── STEP 3: Composite final score ─────────────────────────────
        # final = 0.45*semantic + 0.35*keyword + 0.20*recency  (all 0–100)
        combined["final_score"] = scorer.compute_final_scores(
            combined, combined["keyword_score"]
        )

        # ── STEP 4: Fuzzy dedup (removes near-duplicate titles at same company) ─
        # Requires rapidfuzz; skipped gracefully if not installed.
        combined = fuzzy_dedup(combined)

        if "max_amount" in combined.columns:
            combined["max_amount"] = pd.to_numeric(combined["max_amount"], errors="coerce").fillna(0)
        else:
            combined["max_amount"] = 0

        # Sort by composite score first, then salary as tiebreaker
        combined = combined.sort_values(["final_score", "max_amount"], ascending=[False, False])
        return combined

    india_final   = process(india_dfs)
    foreign_final = process(foreign_dfs)
    top_india   = india_final.head(12)  if not india_final.empty   else pd.DataFrame()
    top_foreign = foreign_final.head(8) if not foreign_final.empty else pd.DataFrame()
    tprint(f"\n🇮🇳 India jobs selected:   {len(top_india)}")
    tprint(f"🌍 Foreign jobs selected: {len(top_foreign)}")

    # Section 4 — Company scrapers (concurrent inside fetch_all_company_jobs)
    t0 = time.time()
    tprint("\n🏢 [4/4] Direct career pages (Amazon · Lever · Greenhouse · "
           "Naukri RSS · Instahyre · Hirist · Wellfound)...")
    company_df = fetch_all_company_jobs()
    if not company_df.empty:
        company_df["from_company_scraper"] = True
        company_df = company_df[company_df.apply(is_entry_level, axis=1)]
        company_df["keyword_score"]  = batch_skill_scores(company_df)
        company_df["skill_score"]    = company_df["keyword_score"]
        company_df = company_df[company_df["keyword_score"] >= MIN_SKILL_SCORE]
        if not company_df.empty:
            company_df["semantic_score"] = scorer.compute_semantic_scores(company_df)
            company_df["final_score"]    = scorer.compute_final_scores(
                company_df, company_df["keyword_score"]
            )
            company_df = fuzzy_dedup(company_df)
        top_company = company_df.sort_values("final_score", ascending=False).head(10)
        tprint(f"  {len(top_company)} company jobs after filter")
    else:
        top_company = pd.DataFrame()
        tprint("  No company jobs found")
    tprint(f"⏱️  Section 4 done in {(time.time()-t0)/60:.1f} min")

    all_parts = [x for x in [top_india, top_foreign, top_company] if not x.empty]
    if not all_parts:
        tprint("No jobs found from any source.")
        return pd.DataFrame()

    final = pd.concat(all_parts, ignore_index=True)
    if "from_company_scraper" not in final.columns:
        final["from_company_scraper"] = False
    else:
        final["from_company_scraper"] = final["from_company_scraper"].fillna(False)

    final = not_seen_filter(final, seen_hashes)

    india_count   = len(final[final["region"] == "india"])   if "region" in final.columns else 0
    foreign_count = len(final[final["region"] == "foreign"]) if "region" in final.columns else 0
    tprint(f"\n✅ Final — India: {india_count} | Foreign: {foreign_count} | Total: {len(final)}")
    tprint(f"⏱️  Total runtime: {(time.time()-run_start)/60:.1f} min")
    return final


# ── EMAIL ────────────────────────────────────────────────
def build_followup_section():
    """Build HTML for jobs needing follow-up (applied 7+ days ago, no stage update)."""
    followups = get_followup_jobs(days=7)
    if not followups:
        return ""
    cards = ""
    for row in followups:
        id_, title, company, location, url, date_applied, notes = row
        days_ago = ""
        try:
            d = date_type.fromisoformat(date_applied)
            days_ago = f"{(date_type.today() - d).days} days ago"
        except Exception:
            days_ago = date_applied
        cards += f"""
        <div style="background:#fff8e1;border-radius:10px;padding:12px 16px;margin-bottom:8px;
                    border-left:5px solid #f9a825;">
          <p style="margin:0;font-size:14px;font-weight:bold;color:#333;">{title}</p>
          <p style="margin:2px 0;font-size:12px;color:#666;">{company} &nbsp;·&nbsp; {location}</p>
          <p style="margin:2px 0;font-size:11px;color:#888;">Applied: {date_applied} ({days_ago}) &nbsp;·&nbsp; No response yet</p>
          {f'<p style="margin:2px 0;font-size:11px;color:#555;">Notes: {notes}</p>' if notes else ''}
          <a href="{url}" style="font-size:12px;color:#1565c0;">View Job</a>
        </div>"""
    return f"""
    <div style="background:#fff3cd;border-radius:10px;padding:10px 14px;margin:16px 0 10px;">
      <h2 style="margin:0;font-size:16px;color:#856404;">⏰ Follow-Up Needed ({len(followups)})</h2>
      <p style="margin:4px 0 0;font-size:11px;color:#856404;">Applied 7+ days ago with no update — consider following up!</p>
    </div>
    {cards}"""


def build_weekly_summary_section():
    """Build HTML weekly stats section."""
    s = get_weekly_stats()
    response_rate = round((s['oas'] + s['interviews']) / max(s['applied_week'], 1) * 100)
    return f"""
    <div style="background:#e8eaf6;border-radius:12px;padding:16px 20px;margin:16px 0;">
      <h2 style="margin:0 0 10px;font-size:16px;color:#283593;">📊 Weekly Summary (Last 7 Days)</h2>
      <table style="width:100%;font-size:13px;border-collapse:collapse;">
        <tr>
          <td style="padding:4px 8px;color:#444;">🆕 New jobs found</td>
          <td style="padding:4px 8px;font-weight:bold;color:#1a237e;">{s['new_jobs']}</td>
          <td style="padding:4px 8px;color:#444;">✅ Applied</td>
          <td style="padding:4px 8px;font-weight:bold;color:#2e7d32;">{s['applied_week']}</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#444;">📝 OAs received</td>
          <td style="padding:4px 8px;font-weight:bold;color:#e65100;">{s['oas']}</td>
          <td style="padding:4px 8px;color:#444;">🎤 Interviews</td>
          <td style="padding:4px 8px;font-weight:bold;color:#6a1b9a;">{s['interviews']}</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#444;">🎉 Offers</td>
          <td style="padding:4px 8px;font-weight:bold;color:#1b5e20;">{s['offers']}</td>
          <td style="padding:4px 8px;color:#444;">❌ Rejections</td>
          <td style="padding:4px 8px;font-weight:bold;color:#c62828;">{s['rejected']}</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#444;">💬 Response Rate</td>
          <td colspan="3" style="padding:4px 8px;font-weight:bold;color:#283593;">{response_rate}% (OA + Interview / Applied)</td>
        </tr>
      </table>
    </div>"""


def build_email_html(df):
    date_str = datetime.now().strftime("%d %b %Y")

    if df.empty:
        return f"""<!DOCTYPE html><html>
        <head><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
        <body style="font-family:Arial,sans-serif;padding:20px;background:#f4f4f4;">
        <div style="max-width:600px;margin:auto;background:#fff;border-radius:12px;padding:24px;text-align:center;">
          <h2 style="color:#1a237e;">Job Alert - {date_str}</h2>
          <p style="color:#888;">No new matching jobs found today. Check tomorrow!</p>
        </div></body></html>"""

    india_jobs   = df[df["region"] == "india"]   if "region" in df.columns else df
    foreign_jobs = df[df["region"] == "foreign"] if "region" in df.columns else pd.DataFrame()

    role_colors = {
        "software engineer"        : ("#e8f5e9", "#1b5e20"),
        "machine learning engineer": ("#f3e5f5", "#6a1b9a"),
        "ai engineer"              : ("#fce4ec", "#880e4f"),
        "backend developer python" : ("#fff8e1", "#f57f17"),
        "data engineer"            : ("#fff3e0", "#e65100"),
    }

    def make_cards(subset, flag):
        cards = ""
        for i, (_, job) in enumerate(subset.iterrows(), 1):
            title     = html_module.escape(str(job.get("title",    "N/A")))
            company   = html_module.escape(str(job.get("company",  "N/A")))
            location  = html_module.escape(str(job.get("location", "N/A") or "Remote"))
            is_direct = bool(job.get("from_company_scraper", False))
            source    = html_module.escape(str(job.get("site", "N/A")).title())
            job_url   = str(job.get("job_url", ""))
            posted    = str(job.get("date_posted", "N/A"))
            is_remote = job.get("is_remote", False)
            role_tag  = str(job.get("searched_role", ""))
            currency  = str(job.get("currency", "USD")).upper()
            keyword_sc  = float(job.get("keyword_score",  job.get("skill_score", 0)))
            semantic_sc = float(job.get("semantic_score", 0))
            final_sc    = float(job.get("final_score",    keyword_sc))

            try:
                if pd.notna(job.get("min_amount")) and pd.notna(job.get("max_amount")):
                    sym    = "Rs." if currency == "INR" else "$"
                    salary = f'{sym}{float(job["min_amount"]):,.0f} - {sym}{float(job["max_amount"]):,.0f} / yr'
                    salary_color = "#2e7d32"
                else:
                    salary = "Salary not disclosed"
                    salary_color = "#999"
            except Exception:
                salary = "Salary not disclosed"
                salary_color = "#999"

            bar_color = "#4caf50" if final_sc >= 55 else "#ff9800" if final_sc >= 35 else "#f44336"
            skill_bar = f"""
            <div style="margin:6px 0 4px;">
              <span style="font-size:12px;color:#333;font-weight:bold;">Match Score: {final_sc:.0f}%</span>
              <div style="background:#eee;border-radius:4px;height:7px;margin:3px 0 4px;">
                <div style="background:{bar_color};width:{min(final_sc,100):.0f}%;height:7px;border-radius:4px;"></div>
              </div>
              <span style="font-size:10px;color:#999;">Semantic: {semantic_sc:.0f}% &nbsp;&bull;&nbsp; Keywords: {keyword_sc:.0f}%</span>
            </div>"""

            remote_badge = (
                '<span style="background:#e3f2fd;color:#1565c0;padding:3px 8px;border-radius:10px;font-size:11px;font-weight:bold;">Remote</span>'
                if is_remote else
                '<span style="background:#fce4ec;color:#c62828;padding:3px 8px;border-radius:10px;font-size:11px;font-weight:bold;">On-site</span>'
            )

            rbg, rclr = role_colors.get(role_tag.strip().lower(), ("#f5f5f5", "#333"))

            apply_btn = (
                f'<a href="{html_module.escape(job_url)}" style="display:inline-block;background:#1b5e20;color:white;'
                f'padding:9px 20px;border-radius:8px;text-decoration:none;font-size:13px;'
                f'font-weight:bold;margin-top:10px;">Apply Now</a>'
                if is_safe_url(job_url) else
                '<span style="color:#ccc;font-size:12px;">No link</span>'
            )

            cards += f"""
            <div style="background:#fff;border-radius:12px;padding:16px 18px;margin-bottom:12px;
                        box-shadow:0 2px 6px rgba(0,0,0,0.08);border-left:5px solid #1565c0;">
              <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;margin-bottom:4px;">
                <p style="margin:0;font-size:15px;font-weight:bold;color:#1a1a1a;">{flag} #{i} {title}</p>
                {remote_badge}
              </div>
              <p style="margin:0 0 4px;font-size:13px;color:#444;">
                <b>{company}</b> &nbsp;
                <span style="background:{rbg};color:{rclr};padding:1px 8px;border-radius:10px;font-size:11px;">{role_tag.title()}</span>
              </p>
              <p style="margin:3px 0;font-size:12px;color:#888;">{location} - {posted} - {source}{' &nbsp;<span style="background:#e8f5e9;color:#1b5e20;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:bold;">🏢 Direct</span>' if is_direct else ''}</p>
              {skill_bar}
              <p style="margin:6px 0 4px;font-size:15px;font-weight:bold;color:{salary_color};">{salary}</p>
              {apply_btn}
            </div>"""
        return cards

    india_cards   = make_cards(india_jobs,   "🇮🇳")
    foreign_cards = make_cards(foreign_jobs, "🌍")

    india_section = f"""
        <div style="background:#e8f5e9;border-radius:10px;padding:10px 14px;margin:16px 0 10px;">
          <h2 style="margin:0;font-size:16px;color:#1b5e20;">🇮🇳 India Jobs ({len(india_jobs)})</h2>
        </div>
        {india_cards}""" if not india_jobs.empty else ""

    foreign_section = f"""
        <div style="background:#e3f2fd;border-radius:10px;padding:10px 14px;margin:16px 0 10px;">
          <h2 style="margin:0;font-size:16px;color:#0d47a1;">🌍 Foreign / Remote Jobs ({len(foreign_jobs)})</h2>
        </div>
        {foreign_cards}""" if not foreign_jobs.empty else ""

    return f"""<!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width,initial-scale=1.0">
      <meta charset="UTF-8">
    </head>
    <body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,sans-serif;">
      <div style="max-width:600px;margin:0 auto;padding:16px;">
        <div style="background:linear-gradient(135deg,#1a237e,#1565c0);border-radius:14px;
                    padding:22px 24px;margin-bottom:16px;color:white;">
          <h1 style="margin:0 0 6px;font-size:20px;">Deepak's Job Alerts - {date_str}</h1>
          <p style="margin:2px 0;font-size:12px;opacity:0.9;">India: {len(india_jobs)} | Foreign: {len(foreign_jobs)}</p>
          <p style="margin:2px 0;font-size:12px;opacity:0.9;">Min Rs.12L/yr or $22K/yr | Under 2yr exp | Resume-matched</p>
          <p style="margin:4px 0 0;font-size:11px;opacity:0.75;">Skills: Python, React, Azure, RAG, FastAPI, TypeScript, ML</p>
        </div>
        {build_weekly_summary_section()}
        {build_followup_section()}
        {india_section}
        {foreign_section}
        <div style="text-align:center;padding:14px;font-size:11px;color:#aaa;">
          Resume-matched via JobSpy · Amazon · Lever · Greenhouse · Naukri RSS · Instahyre · Hirist · Wellfound | {datetime.now().strftime("%I:%M %p")} IST
        </div>
      </div>
    </body>
    </html>"""


def send_email(html_body, job_count):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Alert: {job_count} New Matches - {datetime.now().strftime('%d %b %Y')}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print(f"✅ Email sent at {datetime.now().strftime('%I:%M %p')}")


def send_crash_email(error_msg):
    """Send a plain-text crash alert so you know when the script fails."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[JOB ALERT CRASH] {datetime.now().strftime('%d %b %Y %I:%M %p')}"
        msg["From"]    = GMAIL_USER
        msg["To"]      = TO_EMAIL
        body = f"Job alert script crashed at {datetime.now()}\n\nError:\n{error_msg}"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
        print("Crash alert email sent.")
    except Exception as e:
        print(f"Could not send crash email: {e}")


# ── RUN ──────────────────────────────────────────────────
def run_job_alert():
    init_db()

    # FIX #1: warmup runs in a daemon thread so it truly overlaps with scraping.
    # Previously it blocked here for ~15 s before fetch_top_jobs() even started.
    # The NLI singleton uses a threading.Lock() so it’s safe to load in parallel;
    # any job that reaches is_entry_level_ml() before warmup finishes will simply
    # wait on the lock for the remaining load time — worst case a few seconds, not 15.
    # Both heavy models load in background threads so scraping starts immediately.
    # They'll be ready before scoring runs (scraping takes ~5 min).
    _warmup_t = threading.Thread(target=warmup_nli_model,         daemon=True, name="nli-warmup")
    _embed_t  = threading.Thread(target=scorer.warmup_embed_model, daemon=True, name="embed-warmup")
    _warmup_t.start()
    _embed_t.start()
    print("[NLI]   Stage 2 filter  loading in background (nli-deberta-v3-small)...")
    print("[EMBED] Semantic scorer loading in background (all-MiniLM-L6-v2)...")

    # Fail fast — don't spend 30 min scraping then crash at email send
    missing = [k for k, v in {"GMAIL_USER": GMAIL_USER, "GMAIL_PASSWORD": GMAIL_PASSWORD,
                               "TO_EMAIL": TO_EMAIL}.items() if not v]
    if missing:
        print(f"💥 Missing required env vars: {', '.join(missing)}")
        print("   Check your .env file and try again.")
        sys.exit(1)

    print(f"\n{'='*52}")
    print(f"Job Alert - {datetime.now().strftime('%d %b %Y %I:%M %p')}")
    print(f"{'='*52}")

    try:
        df = fetch_top_jobs()

        saved = sum(1 for _, job in df.iterrows() if save_job(job, sent=True))
        print(f"💾 Saved {saved} new jobs to database")

        stats = get_stats()
        print(f"📊 DB Stats - Total: {stats['total']} | Applied: {stats['applied']} | "
              f"Pending: {stats['pending']} | Skipped: {stats['skipped']}")

        print(f"\n📧 Sending email with {len(df)} jobs...")
        html = build_email_html(df)
        send_email(html, len(df))
        print(f"{'='*52}\n")

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"💥 CRASH: {err}")
        send_crash_email(err)


# ── TEST MODE ────────────────────────────────────────────
if __name__ == "__main__":
    print("Running job alert test...")
    run_job_alert()
    print("Done! Check your inbox.")
    sys.exit(0)
