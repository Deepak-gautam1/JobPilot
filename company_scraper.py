import requests
import pandas as pd
import time
from datetime import datetime

# ── LEVER API (free, no auth needed) ────────────────────
LEVER_COMPANIES = {
    "Razorpay"  : "razorpay",
    "CRED"      : "cred",
    "Meesho"    : "meesho",
    "Swiggy"    : "swiggy",
    "Phonepe"   : "phonepe",
    "Groww"     : "groww",
    "Zepto"     : "zepto",
}

# ── GREENHOUSE API (free, no auth needed) ────────────────
GREENHOUSE_COMPANIES = {
    "Flipkart"  : "flipkart",
    "Intuit"    : "intuit",
    "Atlassian" : "atlassian",
    "Uber"      : "uber",
    "Dropbox"   : "dropbox",
    "Netflix"   : "netflix",
}

# Target role keywords to match against title/team
TARGET_ROLES = [
    "software engineer", "software developer",
    "full stack", "backend", "frontend",
    "machine learning", "data engineer",
    "sde", "swe", "python", "react",
]

# Fix #5: added pune, chennai to match job_alert.py INDIA_LOCATIONS
TARGET_LOCATIONS = [
    "india", "bangalore", "gurugram", "hyderabad",
    "mumbai", "pune", "chennai", "remote",
]


