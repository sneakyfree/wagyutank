"""Role hierarchy for the staff control panel.

Four tiers, in ascending authority:

  user         – a normal member (buyer/seller). No panel access.
  manager      – day-to-day operations: sees analytics + members, moderates the
                 Roundup and ads. Cannot suspend/delete members, change platform
                 settings, send campaigns, or manage roles.
  admin        – everything a manager does, plus member suspension/deletion,
                 campaigns, settings, AI provider, and promoting/removing MANAGERS.
                 Cannot create or remove other admins.
  super_admin  – everything, including assigning and removing admins. The owner.

A staff member can only act on accounts strictly below their own rank.
"""

RANK = {"user": 0, "manager": 1, "admin": 2, "super_admin": 3}
STAFF_ROLES = ("manager", "admin", "super_admin")
ASSIGNABLE_ROLES = ("user", "manager", "admin", "super_admin")


def rank(role: str | None) -> int:
    return RANK.get(role or "user", 0)


def role_for_email(email: str, super_admin_emails: str, admin_emails: str) -> str:
    """Bootstrap role for a freshly-registered / migrated account by email."""
    e = (email or "").strip().lower()
    supers = {x.strip().lower() for x in (super_admin_emails or "").split(",") if x.strip()}
    admins = {x.strip().lower() for x in (admin_emails or "").split(",") if x.strip()}
    if e in supers:
        return "super_admin"
    if e in admins:
        return "admin"
    return "user"
