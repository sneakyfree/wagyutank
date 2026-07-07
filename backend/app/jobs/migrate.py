"""Lightweight additive column migration (SQLite ALTER ADD COLUMN).

  python -m app.jobs.migrate

Adds columns introduced after a table's initial creation. Idempotent — only adds
what's missing. Run before restarting the API when new columns are added.
"""
from .. import models  # noqa: F401 — register all tables on Base.metadata
from ..db import Base, engine

# table -> {column: "TYPE [DEFAULT ...]"}
_MIGRATIONS = {
    "users": {
        "role": "VARCHAR(12) DEFAULT 'user'",
        "account_status": "VARCHAR(12) DEFAULT 'active'",
        "last_login_at": "DATETIME",
        "phone": "VARCHAR(32)",
        "recovery_email": "VARCHAR(255)",
        "marketing_opt_in": "BOOLEAN DEFAULT 1",
        "totp_secret": "VARCHAR(64)",
        "totp_enabled": "BOOLEAN DEFAULT 0",
    },
    "listings": {
        "css_status": "VARCHAR(12) DEFAULT 'unknown'",
        "is_sample": "BOOLEAN DEFAULT 0",
        "catalog_opt_in": "BOOLEAN DEFAULT 0",
    },
    "aggregated_listings": {
        "css_status": "VARCHAR(12) DEFAULT 'unknown'",
        "export_regions": "TEXT DEFAULT '[]'",
        "region": "VARCHAR(24)",
        "source_updated_at": "DATETIME",
        "source_date_type": "VARCHAR(16)",
    },
    "animals": {  # ensure the breed-history columns too (safe if already present)
        "prefecture": "VARCHAR(60)",
        "bio": "TEXT",
        "marbling_note": "TEXT",
        "photo_note": "VARCHAR(300)",
    },
}


def main():
    Base.metadata.create_all(bind=engine)  # create any wholly-new tables first
    added = 0
    with engine.begin() as conn:
        existing_tables = {r[0] for r in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, cols in _MIGRATIONS.items():
            if table not in existing_tables:
                continue
            have = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for col, decl in cols.items():
                if col not in have:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                    print(f"  + {table}.{col}")
                    added += 1
    print(f"Migration complete ({added} column(s) added).")
    _promote_admins()


def _promote_admins():
    """Promote configured admin emails (accounts must already exist)."""
    from ..config import settings
    from ..db import SessionLocal
    from ..models import User
    emails = [e.strip().lower() for e in (settings.admin_emails or "").split(",") if e.strip()]
    if not emails:
        return
    db = SessionLocal()
    try:
        promoted = 0
        for u in db.query(User).filter(func_lower_in(User.email, emails)).all():
            if u.role != "admin":
                u.role = "admin"
                promoted += 1
        db.commit()
        if promoted:
            print(f"Promoted {promoted} account(s) to admin.")
    finally:
        db.close()


def func_lower_in(col, values):
    from sqlalchemy import func
    return func.lower(col).in_(values)


if __name__ == "__main__":
    main()
