import sys
import time
import html as html_module
import re
import smtplib
import warnings
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jobspy import scrape_jobs
from datetime import datetime
from database import init_db, save_job, is_already_seen, make_hash, get_stats, get_followup_jobs, get_weekly_stats, get_all_seen_hashes
from company_scraper import fetch_all_company_jobs

# Fix unicode/emoji encoding for Task Scheduler
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

warnings.filterwarnings("ignore", category=FutureWarning)

# ── CONFIG ───────────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

GMAIL_USER     = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
TO_EMAIL       = os.getenv("TO_EMAIL")


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

FAANG_SEARCHES = [
    "software engineer Google India",
    "SDE Amazon India entry level",
    "software engineer Microsoft Hyderabad",
    "software engineer Goldman Sachs Bangalore",
]

ALL_ROLES = ROLES


# ── LOCATIONS ────────────────────────────────────────────
# In job_alert.py INDIA_LOCATIONS — remove glassdoor
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
MIN_SALARY_INR  = 1500000
MIN_SKILL_SCORE = 5


# ── EXPERIENCE FILTERS ───────────────────────────────────
SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", " sr ", "lead", "staff", "principal",
    "director", "head of", "vp ", "vice president", "manager",
    "architect", "consultant", "specialist ii", "level iii",
    "level 3", "level 4", "level 5",
]

OVEREXP_DESC_KEYWORDS = [
    "3+ years", "4+ years", "5+ years", "6+ years", "7+ years",
    "8+ years", "10+ years", "3 or more years", "4 or more years",
    "minimum 3 years", "minimum 4 years", "minimum 5 years",
    "at least 3 years", "at least 4 years", "at least 5 years",
    "3 years of experience", "4 years of experience",
    "5 years of experience", "6 years of experience",
    "3-5 years", "4-6 years", "5-7 years", "5-8 years",
    "3 to 5 years", "4 to 6 years", "5 to 7 years",
    "experienced engineer", "seasoned engineer",
    "proven track record of", "extensive experience",
]

RESULTS_PER_SEARCH = 10


# ── PRE-COMPILE REGEX ────────────────────────────────────
DIGIT_EXP_RE = re.compile(
    r'\b([2-9]|1[0-5])\s*(?:\+|-\s*\d+|\s+to\s+\d+)?\s*'
    r'(?:years?|yrs?)(?:\s+of)?\s*(?:relevant\s+|work\s+|professional\s+)?experience\b'
)
WORD_EXP_RE = re.compile(
    r'\b(two|three|four|five|six|seven|eight|nine|ten)\s*'
    r'(?:years?|yrs?)(?:\s+of)?\s*(?:relevant\s+|work\s+|professional\s+)?experience\b'
)
NAUKRI_EXP_RANGE_RE  = re.compile(r'-(\d+)-to-(\d+)-year')
NAUKRI_EXP_SINGLE_RE = re.compile(r'-(\d+)-year')


# ── HELPERS ──────────────────────────────────────────────
_BOUNDARY_SKILLS = {"ai", "gpt", "sql", "git", "rag", "llm"}


def skill_match_score(job):
    text = " ".join([
        str(job.get("title", "")),
        str(job.get("description", "")),
    ]).lower()
    matched = []
    for s in MY_SKILLS:
        if s in _BOUNDARY_SKILLS:
            if re.search(rf'\b{re.escape(s)}\b', text):
                matched.append(s)
        else:
            if s in text:
                matched.append(s)
    return round((len(matched) / len(MY_SKILLS)) * 100, 1), matched


def salary_ok(job):
    min_amt  = job.get("min_amount")
    currency = str(job.get("currency", "USD")).upper()
    region   = str(job.get("region", "")).lower()
    try:
        if pd.isna(min_amt):
            return region == "india"
        if currency == "INR":
            return float(min_amt) >= MIN_SALARY_INR
        return float(min_amt) >= MIN_SALARY_USD
    except (TypeError, ValueError):
        return region == "india"


def is_entry_level(job):
    title = str(job.get("title", "")).lower()
    desc  = str(job.get("description", "")).lower()
    level = str(job.get("job_level", "")).lower()
    url   = str(job.get("job_url", "")).lower()

    if any(kw in title for kw in SENIOR_TITLE_KEYWORDS):
        return False
    if any(kw in level for kw in ["senior", "mid-senior", "director", "manager", "lead"]):
        return False
    if any(kw in desc for kw in OVEREXP_DESC_KEYWORDS):
        return False
    if DIGIT_EXP_RE.search(desc):
        return False
    if WORD_EXP_RE.search(desc):
        return False
    if "naukri.com" in url:
        m = NAUKRI_EXP_RANGE_RE.search(url)
        if m and int(m.group(1)) >= 2:
            return False
        m2 = NAUKRI_EXP_SINGLE_RE.search(url)
        if m2 and int(m2.group(1)) >= 2:
            return False
    return True


