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
        "dead_streak": "INTEGER DEFAULT 0",
    },
    "wagyu_videos": {
        "editorial": "TEXT",
    },
    "comments": {
        "lang": "VARCHAR(5) DEFAULT 'en'",
    },
    "animals": {  # ensure the breed-history columns too (safe if already present)
        "is_legend": "BOOLEAN DEFAULT 0",
        "prefecture": "VARCHAR(60)",
        "bio": "TEXT",
        "marbling_note": "TEXT",
        "photo_note": "VARCHAR(300)",
    },
}


def _generic_decl(col) -> str:
    """SQLite column declaration for a model column, derived from its type. Added
    as NULLable (no NOT NULL) so `ALTER TABLE ADD COLUMN` never needs a value for
    existing rows; a constant server/Python default is appended when we have one."""
    try:
        decl = col.type.compile(dialect=engine.dialect)
    except Exception:  # noqa: BLE001 — unknown type → let SQLite treat it loosely
        decl = "TEXT"
    d = getattr(col, "default", None)
    if d is not None and getattr(d, "is_scalar", False) and not callable(getattr(d, "arg", None)):
        arg = d.arg
        if isinstance(arg, bool):
            decl += f" DEFAULT {1 if arg else 0}"
        elif isinstance(arg, (int, float)):
            decl += f" DEFAULT {arg}"
        elif isinstance(arg, str):
            decl += " DEFAULT '" + arg.replace("'", "''") + "'"
    return decl


def main():
    Base.metadata.create_all(bind=engine)  # create any wholly-new tables first
    added = 0
    with engine.begin() as conn:
        existing_tables = {r[0] for r in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        # 1) explicit migrations (kept for columns that want a specific default)
        for table, cols in _MIGRATIONS.items():
            if table not in existing_tables:
                continue
            have = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for col, decl in cols.items():
                if col not in have:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                    print(f"  + {table}.{col}")
                    added += 1
        # 2) generic drift heal — any model column missing from the DB, derived
        #    straight from the ORM metadata. This is what lets a tank whose DB was
        #    created at an older model version (schema drift) self-heal on migrate
        #    instead of 500ing on the first query that selects the new column.
        for table_obj in Base.metadata.sorted_tables:
            if table_obj.name not in existing_tables:
                continue
            have = {r[1] for r in conn.exec_driver_sql(
                f"PRAGMA table_info({table_obj.name})")}
            for col in table_obj.columns:
                if col.name in have:
                    continue
                conn.exec_driver_sql(
                    f"ALTER TABLE {table_obj.name} ADD COLUMN {col.name} {_generic_decl(col)}")
                print(f"  + {table_obj.name}.{col.name} (auto)")
                added += 1
    print(f"Migration complete ({added} column(s) added).")
    _promote_admins()


def _promote_admins():
    """Promote configured staff emails to their bootstrap role (super_admin >
    admin). Only ever raises a role, never demotes — manual changes stick."""
    from ..config import settings
    from ..db import SessionLocal
    from ..models import User
    from ..roles import rank, role_for_email

    all_emails = [e.strip().lower() for e in
                  f"{settings.super_admin_emails},{settings.admin_emails}".split(",") if e.strip()]
    if not all_emails:
        return
    db = SessionLocal()
    try:
        promoted = 0
        for u in db.query(User).filter(func_lower_in(User.email, all_emails)).all():
            target = role_for_email(u.email, settings.super_admin_emails, settings.admin_emails)
            if rank(target) > rank(u.role):
                u.role = target
                promoted += 1
                print(f"  ↑ {u.email} → {target}")
        db.commit()
        if promoted:
            print(f"Promoted {promoted} staff account(s).")
    finally:
        db.close()


def func_lower_in(col, values):
    from sqlalchemy import func
    return func.lower(col).in_(values)


if __name__ == "__main__":
    main()