# ── RETRY HELPER (Fix #7) ────────────────────────────────
def get_with_retry(url, headers=None, timeout=10, retries=2):
    """GET with simple retry on failure."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            return resp
        except Exception as e:
            if attempt < retries:
                print(f"     ⚠️ Retry {attempt+1}/{retries} for {url[:60]}... ({e})")
                time.sleep(3)
            else:
                raise


# ── LEVER ────────────────────────────────────────────────
def fetch_lever_jobs(company_name, company_slug):
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        resp = get_with_retry(url, timeout=10)
        if resp.status_code != 200:
            return []
        jobs = resp.json()
        results = []
        for job in jobs:
            title    = job.get("text", "").lower()
            location = job.get("categories", {}).get("location", "").lower()
            team     = job.get("categories", {}).get("team", "").lower()

            if not any(r in title or r in team for r in TARGET_ROLES):
                continue
            if not any(l in location for l in TARGET_LOCATIONS):
                if "remote" not in location:
                    continue

            # Lever stores description in lists[] + additional — not a flat 'description' field
            desc_parts = [item.get("content", "") for item in job.get("lists", [])]
            desc_parts.append(job.get("additional", ""))
            description = " ".join(filter(None, desc_parts))

            results.append({
                "title"        : job.get("text"),
                "company"      : company_name,
                "location"     : job.get("categories", {}).get("location", "N/A"),
                "job_url"      : job.get("hostedUrl", ""),
                "date_posted"  : datetime.fromtimestamp(job["createdAt"]/1000).strftime("%Y-%m-%d") if job.get("createdAt") else "N/A",
                "site"         : "lever",
                "searched_role": job.get("categories", {}).get("team", "SDE"),
                "description"  : description,
                "min_amount"   : None,
                "max_amount"   : None,
                "currency"     : "INR",
                "is_remote"    : "remote" in location,
                "region"       : "foreign" if "remote" in location else "india",
                "skill_score"  : 0,
            })
        return results
    except Exception as e:
        print(f"  ⚠️ Lever error for {company_name}: {e}")
        return []


# ── GREENHOUSE ───────────────────────────────────────────
def fetch_greenhouse_jobs(company_name, company_slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
    try:
        resp = get_with_retry(url, timeout=10)
        if resp.status_code != 200:
            return []
        jobs = resp.json().get("jobs", [])
        results = []
        for job in jobs:
            title    = job.get("title", "").lower()
            location = job.get("location", {}).get("name", "").lower()

            if not any(r in title for r in TARGET_ROLES):
                continue
            if not any(l in location for l in TARGET_LOCATIONS):
                if "remote" not in location:
                    continue

            results.append({
                "title"        : job.get("title"),
                "company"      : company_name,
                "location"     : job.get("location", {}).get("name", "N/A"),
                "job_url"      : job.get("absolute_url", ""),
                "date_posted"  : job.get("updated_at", "N/A")[:10],
                "site"         : "greenhouse",
                "searched_role": "SDE",
                "description"  : job.get("content", ""),   # Greenhouse uses 'content' not 'description'
                "min_amount"   : None,
                "max_amount"   : None,
                "currency"     : "INR",
                "is_remote"    : "remote" in location,
                "region"       : "foreign" if "remote" in location else "india",
                "skill_score"  : 0,
            })
        return results
    except Exception as e:
        print(f"  ⚠️ Greenhouse error for {company_name}: {e}")
        return []


# ── AMAZON JOBS API (free, no auth) ──────────────────────
AMAZON_ROLES = [
    "software development engineer",
    "software engineer",
    "machine learning engineer",
    "data engineer",
]
AMAZON_LOCATIONS = ["Bangalore", "Hyderabad", "Gurugram"]

def fetch_amazon_jobs():
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept"    : "application/json, text/javascript, */*",
    }
    for role in AMAZON_ROLES:
        for loc in AMAZON_LOCATIONS:
            url = (
                f"https://www.amazon.jobs/en/search.json"
                f"?base_query={requests.utils.quote(role)}"
                f"&loc_query={requests.utils.quote(loc)}"
                f"&country=IND&category=software-development"
                f"&result_limit=20"
            )
            try:
                resp = get_with_retry(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                jobs = resp.json().get("jobs", [])
                for job in jobs:
                    title   = job.get("title", "").lower()
                    job_loc = job.get("location", "").lower()
                    if not any(r in title for r in TARGET_ROLES):
                        continue
                    results.append({
                        "title"        : job.get("title"),
                        "company"      : "Amazon",
                        "location"     : job.get("location", loc),
                        "job_url"      : f"https://www.amazon.jobs{job.get('job_path', '')}",
                        "date_posted"  : job.get("posted_date", "N/A")[:10] if job.get("posted_date") else "N/A",
                        "site"         : "amazon.jobs",
                        "searched_role": role,
                        "description"  : job.get("description", ""),
                        "min_amount"   : None,
                        "max_amount"   : None,
                        "currency"     : "INR",
                        "is_remote"    : "remote" in job_loc,
                        "region"       : "india",
                        "skill_score"  : 0,
                    })
            except Exception as e:
                print(f"  ⚠️ Amazon error for {role} @ {loc}: {e}")
            time.sleep(2)

    # Deduplicate by job_url
    seen, unique = set(), []
    for j in results:
        if j["job_url"] not in seen:
            seen.add(j["job_url"])
            unique.append(j)
    print(f"     ✅ {len(unique)} Amazon jobs found")
    return unique


# ── MAIN ─────────────────────────────────────────────────
def fetch_all_company_jobs():
    all_jobs = []

    print("\n🏢 Fetching from Lever companies...")
    for name, slug in LEVER_COMPANIES.items():
        print(f"  🔍 {name}...")
        jobs = fetch_lever_jobs(name, slug)
        print(f"     ✅ {len(jobs)} matching jobs")
        all_jobs.extend(jobs)

    print("\n🏢 Fetching from Greenhouse companies...")
    for name, slug in GREENHOUSE_COMPANIES.items():
        print(f"  🔍 {name}...")
        jobs = fetch_greenhouse_jobs(name, slug)
        print(f"     ✅ {len(jobs)} matching jobs")
        all_jobs.extend(jobs)

    print("\n🏢 Fetching from Amazon Jobs...")
    amazon_jobs = fetch_amazon_jobs()
    all_jobs.extend(amazon_jobs)

    return pd.DataFrame(all_jobs) if all_jobs else pd.DataFrame()
