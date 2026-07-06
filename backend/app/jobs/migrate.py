"""Lightweight additive column migration (SQLite ALTER ADD COLUMN).

  python -m app.jobs.migrate

Adds columns introduced after a table's initial creation. Idempotent — only adds
what's missing. Run before restarting the API when new columns are added.
"""
from ..db import Base, engine

# table -> {column: "TYPE [DEFAULT ...]"}
_MIGRATIONS = {
    "listings": {
        "css_status": "VARCHAR(12) DEFAULT 'unknown'",
    },
    "aggregated_listings": {
        "css_status": "VARCHAR(12) DEFAULT 'unknown'",
        "export_regions": "TEXT DEFAULT '[]'",
        "region": "VARCHAR(24)",
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


if __name__ == "__main__":
    main()
