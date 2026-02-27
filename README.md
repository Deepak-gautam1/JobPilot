---

```markdown
# JobPilot 🤖
> Automated job hunting pipeline — scrapes 7+ platforms nightly, scores jobs against your resume, and delivers a curated digest to Gmail at 8PM every night.

Built because I was applying to 10 jobs one day and ghosting myself for 3 days straight. No discipline. No system. Just chaos. So I automated it.

---

## What It Does

Every night at 8PM, JobPilot automatically:

1. **Scrapes 7+ platforms** — Indeed, Naukri, LinkedIn, Google Jobs, Lever, Greenhouse, Amazon Jobs direct API
2. **Scores every job against your resume** — 30-skill profile with regex word-boundary matching (no false positives)
3. **Kills senior roles** — 47-pattern regex blocks "3+ years", "senior", "lead", "staff", "principal" automatically
4. **Enforces salary floor** — ₹15L/yr for India, $22K/yr for Remote/Singapore
5. **Sends a beautiful HTML email digest** — job cards with skill match bar, salary, source, urgency badge
6. **Tracks everything** in SQLite — applied status, interview stage, follow-up reminders after 7 days

---

## Claude + MCP Integration 🤖

Built two custom MCP (Model Context Protocol) servers:

- **Gmail MCP** — gives Claude read access to your Gmail
- **JobSpy MCP** — gives Claude job search capabilities

Connect both in Claude Desktop and ask in plain English:

> "How many jobs did I apply to this week?"
> "Did Meesho or Razorpay respond?"
> "Which applications are pending after 7 days?"
> "Mark the Dropbox application as Interview stage"

Claude reads your confirmation emails, parses them, and auto-registers each application into SQLite. No spreadsheet. No manual entry.

---

## Stack

| Tool                                       | Purpose                              |
| ------------------------------------------ | ------------------------------------ |
| [JobSpy](https://github.com/Bunsly/JobSpy) | Multi-platform job scraper           |
| Claude + MCP                               | Natural language over Gmail + job DB |
| SQLite                                     | Local job tracking database          |
| Python + Task Scheduler                    | Fully automated nightly runs         |
| Gmail SMTP                                 | HTML email delivery                  |

---

## Project Structure

```text
JobPilot/
├── job_alert.py           # Main pipeline — scrape, filter, score, email
├── database.py            # SQLite operations — single source of truth
├── company_scraper.py     # Lever + Greenhouse + Amazon Jobs direct APIs
├── update_applied.py      # CLI tool — mark applied, update stages, add notes
├── .env.example           # Credential template
├── requirements.txt       # Dependencies
└── README.md

```

---

## Setup

### 1. Clone and install

```bash
git clone [https://github.com/Deepak-gautam1/JobPilot.git](https://github.com/Deepak-gautam1/JobPilot.git)
cd JobPilot
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

```

### 2. Configure credentials

```bash
cp .env.example .env

```

Edit `.env`:

```env
GMAIL_USER=your_gmail@gmail.com
GMAIL_PASSWORD=your_16_char_app_password
TO_EMAIL=your_gmail@gmail.com

```

_Get Gmail App Password: Google Account → Security → 2FA → App Passwords_

### 3. Configure your resume

Edit `job_alert.py`:

```python
MY_SKILLS = [
    "python", "react", "fastapi", ...   # your actual skills
]
ROLES = [
    "software engineer",
    "full stack developer",             # your target roles
    ...
]
INDIA_LOCATIONS = [
    {"location": "Bangalore, India", ...},   # your target cities
]
MIN_SALARY_INR = 1500000    # ₹15L/yr — adjust to your floor

```

### 4. Run manually

```bash
python job_alert.py

```

### 5. Schedule nightly (Windows)

```text
Task Scheduler → Create Task
  Trigger : Daily at 8:00 PM
  Action  : python C:\full\path\to\job_alert.py
  Start in: C:\full\path\to\JobPilot\

```

---

## CLI Tracker

After receiving your email and applying to jobs:

```bash
python update_applied.py

```

```text
=== Job Application Tracker ===
1. Review pending jobs      ← mark applied/not applied
2. Update stages            ← OA / Interview / Offer / Rejected
3. Both

```

---

## Email Preview

Each job card shows:

- Title, Company, Location
- Resume match % with visual bar (green/orange/red)
- Salary (if listed)
- Source platform + posted date
- Direct Apply button
- Weekly summary stats
- Follow-up reminders for applications with no response in 7 days

---

## Known Limitations

- Glassdoor blocks Indian city searches (400 errors) — excluded by design
- LinkedIn rate limits description fetching — handled with delays
- FAANG portals change structure frequently — Amazon Jobs API used directly
- Task Scheduler requires PC to be on at 8PM

---

## What I Learned Building This

- "3 years experience" appears 47 different ways in job descriptions
- Every scraper fix reveals a new bug
- MCP protocol makes Claude genuinely useful as a personal assistant
- Automating the boring part makes the important part (actually applying) much easier to stay consistent with

---

## License

MIT — use it, modify it, make it your own.

Built by **Deepak Gautam** — NIT Kurukshetra

Shoutout to **CampusX** for the MCP lectures 🙏

---

## What's Different From the Old README

| Old (chinpeerapat base)        | New (your actual project)                |
| ------------------------------ | ---------------------------------------- |
| Generic JobSpy MCP server docs | Your specific pipeline documented        |
| No setup for Indian job market | ₹15L floor, Indian cities, Naukri config |
| No email system documented     | Full Gmail digest explained              |
| No tracking system             | SQLite + update_applied.py CLI           |
| No Claude integration details  | Gmail MCP + natural language queries     |
| Example JSON queries           | Actual conversation examples             |

```

***

This is going to look incredibly clean when recruiters land on your repo. Would you like me to help you write a `.gitignore` file so you don't accidentally push your SQLite database or `.env` credentials to the public repository?

```
