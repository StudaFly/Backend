"""roles_data

Data step of the roles model, separate from the schema migrations:
- `role = admin` + institution  -> `org_staff` + active `manager` membership;
- student with an institution   -> active enrollment, source `migration`;
- `institutions.config`         -> `branding` (colors) + `settings` (everything else);
- every organization gets a slug and a random join code;
- `destinations.country`        -> ISO 3166-1 alpha-2 `country_code`.

`superadmin` accounts and `admin` accounts without an institution are never converted
automatically: the migration stops and lists them (platform admins are created with the CLI).

The helpers are copied here on purpose: a migration must not depend on application code
that keeps evolving.

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-11-02 00:00:01.000000

"""
import json
import re
import secrets
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a1b2c3d4e5"
down_revision: str | None = "e5f6a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BRANDING_KEYS = ("primary_color", "accent_color")

COUNTRY_CODES = {
    "Allemagne": "DE",
    "Australie": "AU",
    "Autriche": "AT",
    "Belgique": "BE",
    "Canada": "CA",
    "Chine": "CN",
    "Corée du Sud": "KR",
    "Danemark": "DK",
    "Espagne": "ES",
    "États-Unis": "US",
    "Finlande": "FI",
    "France": "FR",
    "Grèce": "GR",
    "Hongrie": "HU",
    "Irlande": "IE",
    "Italie": "IT",
    "Japon": "JP",
    "Pays-Bas": "NL",
    "Pologne": "PL",
    "Portugal": "PT",
    "République Tchèque": "CZ",
    "Royaume-Uni": "GB",
    "Singapour": "SG",
    "Suède": "SE",
}

_JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")[:90] or "organization"


def _join_code() -> str:
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(10))


def upgrade() -> None:
    conn = op.get_bind()

    blocked = conn.execute(
        sa.text(
            "SELECT id, email, role FROM users "
            "WHERE role = 'superadmin' OR (role = 'admin' AND institution_id IS NULL)"
        )
    ).all()
    if blocked:
        listing = ", ".join(f"{row.email} ({row.role})" for row in blocked)
        raise RuntimeError(
            "Accounts that cannot be converted automatically — decide for each one "
            f"(platform admins are created with the CLI): {listing}"
        )

    conn.execute(
        sa.text(
            "UPDATE users SET account_type = 'org_staff' "
            "WHERE role = 'admin' AND institution_id IS NOT NULL"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO organization_members (id, organization_id, user_id, org_role, is_active) "
            "SELECT gen_random_uuid(), institution_id, id, 'manager', true FROM users "
            "WHERE role = 'admin' AND institution_id IS NOT NULL"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO student_enrollments (id, organization_id, student_id, status, source, "
            "joined_at) "
            "SELECT gen_random_uuid(), institution_id, id, 'active', 'migration', created_at "
            "FROM users WHERE role = 'student' AND institution_id IS NOT NULL"
        )
    )

    used_slugs: set[str] = set()
    for org in conn.execute(sa.text("SELECT id, name, config FROM organizations")).all():
        config = org.config or {}
        branding = {k: config[k] for k in BRANDING_KEYS if k in config}
        settings = {k: v for k, v in config.items() if k not in BRANDING_KEYS}
        base = _slugify(org.name)
        slug, suffix = base, 2
        while slug in used_slugs:
            slug, suffix = f"{base}-{suffix}", suffix + 1
        used_slugs.add(slug)
        conn.execute(
            sa.text(
                "UPDATE organizations SET slug = :slug, join_code = :code, "
                "branding = CAST(:branding AS jsonb), settings = CAST(:settings AS jsonb) "
                "WHERE id = :id"
            ),
            {
                "id": org.id,
                "slug": slug,
                "code": _join_code(),
                "branding": json.dumps(branding),
                "settings": json.dumps(settings),
            },
        )

    for country, code in COUNTRY_CODES.items():
        conn.execute(
            sa.text("UPDATE destinations SET country_code = :code WHERE country = :country"),
            {"code": code, "country": country},
        )
    unmapped = conn.execute(
        sa.text("SELECT DISTINCT country FROM destinations WHERE country_code IS NULL")
    ).scalars()
    for country in unmapped:
        # Not guessed on purpose: listed in STATUS.md and fixed by hand.
        print(f"[roles_data] no ISO code for destination country {country!r}")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE users SET role = CASE account_type "
            "WHEN 'org_staff' THEN 'admin' WHEN 'platform_admin' THEN 'superadmin' "
            "ELSE 'student' END"
        )
    )
    # The legacy column is not maintained after the upgrade: rebuild it from scratch.
    conn.execute(sa.text("UPDATE users SET institution_id = NULL"))
    conn.execute(
        sa.text(
            "UPDATE users u SET institution_id = m.organization_id FROM organization_members m "
            "WHERE m.user_id = u.id AND m.is_active"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE users u SET institution_id = e.organization_id FROM student_enrollments e "
            "WHERE e.student_id = u.id AND e.status = 'active'"
        )
    )
    conn.execute(sa.text("UPDATE organizations SET config = branding || settings"))
