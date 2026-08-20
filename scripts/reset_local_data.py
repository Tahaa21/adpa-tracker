#!/usr/bin/env python3
"""Safely wipe locally-imported assessment data — real or demo.

Deletes rows (never files, never source code, never git history) for:
    FindingInstance, ValidationRecord, Remediation, Finding, Asset, Assessment

Owners (e.g. "Identity Team") are organizational labels, not assessment
data, and are kept by default — pass --include-owners to also clear them.

This talks directly to the database configured by DATABASE_URL (the same
settings the running backend uses) — there is intentionally no DELETE API,
so this script is the supported way to clear local data.

Usage:
    cd backend && source venv/bin/activate
    python3 ../scripts/reset_local_data.py            # asks for confirmation
    python3 ../scripts/reset_local_data.py --yes       # no prompt
    python3 ../scripts/reset_local_data.py --include-owners --yes

Typical workflows:
    Clear demo data before importing real data:
        python3 scripts/reset_local_data.py --yes

    Clear real data before re-seeding the demo:
        python3 scripts/reset_local_data.py --yes
        python3 scripts/load_sample_data.py

    Clear real data before committing/pushing (real data is never committed
    regardless — .gitignore excludes the DB file — but this also clears it
    from the running app so nothing shows up if you demo from this machine):
        python3 scripts/reset_local_data.py --yes
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.models.assessment import Assessment  # noqa: E402
from app.models.asset import Asset  # noqa: E402
from app.models.finding import Finding  # noqa: E402
from app.models.finding_instance import FindingInstance  # noqa: E402
from app.models.owner import Owner  # noqa: E402
from app.models.remediation import Remediation  # noqa: E402
from app.models.validation import ValidationRecord  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument(
        "--include-owners",
        action="store_true",
        help="also delete Owner records (team/person assignments). Off by default.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        counts = {
            "FindingInstance": db.query(FindingInstance).count(),
            "ValidationRecord": db.query(ValidationRecord).count(),
            "Remediation": db.query(Remediation).count(),
            "Finding": db.query(Finding).count(),
            "Asset": db.query(Asset).count(),
            "Assessment": db.query(Assessment).count(),
        }
        if args.include_owners:
            counts["Owner"] = db.query(Owner).count()

        total = sum(counts.values())
        if total == 0:
            print("Nothing to delete — the local database is already empty.")
            return

        print("This will permanently delete the following LOCAL data:")
        for label, count in counts.items():
            print(f"  {label}: {count}")
        print(
            "\nThis does NOT touch source code, migrations, or git history — "
            "only rows in the local database."
        )

        if not args.yes:
            confirm = input("\nType 'yes' to proceed: ").strip().lower()
            if confirm != "yes":
                print("Aborted — nothing was deleted.")
                return

        # Delete children before parents to respect foreign keys.
        db.query(FindingInstance).delete()
        db.query(ValidationRecord).delete()
        db.query(Remediation).delete()
        db.query(Finding).delete()
        db.query(Asset).delete()
        db.query(Assessment).delete()
        if args.include_owners:
            db.query(Owner).delete()
        db.commit()

        print(f"\nDeleted {total} rows across {len(counts)} tables. Local database is now clear.")
        print(
            "Re-seed sanitized demo data anytime with: "
            "python3 scripts/load_sample_data.py"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