def not_seen_filter(df, seen_hashes):
    """Remove jobs already in DB using pre-loaded in-memory hash set."""
    def not_seen(job):
        h = make_hash(
            str(job.get("job_url", "")),
            str(job.get("title", "")),
            str(job.get("company", ""))
        )
        return h not in seen_hashes
    before = len(df)
    df = df[df.apply(not_seen, axis=1)]
    print(f"🔁 Removed {before - len(df)} already-seen | ✨ New: {len(df)}")
    return df


def fetch_jobs_for_location(role, loc_config, fetch_linkedin_desc=False, retries=2):
    """Scrape jobs with simple retry on network errors."""
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
            return df
        except Exception as e:
            if attempt < retries:
                print(f"     ⚠️ Retry {attempt+1}/{retries} ({e})")
                time.sleep(5)
            else:
                print(f"     ❌ Failed after {retries+1} attempts: {e}")
                return pd.DataFrame()


# ── MAIN FETCH ───────────────────────────────────────────
def fetch_top_jobs():
    india_dfs   = []
    foreign_dfs = []
    seen_combos = set()
    run_start   = time.time()

    seen_hashes = get_all_seen_hashes()
    print(f"🗃️  Loaded {len(seen_hashes)} seen job hashes from DB")

    # ── FIX 3a: updated section label (Naukri moved to RSS scraper) ──
    t0 = time.time()
    print("\n🔍 [1/4] Regular searches (Indeed / Glassdoor / Google)...")
    for role in ALL_ROLES:
        for loc in INDIA_LOCATIONS:
            print(f"  India: {role} @ {loc['location']}...")
            df = fetch_jobs_for_location(role, loc)
            if not df.empty:
                df["searched_role"] = role
                df["region"]        = "india"
                india_dfs.append(df)
                print(f"     {len(df)} results")
            time.sleep(5)

        for loc in FOREIGN_LOCATIONS:
            key = (role, loc["location"])
            if key in seen_combos:
                continue
            seen_combos.add(key)
            print(f"  Foreign: {role} @ {loc['location']}...")
            df = fetch_jobs_for_location(role, loc)
            if not df.empty:
                df["searched_role"] = role
                df["region"]        = "foreign"
                foreign_dfs.append(df)
                print(f"     {len(df)} results")
            time.sleep(5)
    print(f"⏱️  Section done in {(time.time()-t0)/60:.1f} min")

    t0 = time.time()
    print("\n🏢 [2/4] FAANG searches (Bangalore + Hyderabad)...")
    for role in FAANG_SEARCHES:
        for loc in FAANG_LOCATIONS:
            print(f"  FAANG: {role} @ {loc['location']}...")
            df = fetch_jobs_for_location(role, loc)
            if not df.empty:
                df["searched_role"] = role
                df["region"]        = "india"
                india_dfs.append(df)
                print(f"     {len(df)} results")
            time.sleep(5)
    print(f"⏱️  Section done in {(time.time()-t0)/60:.1f} min")

    # ── FIX 4: removed duplicate comment line ──
    t0 = time.time()
    print("\n🔵 [3/4] LinkedIn India searches (with descriptions)...")
    for role in ALL_ROLES:
        for loc in LINKEDIN_INDIA_LOCATIONS:
            print(f"  LinkedIn IN: {role} @ {loc['location']}...")
            df = fetch_jobs_for_location(role, loc, fetch_linkedin_desc=True)
            if not df.empty:
                df["searched_role"] = role
                df["region"]        = "india"
                india_dfs.append(df)
                print(f"     {len(df)} results")
            time.sleep(8)
    print(f"⏱️  Section done in {(time.time()-t0)/60:.1f} min")

    def process(dfs):
        if not dfs:
            return pd.DataFrame()
        combined = pd.concat(dfs, ignore_index=True)
        combined = combined.drop_duplicates(subset=["job_url"], keep="first")
        combined = combined[combined.apply(salary_ok, axis=1)]
        combined = combined[combined.apply(is_entry_level, axis=1)]
        combined["skill_score"] = combined.apply(lambda j: skill_match_score(j)[0], axis=1)
        combined = combined[combined["skill_score"] >= MIN_SKILL_SCORE]
        if "max_amount" in combined.columns:
            combined["max_amount"] = pd.to_numeric(combined["max_amount"], errors="coerce").fillna(0)
        else:
            combined["max_amount"] = 0
        combined = combined.sort_values(["skill_score", "max_amount"], ascending=[False, False])
        return combined

    india_final   = process(india_dfs)
    foreign_final = process(foreign_dfs)

    top_india   = india_final.head(12)  if not india_final.empty   else pd.DataFrame()
    top_foreign = foreign_final.head(8) if not foreign_final.empty else pd.DataFrame()
    print(f"\n🇮🇳 India jobs selected:   {len(top_india)}")
    print(f"🌍 Foreign jobs selected: {len(top_foreign)}")

    # ── FIX 3b: updated section label + FIX 1: head(10) ──
    t0 = time.time()
    print("\n🏢 [4/4] Direct career pages (Amazon · Lever · Greenhouse · Naukri RSS · Instahyre · Hirist · Wellfound)...")
    company_df = fetch_all_company_jobs()
    if not company_df.empty:
        company_df["from_company_scraper"] = True
        company_df = company_df[company_df.apply(is_entry_level, axis=1)]
        company_df["skill_score"] = company_df.apply(lambda j: skill_match_score(j)[0], axis=1)
        company_df = company_df[company_df["skill_score"] >= MIN_SKILL_SCORE]
        # FIX 1: increased from head(5) → head(10) for 6 sources now
        top_company = company_df.sort_values("skill_score", ascending=False).head(10)
        print(f"  {len(top_company)} company jobs after filter")
    else:
        top_company = pd.DataFrame()
        print("  No company jobs found")
    print(f"⏱️  Section done in {(time.time()-t0)/60:.1f} min")

    all_parts = [x for x in [top_india, top_foreign, top_company] if not x.empty]
    if not all_parts:
        print("No jobs found from any source.")
        return pd.DataFrame()

    final = pd.concat(all_parts, ignore_index=True)
    if "from_company_scraper" not in final.columns:
        final["from_company_scraper"] = False
    else:
        final["from_company_scraper"] = final["from_company_scraper"].fillna(False)

    final = not_seen_filter(final, seen_hashes)

    india_count   = len(final[final["region"] == "india"])   if "region" in final.columns else 0
    foreign_count = len(final[final["region"] == "foreign"]) if "region" in final.columns else 0
    print(f"\n✅ Final — India: {india_count} | Foreign: {foreign_count} | Total: {len(final)}")
    print(f"⏱️  Total runtime: {(time.time()-run_start)/60:.1f} min")
    return final


