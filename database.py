import sqlite3
import hashlib
import os
from contextlib import contextmanager
from datetime import datetime

# Absolute path so Task Scheduler doesn't create DB in C:\Windows\System32
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_tracker.db")


@contextmanager
def _db():
    """Context manager — opens a connection, yields cursor, commits on success, always closes."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # allows dict-style access if needed later
    try:
        yield conn, conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables and indexes if they don't exist. Also migrates existing DBs."""
    with _db() as (conn, c):
        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash       TEXT UNIQUE,
                title          TEXT,
                company        TEXT,
                location       TEXT,
                salary_min     REAL,
                salary_max     REAL,
                currency       TEXT,
                site           TEXT,
                job_url        TEXT,
                searched_role  TEXT,
                region         TEXT,
                skill_score    REAL,   -- keyword match score (0-100)
                semantic_score REAL,   -- embedding cosine similarity score (0-100)
                final_score    REAL,   -- weighted composite: semantic+keyword+recency
                date_posted    TEXT,
                date_scraped   TEXT DEFAULT (datetime('now','localtime')),
                sent_in_email  INTEGER DEFAULT 0,
                applied        TEXT DEFAULT 'pending',
                stage          TEXT DEFAULT 'none',
                date_applied   TEXT,
                notes          TEXT DEFAULT ''
            )
        """)


        # Migrate existing DBs that don't have newer columns
        existing_cols = [row[1] for row in c.execute("PRAGMA table_info(jobs)").fetchall()]
        if "stage" not in existing_cols:
            c.execute("ALTER TABLE jobs ADD COLUMN stage TEXT DEFAULT 'none'")
        if "date_applied" not in existing_cols:
            c.execute("ALTER TABLE jobs ADD COLUMN date_applied TEXT")
        if "notes" not in existing_cols:
            c.execute("ALTER TABLE jobs ADD COLUMN notes TEXT DEFAULT ''")
        # New scoring columns — added in semantic scoring upgrade
        if "semantic_score" not in existing_cols:
            c.execute("ALTER TABLE jobs ADD COLUMN semantic_score REAL")
        if "final_score" not in existing_cols:
            c.execute("ALTER TABLE jobs ADD COLUMN final_score REAL")


        
        # Indexes for fast dedup lookups and stats queries
        c.execute("CREATE INDEX IF NOT EXISTS idx_job_hash  ON jobs(job_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_applied   ON jobs(applied)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_scraped   ON jobs(date_scraped)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_final_sc  ON jobs(final_score)")

def make_hash(job_url, title, company):
    """Create a unique fingerprint for a job."""
    raw = f"{job_url}|{title}|{company}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()


def get_all_seen_hashes():
    """Load all seen job hashes into a set for fast in-memory dedup."""
    with _db() as (_, c):
        c.execute("SELECT job_hash FROM jobs")
        return {row[0] for row in c.fetchall()}


def save_job(job, sent=True):
    """Save a job to DB. Returns True if inserted, False if duplicate."""
    import pandas as pd

    job_url  = str(job.get("job_url", ""))
    title    = str(job.get("title", ""))
    company  = str(job.get("company", ""))
    job_hash = make_hash(job_url, title, company)

    try:
        with _db() as (_, c):
            c.execute("""
                INSERT INTO jobs (
                    job_hash, title, company, location,
                    salary_min, salary_max, currency, site,
                    job_url, searched_role, region,
                    skill_score, semantic_score, final_score,
                    date_posted, sent_in_email, applied
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                float(job.get("skill_score",    0)),
                float(job.get("semantic_score", 0)),
                float(job.get("final_score",    job.get("skill_score", 0))),
                str(job.get("date_posted", "")),
                1 if sent else 0,
                "pending",
            ))
        return True
    except sqlite3.IntegrityError:
        return False


def mark_applied(job_url, decision):
    """Mark a job as applied=yes or applied=no. Sets date_applied if yes."""
    with _db() as (_, c):
        if decision == "yes":
            c.execute("""
                UPDATE jobs SET applied = ?, date_applied = date('now','localtime')
                WHERE job_url = ?
            """, (decision, job_url))
        else:
            c.execute("UPDATE jobs SET applied = ? WHERE job_url = ?", (decision, job_url))


def mark_stage(job_url, stage):
    """Update interview stage. Values: none / oa / interview / offer / rejected"""
    with _db() as (_, c):
        c.execute("UPDATE jobs SET stage = ? WHERE job_url = ?", (stage, job_url))


def update_notes(job_url, notes):
    """Set notes on a job (referral, HR name, follow-up info)."""
    with _db() as (_, c):
        c.execute("UPDATE jobs SET notes = ? WHERE job_url = ?", (notes, job_url))


def get_pending_jobs(limit=20):
    """Return pending jobs ordered by most recently scraped."""
    with _db() as (_, c):
        c.execute("""
            SELECT id, title, company, location, salary_min, salary_max,
                   currency, job_url, date_scraped, stage, notes
            FROM jobs
            WHERE applied = 'pending'
            ORDER BY date_scraped DESC
            LIMIT ?
        """, (limit,))
        return c.fetchall()


def get_applied_jobs(limit=30):
    """Return applied jobs ordered by most recently applied."""
    with _db() as (_, c):
        c.execute("""
            SELECT id, title, company, location, job_url,
                   date_applied, stage, notes
            FROM jobs
            WHERE applied = 'yes'
            ORDER BY date_applied DESC
            LIMIT ?
        """, (limit,))
        return c.fetchall()


def get_followup_jobs(days=7):
    """Return jobs applied N+ days ago with no stage update."""
    with _db() as (_, c):
        c.execute("""
            SELECT id, title, company, location, job_url, date_applied, notes
            FROM jobs
            WHERE applied = 'yes'
              AND stage = 'none'
              AND date_applied IS NOT NULL
              AND julianday('now') - julianday(date_applied) >= ?
            ORDER BY date_applied ASC
        """, (days,))
        return c.fetchall()


def get_weekly_stats():
    """Return stats for the past 7 days only."""
    with _db() as (_, c):
        def q(sql, params=()):
            c.execute(sql, params)
            return c.fetchone()[0]

        return {
            "new_jobs"    : q("SELECT COUNT(*) FROM jobs WHERE date_scraped >= date('now', '-7 days')"),
            "applied_week": q("SELECT COUNT(*) FROM jobs WHERE applied='yes' AND date_applied >= date('now', '-7 days')"),
            "oas"         : q("SELECT COUNT(*) FROM jobs WHERE stage='oa' AND date_applied >= date('now', '-7 days')"),
            "interviews"  : q("SELECT COUNT(*) FROM jobs WHERE stage='interview' AND date_applied >= date('now', '-7 days')"),
            "offers"      : q("SELECT COUNT(*) FROM jobs WHERE stage='offer' AND date_applied >= date('now', '-7 days')"),
            "rejected"    : q("SELECT COUNT(*) FROM jobs WHERE stage='rejected' AND date_applied >= date('now', '-7 days')"),
        }


def get_stats():
    """Return summary stats."""
    with _db() as (_, c):
        def q(sql):
            c.execute(sql)
            return c.fetchone()[0]

        return {
            "total"  : q("SELECT COUNT(*) FROM jobs"),
            "applied": q("SELECT COUNT(*) FROM jobs WHERE applied='yes'"),
            "skipped": q("SELECT COUNT(*) FROM jobs WHERE applied='no'"),
            "pending": q("SELECT COUNT(*) FROM jobs WHERE applied='pending'"),
        }
