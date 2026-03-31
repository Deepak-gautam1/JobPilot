import requests
import pandas as pd
import time
import json
from datetime import datetime
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# Cloudscraper bypasses Cloudflare — install with: pip install cloudscraper
try:
    import cloudscraper as _cloudscraper
    _CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    _CLOUDSCRAPER_AVAILABLE = False

from filters import is_entry_level as _is_entry_level_filter

def _is_entry_level_scraper(title: str, description: str) -> bool:
    """Delegates to filters.is_entry_level — single source of truth."""
    return _is_entry_level_filter(title=title, description=description)

# ── LEVER API ────────────────────────────────────────────
LEVER_COMPANIES = {
    "Razorpay": "razorpay", "CRED": "cred", "Meesho": "meesho",
    "Swiggy": "swiggy", "Phonepe": "phonepe", "Groww": "groww", "Zepto": "zepto",
    "Postman": "postman", "BrowserStack": "browserstack", "Hasura": "hasura",
}

# ── GREENHOUSE API ───────────────────────────────────────
GREENHOUSE_COMPANIES = {
    "Flipkart": "flipkart", "Intuit": "intuit", "Atlassian": "atlassian",
    "Uber": "uber", "Dropbox": "dropbox", "Netflix": "netflix",
    "Stripe": "stripe", "Twilio": "twilio", "Notion": "notion",
}

TARGET_ROLES = [
    "software engineer", "software developer", "full stack", "backend", "frontend",
    "machine learning", "data engineer", "sde", "swe", "python", "react",
    "ai engineer", "ml engineer", "platform engineer", "devops",
]
TARGET_LOCATIONS = [
    "india", "bangalore", "gurugram", "hyderabad", "mumbai", "pune", "chennai", "remote",
]


# ── RETRY HELPER ─────────────────────────────────────────
def get_with_retry(url, headers=None, timeout=10, retries=2):
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


def deduplicate_jobs(jobs_list):
    seen, unique = set(), []
    for j in jobs_list:
        if j["job_url"] not in seen:
            seen.add(j["job_url"])
            unique.append(j)
    return unique


# ── INSTAHYRE ────────────────────────────────────────────
INSTAHYRE_SKILLS = ["python", "react", "machine learning", "data engineer", "backend"]

_INSTAHYRE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/122.0.0.0 Safari/537.36")

