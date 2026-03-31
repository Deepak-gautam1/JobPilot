"""
Quick DB updater — run this after Claude tells you to.
Usage: python mark_jobs.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_tracker.db")

UPDATES = [
    # (company_keyword, decision)   decision = 'yes' / 'no'
    ("Crossing Hurdles", "no"),
    ("Connectrz", "no"),
]

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

for company, decision in UPDATES:
    c.execute("UPDATE jobs SET applied = ? WHERE company LIKE ?", (decision, f"%{company}%"))
    rows = c.rowcount
    print(f"{'✅' if decision == 'yes' else '❌'} {company} → applied={decision} ({rows} row updated)")

conn.commit()

c.execute("SELECT applied, COUNT(*) FROM jobs GROUP BY applied")
stats = dict(c.fetchall())
print(f"\n📊 DB Stats — Pending: {stats.get('pending',0)} | Applied: {stats.get('yes',0)} | Skipped: {stats.get('no',0)}")
conn.close()
