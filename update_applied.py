from database import (
    DB_PATH,                          # ← single source of truth, no local redefinition
    mark_applied, mark_stage, update_notes,
    get_stats, get_pending_jobs, get_applied_jobs  # ← DB queries centralized in database.py
)

STAGES = {
    "1": "oa",
    "2": "interview",
    "3": "offer",
    "4": "rejected",
    "0": "none",
}


def review_pending():
    print("\n=== Pending Jobs ===\n")
    rows = get_pending_jobs()

    if not rows:
        print("No pending jobs!")
        return

    for row in rows:
        id_, title, company, location, sal_min, sal_max, currency, url, scraped, stage, notes = row
        sym    = "Rs." if currency == "INR" else "$"
        salary = f"{sym}{sal_min:,.0f} - {sym}{sal_max:,.0f}" if sal_min else "N/A"

        print(f"\n[{id_}] {title}")
        print(f"     Company  : {company}")
        print(f"     Location : {location}")
        print(f"     Salary   : {salary}")
        print(f"     Scraped  : {scraped}")
        print(f"     Stage    : {stage or 'none'}")
        print(f"     Notes    : {notes or '-'}")
        print(f"     URL      : {url}")

        choice = input("     Applied? (y/n/s=skip): ").strip().lower()
        if choice == 'y':
            mark_applied(url, 'yes')
            print("     ✅ Marked APPLIED")
            note = input("     Add note (referral/HR/blank): ").strip()
            if note:
                update_notes(url, note)
        elif choice == 'n':
            mark_applied(url, 'no')
            print("     ❌ Marked NOT APPLIED")
        else:
            print("     ⏭  Skipped")


def update_stages():
    print("\n=== Update Stages for Applied Jobs ===\n")
    rows = get_applied_jobs()

    if not rows:
        print("No applied jobs found!")
        return

    for row in rows:
        id_, title, company, location, url, date_applied, stage, notes = row
        print(f"\n[{id_}] {title} @ {company}")
        print(f"     Applied  : {date_applied or 'N/A'}")
        print(f"     Stage    : {stage or 'none'}")
        print(f"     Notes    : {notes or '-'}")
        print(f"     URL      : {url}")
        print(f"     Stages   : 0=none | 1=OA | 2=Interview | 3=Offer | 4=Rejected | s=skip")

        choice = input("     Update stage: ").strip().lower()
        if choice in STAGES:
            mark_stage(url, STAGES[choice])
            print(f"     ✅ Stage set to: {STAGES[choice]}")
            note = input("     Update note (blank to keep): ").strip()
            if note:
                update_notes(url, note)
        else:
            print("     ⏭  Skipped")


def main():
    print("\n=== Job Application Tracker ===")
    print(f"DB   : {DB_PATH}")          # ← shows exact DB path so you can verify at a glance
    print("1. Review pending jobs")
    print("2. Update stages (OA / Interview / Offer / Rejected)")
    print("3. Both")
    choice = input("\nChoice (1/2/3): ").strip()

    if choice in ("1", "3"):
        review_pending()
    if choice in ("2", "3"):
        update_stages()

    stats = get_stats()
    print(f"\n=== Stats ===")
    print(f"Total    : {stats['total']}")
    print(f"Applied  : {stats['applied']}")
    print(f"Skipped  : {stats['skipped']}")
    print(f"Pending  : {stats['pending']}")


if __name__ == "__main__":
    main()
