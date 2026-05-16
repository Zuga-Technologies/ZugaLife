"""Breach scope query — enumerate ZugaLife users affected during a window.

Authority: 16 CFR §318.6(a)(2) — "the date of the breach" must be in the
notification. This script answers: WHO was potentially affected, by what
DATA CATEGORY, in what STATE? Output feeds the breach email blast and
the FTC filing.

Usage:
    python scripts/breach_scope_query.py \\
        --window 2026-05-15T00:00:00..2026-05-16T12:00:00 \\
        --categories mood,journal,therapist \\
        --out /tmp/inc-2026-05-16-scope.csv

The output CSV is NOT committed to git — it contains user emails.
Save it to the incident folder + treat as confidential per Mike.

Read-only. Will NOT mutate data. Run from MM via:
    ssh mac 'cd ~/Projects/ZugaLife && python scripts/breach_scope_query.py ...'

For Railway:
    railway ssh "cd /app && python /app/studios/life/scripts/breach_scope_query.py ..."
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# Resolve DB path — Railway = /data/zugaapp.db, MM = ~/Projects/ZugaApp/data/zugaapp.db
DEFAULT_DB_PATH = os.environ.get("ZUGAAPP_DB_PATH", "/data/zugaapp.db")

CATEGORY_TABLES = {
    "mood": "life_mood_entries",
    "journal": "life_journal_entries",
    "habits": "life_habits",
    "goals": "life_goals",
    "therapist": "life_therapist_messages",
    "consent": "life_consents",
}


def parse_window(window: str) -> tuple[datetime, datetime]:
    if ".." not in window:
        raise SystemExit("--window must be ISO-start..ISO-end (e.g. 2026-05-15..2026-05-16)")
    s, e = window.split("..", 1)
    return datetime.fromisoformat(s), datetime.fromisoformat(e)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", required=True, help="ISO start..ISO end, e.g. 2026-05-15..2026-05-16")
    ap.add_argument(
        "--categories", default="mood,journal,habits,goals,therapist",
        help=f"Comma-separated; valid: {','.join(CATEGORY_TABLES)}",
    )
    ap.add_argument("--db", default=DEFAULT_DB_PATH, help=f"SQLite DB path (default: {DEFAULT_DB_PATH})")
    ap.add_argument("--out", required=True, help="Output CSV path (DO NOT COMMIT — contains emails)")
    args = ap.parse_args()

    import sqlite3
    start, end = parse_window(args.window)
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    for c in categories:
        if c not in CATEGORY_TABLES:
            raise SystemExit(f"Unknown category: {c} (valid: {','.join(CATEGORY_TABLES)})")

    if not Path(args.db).exists():
        raise SystemExit(f"DB not found: {args.db}")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    # Per-category affected user_id set, joined with users.email at the end.
    affected: dict[str, set[str]] = {c: set() for c in categories}

    for cat in categories:
        table = CATEGORY_TABLES[cat]
        # Best-effort: tables vary on timestamp column name.
        for col in ("created_at", "updated_at", "logged_at", "ts"):
            try:
                rows = conn.execute(
                    f"SELECT DISTINCT user_id FROM {table} WHERE {col} BETWEEN ? AND ?",
                    (start.isoformat(), end.isoformat()),
                ).fetchall()
                affected[cat] = {r["user_id"] for r in rows}
                break
            except sqlite3.OperationalError:
                continue
        else:
            print(f"WARN: no timestamp column found on {table} — skipping {cat}", file=sys.stderr)

    all_user_ids = set().union(*affected.values()) if affected else set()
    if not all_user_ids:
        print("No users affected in this window.")
        return 0

    # Resolve emails. State column is nullable.
    placeholders = ",".join("?" * len(all_user_ids))
    user_rows = conn.execute(
        f"SELECT id, email, name FROM users WHERE id IN ({placeholders})",
        tuple(all_user_ids),
    ).fetchall()
    users_by_id = {r["id"]: r for r in user_rows}

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["user_id", "email", "name", "categories_accessed"])
        for uid in sorted(all_user_ids):
            u = users_by_id.get(uid)
            if not u:
                continue
            cats_hit = ",".join(sorted(c for c in categories if uid in affected[c]))
            w.writerow([uid, u["email"], u["name"] or "", cats_hit])

    print(f"Wrote {len(all_user_ids)} affected users to {args.out}")
    print(f"Per-category counts: {dict((k, len(v)) for k, v in affected.items())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
