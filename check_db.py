import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_tracker.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print('Tables found:', tables)

# If jobs table exists, show count
if ('jobs',) in tables:
    c.execute("SELECT COUNT(*) FROM jobs")
    print('Total jobs:', c.fetchone()[0])
else:
    print("jobs table does NOT exist — run init_db() first!")

conn.close()
