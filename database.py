import sqlite3
import hashlib
import os
from datetime import datetime

# Absolute path so Task Scheduler doesn't create DB in C:\Windows\System32
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_tracker.db")


def init_db():
    """Create tables if they don't exist. Also migrate existing DBs."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            job_hash      TEXT UNIQUE,
            title         TEXT,
            company       TEXT,
            location      TEXT,
            salary_min    REAL,
            salary_max    REAL,
            currency      TEXT,
            site          TEXT,
            job_url       TEXT,
            searched_role TEXT,
            region        TEXT,
            skill_score   REAL,
            date_posted   TEXT,
            date_scraped  TEXT DEFAULT (datetime('now','localtime')),
            sent_in_email INTEGER DEFAULT 0,
            applied       TEXT DEFAULT 'pending',
            stage         TEXT DEFAULT 'none',
            date_applied  TEXT,
            notes         TEXT DEFAULT ''
        )
    """)

    # Migrate existing DBs that don't have new columns
    existing_cols = [row[1] for row in c.execute("PRAGMA table_info(jobs)").fetchall()]
    if "stage" not in existing_cols:
        c.execute("ALTER TABLE jobs ADD COLUMN stage TEXT DEFAULT 'none'")
    if "date_applied" not in existing_cols:
        c.execute("ALTER TABLE jobs ADD COLUMN date_applied TEXT")
    if "notes" not in existing_cols:
        c.execute("ALTER TABLE jobs ADD COLUMN notes TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def make_hash(job_url, title, company):
    """Create unique fingerprint for a job."""
    raw = f"{job_url}|{title}|{company}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()


def is_already_seen(job_hash):
    """Check if job was already stored (sent before)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM jobs WHERE job_hash = ?", (job_hash,))
    result = c.fetchone()
    conn.close()
    return result is not None


def get_all_seen_hashes():
    """Load all seen job hashes into a set for fast in-memory dedup."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT job_hash FROM jobs")
    hashes = {row[0] for row in c.fetchall()}
    conn.close()
    return hashes


def save_job(job, sent=True):
    """Save a job to DB. Returns True if inserted, False if duplicate."""
    import pandas as pd

    job_url  = str(job.get("job_url", ""))
    title    = str(job.get("title", ""))
    company  = str(job.get("company", ""))
    job_hash = make_hash(job_url, title, company)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO jobs (
                job_hash, title, company, location,
                salary_min, salary_max, currency, site,
                job_url, searched_role, region, skill_score,
                date_posted, sent_in_email, applied
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_hash,
            title,
            company,
            str(job.get("location", "")),
            float(job["min_amount"]) if pd.notna(job.get("min_amount")) else None,
            float(job["max_amount"]) if pd.notna(job.get("max_amount")) else None,
            str(job.get("currency", "USD")),
            str(job.get("site", "")),
            job_url,
            str(job.get("searched_role", "")),
            str(job.get("region", "")),
            float(job.get("skill_score", 0)),
            str(job.get("date_posted", "")),
            1 if sent else 0,
            "pending"
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def mark_applied(job_url, decision):
    """Mark a job as applied=yes or applied=no. Sets date_applied if yes."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if decision == 'yes':
        c.execute("""
            UPDATE jobs SET applied = ?, date_applied = date('now','localtime')
            WHERE job_url = ?
        """, (decision, job_url))
    else:
        c.execute("UPDATE jobs SET applied = ? WHERE job_url = ?", (decision, job_url))
    conn.commit()
    conn.close()


def mark_stage(job_url, stage):
    """Update interview stage. Values: none / oa / interview / offer / rejected"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE jobs SET stage = ? WHERE job_url = ?", (stage, job_url))
    conn.commit()
    conn.close()


def update_notes(job_url, notes):
    """Set notes on a job (referral, HR name, follow-up info)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE jobs SET notes = ? WHERE job_url = ?", (notes, job_url))
    conn.commit()
    conn.close()


def get_pending_jobs(limit=20):
    """Return pending jobs ordered by most recently scraped."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, company, location, salary_min, salary_max,
               currency, job_url, date_scraped, stage, notes
        FROM jobs
        WHERE applied = 'pending'
        ORDER BY date_scraped DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_applied_jobs(limit=30):
    """Return applied jobs ordered by most recently applied."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, company, location, job_url,
               date_applied, stage, notes
        FROM jobs
        WHERE applied = 'yes'
        ORDER BY date_applied DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_followup_jobs(days=7):
    """Return jobs applied N+ days ago with no stage update."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, company, location, job_url, date_applied, notes
        FROM jobs
        WHERE applied = 'yes'
          AND stage = 'none'
          AND date_applied IS NOT NULL
          AND julianday('now') - julianday(date_applied) >= ?
        ORDER BY date_applied ASC
    """, (days,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_weekly_stats():
    """Return stats for the past 7 days only."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM jobs WHERE date_scraped >= date('now', '-7 days')")
    new_jobs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE applied='yes' AND date_applied >= date('now', '-7 days')")
    applied_week = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE stage='oa' AND date_applied >= date('now', '-7 days')")
    oas = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE stage='interview' AND date_applied >= date('now', '-7 days')")
    interviews = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE stage='offer' AND date_applied >= date('now', '-7 days')")
    offers = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE stage='rejected' AND date_applied >= date('now', '-7 days')")
    rejected = c.fetchone()[0]
    conn.close()
    return {
        "new_jobs"    : new_jobs,
        "applied_week": applied_week,
        "oas"         : oas,
        "interviews"  : interviews,
        "offers"      : offers,
        "rejected"    : rejected,
    }


def get_stats():
    """Return summary stats."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM jobs")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE applied='yes'")
    applied = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE applied='no'")
    skipped = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE applied='pending'")
    pending = c.fetchone()[0]
    conn.close()
    return {"total": total, "applied": applied, "skipped": skipped, "pending": pending}
