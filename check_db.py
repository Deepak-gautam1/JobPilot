import sqlite3

conn = sqlite3.connect('job_tracker.db')
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