# ── EMAIL ────────────────────────────────────────────────
def build_followup_section():
    """Build HTML section for jobs needing follow-up (applied 7+ days ago, no stage update)."""
    followups = get_followup_jobs(days=7)
    if not followups:
        return ""
    cards = ""
    for row in followups:
        id_, title, company, location, url, date_applied, notes = row
        days_ago = ""
        try:
            from datetime import date
            d = date.fromisoformat(date_applied)
            days_ago = f"{(date.today() - d).days} days ago"
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

    # FIX 2: all keys lowercase — role_tag.strip().lower() lookup works correctly
    # for both "AI engineer" (from ROLES) and "ai engineer" (from scrapers)
    role_colors = {
        "software engineer"        : ("#e8f5e9", "#1b5e20"),
        "full stack developer"     : ("#e3f2fd", "#0d47a1"),
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
            skill_sc  = float(job.get("skill_score", 0))

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

            bar_color = "#4caf50" if skill_sc >= 50 else "#ff9800" if skill_sc >= 25 else "#f44336"
            skill_bar = f"""
            <div style="margin:6px 0 4px;">
              <span style="font-size:11px;color:#666;">Resume Match: <b>{skill_sc}%</b></span>
              <div style="background:#eee;border-radius:4px;height:6px;margin-top:3px;">
                <div style="background:{bar_color};width:{min(skill_sc,100)}%;height:6px;border-radius:4px;"></div>
              </div>
            </div>"""

            remote_badge = (
                '<span style="background:#e3f2fd;color:#1565c0;padding:3px 8px;border-radius:10px;font-size:11px;font-weight:bold;">Remote</span>'
                if is_remote else
                '<span style="background:#fce4ec;color:#c62828;padding:3px 8px;border-radius:10px;font-size:11px;font-weight:bold;">On-site</span>'
            )

            # FIX 2: use .strip().lower() so "AI engineer" → "ai engineer" matches dict key
            rbg, rclr = role_colors.get(role_tag.strip().lower(), ("#f5f5f5", "#333"))

            apply_btn = (
                f'<a href="{job_url}" style="display:inline-block;background:#1b5e20;color:white;'
                f'padding:9px 20px;border-radius:8px;text-decoration:none;font-size:13px;'
                f'font-weight:bold;margin-top:10px;">Apply Now</a>'
                if job_url else
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
          <p style="margin:2px 0;font-size:12px;opacity:0.9;">Min Rs.15L/yr or $22K/yr | Under 2yr exp | Resume-matched</p>
          <p style="margin:4px 0 0;font-size:11px;opacity:0.75;">Skills: Python, React, Azure, RAG, FastAPI, TypeScript, ML</p>
        </div>
        {build_weekly_summary_section()}
        {build_followup_section()}
        {india_section}
        {foreign_section}
        <!-- FIX 5: updated footer to include all sources -->
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
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
        print("Crash alert email sent.")
    except Exception as e:
        print(f"Could not send crash email: {e}")


# ── RUN ──────────────────────────────────────────────────
def run_job_alert():
    init_db()

    print(f"\n{'='*52}")
    print(f"Job Alert - {datetime.now().strftime('%d %b %Y %I:%M %p')}")
    print(f"{'='*52}")

    try:
        df = fetch_top_jobs()

        saved = sum(1 for _, job in df.iterrows() if save_job(job, sent=True))
        print(f"💾 Saved {saved} new jobs to database")

        stats = get_stats()
        print(f"📊 DB Stats - Total: {stats['total']} | Applied: {stats['applied']} | Pending: {stats['pending']} | Skipped: {stats['skipped']}")

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