def _instahyre_session() -> requests.Session:
    """
    Prime an Instahyre session by visiting the homepage first.
    This sets the necessary cookies that the API endpoint requires.
    Without this step the API returns 404.
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": _INSTAHYRE_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    for warmup_url in (
        "https://www.instahyre.com/",
        "https://www.instahyre.com/search-jobs/",
    ):
        try:
            s.get(warmup_url, timeout=10)
            time.sleep(0.8)
        except Exception:
            pass
    # Switch to JSON API headers after warmup
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.instahyre.com/search-jobs/",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def fetch_instahyre_jobs():
    results = []
    session = _instahyre_session()  # prime cookies first
    for skill in INSTAHYRE_SKILLS:
        url = (
            f"https://www.instahyre.com/api/v1/opportunities?"
            f"keywords={requests.utils.quote(skill)}&limit=15"
        )
        try:
            resp = session.get(url, timeout=12)
            if resp.status_code == 404:
                # 404 usually means no cookie/session — print hint but continue
                print(f"     ⚠️ Instahyre {skill}: HTTP 404 (session may have expired — retrying with fresh session)")
                session = _instahyre_session()
                try:
                    resp = session.get(url, timeout=12)
                except Exception:
                    pass
            if resp.status_code != 200:
                print(f"     ⚠️ Instahyre {skill}: HTTP {resp.status_code}")
                continue
            data = resp.json()
            opportunities = data if isinstance(data, list) else data.get("objects", data.get("opportunities", []))
            for opp in opportunities:
                job = opp.get("job", opp)
                employer = opp.get("employer", {})
                title = job.get("title", job.get("candidate_title", ""))
                if not any(r in title.lower() for r in TARGET_ROLES):
                    continue
                location_list = job.get("locations", [])
                location = location_list[0].get("name", "India") if location_list else "India"
                raw_date = job.get("created_at", job.get("updated_at", ""))
                date_posted = raw_date[:10] if raw_date else "N/A"
                job_id = job.get("id", "")
                slug = job.get("slug", title.lower().replace(" ", "-"))
                description = job.get("description", "")
                if not _is_entry_level_scraper(title, description):
                    continue
                results.append({
                    "title": title,
                    "company": employer.get("company_name", opp.get("company_name", "N/A")),
                    "location": location,
                    "job_url": f"https://www.instahyre.com/job-{job_id}-{slug}/",
                    "date_posted": date_posted,
                    "site": "instahyre",
                    "searched_role": skill,
                    "description": description,
                    "min_amount": None, "max_amount": None,
                    "currency": "INR", "is_remote": job.get("is_work_from_home", False),
                    "region": "india", "skill_score": 0,
                })
            print(f"     ✅ Instahyre {skill}: {len(opportunities)} results")
        except Exception as e:
            print(f"     ⚠️ Instahyre error for {skill}: {e}")
        time.sleep(2)
    unique = deduplicate_jobs(results)
    print(f"     ✅ {len(unique)} Instahyre jobs total (deduplicated)")
    return unique


# ── HIRIST ───────────────────────────────────────────────
def fetch_hirist_jobs():
    results = []
    # Broader UA + Accept to avoid bot-detection 403
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/122.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.hirist.tech/",
    }
    hirist_roles = [
        "software-engineer", "full-stack-developer", "machine-learning-engineer",
        "python-developer", "data-engineer", "ai-engineer", "backend-developer",
    ]
    for role in hirist_roles:
        url = f"https://www.hirist.tech/k/{role}-jobs"
        try:
            resp = get_with_retry(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"     ⚠️ Hirist {role}: HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # ── Multi-strategy selector: try each in priority order ──
            # Strategy 1: common class-based card selectors
            cards = (
                soup.select("div.jobCard") or
                soup.select("li.jobCard") or
                soup.select("[class*='job-card']") or
                soup.select("[class*='jobCard']")
            )

            # Strategy 2: article tags (common in React/Next.js sites)
            if not cards:
                cards = soup.select("article") or soup.select("article[class*='job']")

            # Strategy 3: any <li> inside a jobs list container
            if not cards:
                container = (
                    soup.select_one("ul.jobs-list, ul.job-list, ol.jobs-list,"
                                    " [class*='jobs-list'], [class*='jobsList'],"
                                    " [class*='results']")
                )
                if container:
                    cards = container.find_all("li", recursive=False)

            # Strategy 4: any div/li that contains both a link and looks like a card
            if not cards:
                cards = [
                    el for el in soup.select("div, li")
                    if el.find("a") and el.find("a", href=True)
                    and any(kw in el.get_text(" ", strip=True).lower()
                            for kw in ["engineer", "developer", "python", "data", "backend", "ai", "ml"])
                ][:20]

            if not cards:
                # Debug dump — save first 4 KB of HTML to help diagnose
                import os
                dump_path = os.path.join(os.path.dirname(__file__), "hirist_debug.html")
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write(resp.text[:8000])
                print(f"     ⚠️ Hirist {role}: no cards found — debug HTML saved to hirist_debug.html")
                continue

            count_before = len(results)
            _hirist_sample_logged = False  # log first card structure once per role
            for card in cards[:15]:
                # Broad title selector — try many patterns
                title_el = (
                    card.select_one("a[class*='title']") or
                    card.select_one("h1 a, h2 a, h3 a, h4 a") or
                    card.select_one(".job-title, .jobtitle, [class*='title']") or
                    card.select_one("[class*='title']") or  # non-anchor title divs
                    card.select_one("h1, h2, h3, h4")      # bare headings (no link needed)
                )
                # Broad company selector
                company_el = (
                    card.select_one("[class*='company']") or
                    card.select_one("[class*='employer']") or
                    card.select_one("[class*='org']")
                )
                # Location selector
                loc_el = (
                    card.select_one("[class*='location']") or
                    card.select_one("[class*='city']") or
                    card.select_one("[class*='place']")
                )
                # Link — prefer /j/ pattern, fallback to any <a>
                link_el = (
                    card.select_one("a[href*='/j/']") or
                    card.select_one("a[href*='/job']") or
                    card.select_one("a[href]")
                )
                if not title_el:
                    if not _hirist_sample_logged:
                        print(f"     🔍 Hirist debug — no title_el. Card HTML: {str(card)[:300]}")
                        _hirist_sample_logged = True
                    continue
                title = title_el.get_text(strip=True)
                if not title:
                    continue
                # Debug: log first extracted title per role so we can verify selectors
                if not _hirist_sample_logged:
                    print(f"     🔍 Hirist sample title: '{title}'")
                    _hirist_sample_logged = True
                company  = company_el.get_text(strip=True) if company_el else "N/A"
                location = loc_el.get_text(strip=True)    if loc_el     else "India"
                href     = link_el["href"]                if link_el    else ""
                job_url  = href if href.startswith("http") else f"https://www.hirist.tech{href}"
                if not any(r.replace("-", " ") in title.lower() for r in TARGET_ROLES):
                    continue
                if not _is_entry_level_scraper(title, ""):
                    continue
                results.append({
                    "title": title, "company": company, "location": location,
                    "job_url": job_url, "date_posted": "N/A",
                    "site": "hirist", "searched_role": role.replace("-", " "),
                    "description": "",
                    "min_amount": None, "max_amount": None,
                    "currency": "INR", "is_remote": "remote" in location.lower(),
                    "region": "india", "skill_score": 0,
                })
            added = len(results) - count_before
            print(f"     ✅ Hirist {role}: {len(cards)} cards found, {added} passed filters")
        except Exception as e:
            print(f"     ⚠️ Hirist error for {role}: {e}")
        time.sleep(2)
    unique = deduplicate_jobs(results)
    print(f"     ✅ {len(unique)} Hirist jobs total (deduplicated)")
    return unique


# ── WELLFOUND ────────────────────────────────────────────
WELLFOUND_SEARCHES = [
    ("software-engineer", "india"),
    ("python-developer",  "india"),
    ("machine-learning",  "india"),
    ("backend-developer", "india"),
    ("ai-engineer",       "india"),
    ("data-engineer",     "india"),
]

def fetch_wellfound_jobs():
    results = []
    # Wellfound uses Cloudflare — cloudscraper handles the JS challenge automatically.
    # Fallback to plain requests if not installed (will likely 403).
    if _CLOUDSCRAPER_AVAILABLE:
        scraper = _cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
    else:
        print("     ⚠️ cloudscraper not installed — Wellfound will likely 403.")
        print("        Run: pip install cloudscraper   to fix this.")
        scraper = requests.Session()
        scraper.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })

    for role, loc in WELLFOUND_SEARCHES:
        url = f"https://wellfound.com/role/l/{role}/{loc}"
        try:
            resp = scraper.get(url, timeout=20)
            if resp.status_code != 200:
                print(f"     ⚠️ Wellfound blocked (Status: {resp.status_code}) for {role}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            script_tag = soup.find("script", id="__NEXT_DATA__")
            if not script_tag:
                print(f"     ⚠️ Wellfound: No __NEXT_DATA__ found for {role}")
                continue
            data = json.loads(script_tag.string)
            apollo_state = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("apolloState", {})
                    .get("data", {})
            )
            count = 0
            for key, node in apollo_state.items():
                if not isinstance(node, dict):
                    continue
                if node.get("__typename") != "JobListing":
                    continue
                title = node.get("title", "")
                if not title or not any(r in title.lower() for r in TARGET_ROLES):
                    continue
                startup_ref  = node.get("startup", {})
                startup_key  = startup_ref.get("__ref", "")
                startup_node = apollo_state.get(startup_key, {})
                company      = startup_node.get("name", "Startup (via Wellfound)")
                job_url      = node.get("jobUrl") or node.get("remoteUrl", "")
                if not job_url:
                    listing_slug = node.get("slug", key.replace("JobListing:", ""))
                    job_url = f"https://wellfound.com/jobs/{listing_slug}"
                description = node.get("description", "")
                if not _is_entry_level_scraper(title, description):
                    continue
                results.append({
                    "title": title, "company": company,
                    "location": "India/Remote",
                    "job_url": job_url, "date_posted": "N/A",
                    "site": "wellfound", "searched_role": role,
                    "description": description,
                    "min_amount": None, "max_amount": None,
                    "currency": "USD", "is_remote": True,
                    "region": "india", "skill_score": 0,
                })
                count += 1
            print(f"     ✅ Wellfound {role}: {count} jobs extracted")
        except Exception as e:
            print(f"     ⚠️ Wellfound error for {role}: {e}")
        time.sleep(3)
    unique = deduplicate_jobs(results)
    print(f"     ✅ {len(unique)} Wellfound jobs total (deduplicated)")
    return unique


# ── LEVER ────────────────────────────────────────────────
def fetch_lever_jobs(company_name, company_slug):
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        resp = get_with_retry(url, timeout=10)
        if resp.status_code != 200:
            print(f"     ⚠️ {company_name} (Lever): HTTP {resp.status_code}")
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
            desc_parts  = [item.get("content", "") for item in job.get("lists", [])]
            desc_parts.append(job.get("additional", ""))
            description = " ".join(filter(None, desc_parts))
            if not _is_entry_level_scraper(job.get("text", ""), description):
                continue
            results.append({
                "title": job.get("text"), "company": company_name,
                "location": job.get("categories", {}).get("location", "N/A"),
                "job_url": job.get("hostedUrl", ""),
                "date_posted": datetime.fromtimestamp(job["createdAt"]/1000).strftime("%Y-%m-%d") if job.get("createdAt") else "N/A",
                "site": "lever", "searched_role": job.get("categories", {}).get("team", "SDE"),
                "description": description,
                "min_amount": None, "max_amount": None, "currency": "INR",
                "is_remote": "remote" in location,
                "region": "foreign" if "remote" in location else "india", "skill_score": 0,
            })
        print(f"     ✅ {company_name}: {len(results)} jobs")
        return results
    except Exception as e:
        print(f"     ⚠️ Lever error for {company_name}: {e}")
        return []


# ── GREENHOUSE ───────────────────────────────────────────
def fetch_greenhouse_jobs(company_name, company_slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
    try:
        resp = get_with_retry(url, timeout=10)
        if resp.status_code != 200:
            print(f"     ⚠️ {company_name} (Greenhouse): HTTP {resp.status_code}")
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
            job_desc = job.get("content", "")
            if not _is_entry_level_scraper(job.get("title", ""), job_desc):
                continue
            results.append({
                "title": job.get("title"), "company": company_name,
                "location": job.get("location", {}).get("name", "N/A"),
                "job_url": job.get("absolute_url", ""),
                "date_posted": job.get("updated_at", "N/A")[:10],
                "site": "greenhouse", "searched_role": "SDE",
                "description": job_desc,
                "min_amount": None, "max_amount": None, "currency": "INR",
                "is_remote": "remote" in location,
                "region": "foreign" if "remote" in location else "india", "skill_score": 0,
            })
        print(f"     ✅ {company_name}: {len(results)} jobs")
        return results
    except Exception as e:
        print(f"     ⚠️ Greenhouse error for {company_name}: {e}")
        return []


# ── AMAZON ───────────────────────────────────────────────
AMAZON_ROLES = [
    "software development engineer", "software engineer",
    "machine learning engineer", "data engineer",
]
AMAZON_LOCATIONS = ["Bangalore", "Hyderabad", "Gurugram"]

def fetch_amazon_jobs():
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*",
    }
    for role in AMAZON_ROLES:
        for loc in AMAZON_LOCATIONS:
            url = (
                f"https://www.amazon.jobs/en/search.json"
                f"?base_query={requests.utils.quote(role)}"
                f"&loc_query={requests.utils.quote(loc)}"
                f"&country=IND&category=software-development&result_limit=20"
            )
            try:
                resp = get_with_retry(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                jobs = resp.json().get("jobs", [])
                for job in jobs:
                    title_raw   = job.get("title", "")
                    title_lower = title_raw.lower()
                    job_loc     = job.get("location", "").lower()
                    if not any(r in title_lower for r in TARGET_ROLES):
                        continue
                    description = job.get("description", "")
                    if not _is_entry_level_scraper(title_raw, description):
                        continue
                    results.append({
                        "title": title_raw, "company": "Amazon",
                        "location": job.get("location", loc),
                        "job_url": f"https://www.amazon.jobs{job.get('job_path', '')}",
                        "date_posted": job.get("posted_date", "N/A")[:10] if job.get("posted_date") else "N/A",
                        "site": "amazon.jobs", "searched_role": role,
                        "description": description,
                        "min_amount": None, "max_amount": None, "currency": "INR",
                        "is_remote": "remote" in job_loc,
                        "region": "india", "skill_score": 0,
                    })
            except Exception as e:
                print(f"     ⚠️ Amazon error for {role} @ {loc}: {e}")
            time.sleep(2)
    seen, unique = set(), []
    for j in results:
        if j["job_url"] not in seen:
            seen.add(j["job_url"]); unique.append(j)
    print(f"     ✅ {len(unique)} Amazon jobs found")
    return unique


# ── NAUKRI RSS ───────────────────────────────────────────
NAUKRI_RSS_ROLES = [
    "software-engineer",
    "full-stack-developer",
    "machine-learning-engineer",
    "ai-engineer",
    "python-developer",
    "data-engineer",
]
NAUKRI_RSS_LOCATIONS = [
    "gurugram", "bangalore", "mumbai", "pune", "chennai", "hyderabad"
]

def fetch_naukri_rss_jobs():
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    for role in NAUKRI_RSS_ROLES:
        for location in NAUKRI_RSS_LOCATIONS:
            url = f"https://www.naukri.com/rss/{role}-jobs-in-{location}"
            try:
                resp = requests.get(url, headers=headers, timeout=8)
                if resp.status_code != 200:
                    print(f"     ⚠️ Naukri RSS {role}@{location}: HTTP {resp.status_code}")
                    time.sleep(1)
                    continue

                # Guard: Naukri sometimes returns an HTML page (bot-detection)
                # instead of RSS XML.  Attempting ET.fromstring on HTML raises
                # ParseError AND corrupts the variable state, so detect early.
                body_head = resp.text[:200].lower().strip()
                if body_head.startswith("<!doctype") or "<html" in body_head[:80]:
                    print(f"     ⚠️ Naukri RSS HTML block (bot-detected): {role}@{location} — skipping")
                    time.sleep(2)
                    continue

                root    = ET.fromstring(resp.content)
                channel = root.find("channel")
                if channel is None:
                    time.sleep(1)
                    continue

                items = channel.findall("item")[:10]
                count = 0
                for item in items:
                    title   = item.findtext("title", "").strip()
                    link    = item.findtext("link", "").strip()
                    pubdate = item.findtext("pubDate", "")[:10] if item.findtext("pubDate") else "N/A"
                    desc    = item.findtext("description", "").strip()
                    author  = item.findtext("author", item.findtext("{http://purl.org/dc/elements/1.1/}creator", "N/A"))

                    if not title or not link:
                        continue
                    if not _is_entry_level_scraper(title, desc):
                        continue

                    results.append({
                        "title"        : title,
                        "company"      : author,
                        "location"     : location.title() + ", India",
                        "job_url"      : link,
                        "date_posted"  : pubdate,
                        "site"         : "naukri",
                        "searched_role": role.replace("-", " "),
                        "description"  : desc,
                        "min_amount"   : None,
                        "max_amount"   : None,
                        "currency"     : "INR",
                        "is_remote"    : False,
                        "region"       : "india",
                        "skill_score"  : 0,
                    })
                    count += 1

                if count:
                    print(f"     ✅ Naukri RSS: {role} @ {location} → {count} jobs")

            except requests.Timeout:
                print(f"     ⏱️ Naukri RSS timeout: {role}@{location} — skipping")
            except ET.ParseError as xml_err:
                # Naukri sometimes returns an HTML error page instead of RSS.
                # Detect this and give a clearer message.
                body_preview = resp.text[:120].lower().strip() if 'resp' in dir() else ""
                if "<!doctype" in body_preview or "<html" in body_preview:
                    print(f"     ⚠️ Naukri RSS HTML block (bot-detected): {role}@{location} — skipping")
                else:
                    print(f"     ⚠️ Naukri RSS XML parse error: {role}@{location} — skipping ({xml_err})")
            except Exception as e:
                print(f"     ⚠️ Naukri RSS error {role}@{location}: {e}")

            time.sleep(1)

    seen, unique = set(), []
    for j in results:
        if j["job_url"] not in seen:
            seen.add(j["job_url"])
            unique.append(j)
    print(f"     ✅ {len(unique)} Naukri RSS jobs total (deduplicated)")
    return unique


# ── MAIN ─────────────────────────────────────────────────
def fetch_all_company_jobs():
    all_jobs = []

    print("\n🏢 Fetching from Lever companies...")
    for name, slug in LEVER_COMPANIES.items():
        print(f"  {name}...")
        all_jobs.extend(fetch_lever_jobs(name, slug))

    print("\n🏢 Fetching from Greenhouse companies...")
    for name, slug in GREENHOUSE_COMPANIES.items():
        print(f"  {name}...")
        all_jobs.extend(fetch_greenhouse_jobs(name, slug))

    print("\n🏢 Fetching from Amazon Jobs...")
    all_jobs.extend(fetch_amazon_jobs())

    print("\n📰 Fetching from Naukri RSS...")
    all_jobs.extend(fetch_naukri_rss_jobs())

    print("\n🚀 Fetching from Instahyre...")
    all_jobs.extend(fetch_instahyre_jobs())

    print("\n🎯 Fetching from Hirist...")
    all_jobs.extend(fetch_hirist_jobs())

    print("\n🦄 Fetching from Wellfound...")
    all_jobs.extend(fetch_wellfound_jobs())

    return pd.DataFrame(all_jobs) if all_jobs else pd.DataFrame()
