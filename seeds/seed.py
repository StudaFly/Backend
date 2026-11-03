"""
Main seed — StudaFly
Usage:
    python -m seeds.seed                  # seed destinations + organizations (idempotent)
    python -m seeds.seed --force          # update existing data
    python -m seeds.seed --dry-run        # simulate, write nothing
    python -m seeds.seed --dest           # destinations (+ country profiles) only
    python -m seeds.seed --org            # organizations only

Data:
    data/destinations.json          cities (cost of living, guide) — fixed ids
    data/destination_profiles.json  country profiles (image, summary, facts, key steps) taken
                                    from the former web mock; creates the missing cities
    data/organizations.json         B2B schools — fixed ids; join codes are generated on creation

Prerequisites:
    - alembic upgrade head (tables created)
    - environment variables set (DATABASE_URL)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.app.core.config import settings
from src.app.models.destination import Destination
from src.app.models.organization import Organization
from src.app.services.organization_service import generate_join_code

DATA_DIR = Path(__file__).parent / "data"


def _load_json(filename: str) -> list[dict]:
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


async def seed_destinations(
    db: AsyncSession, force: bool = False, dry_run: bool = False
) -> tuple[int, int]:
    data = _load_json("destinations.json")
    created = updated = 0

    for item in data:
        dest_id = UUID(item["id"])
        result = await db.execute(select(Destination).where(Destination.id == dest_id))
        existing = result.scalar_one_or_none()

        if existing is None:
            if not dry_run:
                db.add(
                    Destination(
                        id=dest_id,
                        country=item["country"],
                        country_code=item["country_code"],
                        city=item["city"],
                        cost_of_living=item.get("cost_of_living"),
                        guide_content=item.get("guide_content"),
                    )
                )
            created += 1
            print(f"  + {item['city']}, {item['country']}")
        elif force:
            if not dry_run:
                existing.country = item["country"]
                existing.country_code = item["country_code"]
                existing.city = item["city"]
                existing.cost_of_living = item.get("cost_of_living")
                existing.guide_content = item.get("guide_content")
            updated += 1
            print(f"  ~ {item['city']}, {item['country']} (updated)")
        else:
            print(f"  · {item['city']}, {item['country']} (existing)")

    return created, updated


def _profile_destination_id(country: str, city: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"studafly:destination:{country}/{city}")


def _apply_profile(destination: Destination, profile: dict, force: bool) -> bool:
    changed = False
    if destination.country_code != profile["country_code"]:
        destination.country_code = profile["country_code"]
        changed = True
    for field in ("image_url", "summary", "facts"):
        if force or getattr(destination, field) is None:
            if getattr(destination, field) != profile[field]:
                setattr(destination, field, profile[field])
                changed = True

    guide = dict(destination.guide_content or {})
    if force or not guide.get("key_steps"):
        if guide.get("key_steps") != profile["key_steps"]:
            guide["key_steps"] = profile["key_steps"]
            guide.setdefault("overview", profile["summary"])
            destination.guide_content = guide
            changed = True
    return changed


async def seed_destination_profiles(
    db: AsyncSession, force: bool = False, dry_run: bool = False
) -> tuple[int, int]:
    profiles = _load_json("destination_profiles.json")
    created = updated = 0

    for profile in profiles:
        country = profile["country"]
        result = await db.execute(select(Destination).where(Destination.country == country))
        existing = {d.city: d for d in result.scalars().all()}

        for city in profile["cities"]:
            if city in existing:
                continue
            if not dry_run:
                destination = Destination(
                    id=_profile_destination_id(country, city),
                    country=country,
                    country_code=profile["country_code"],
                    city=city,
                    cost_of_living=profile["cost_of_living"],
                    guide_content={"overview": profile["summary"]},
                )
                _apply_profile(destination, profile, force=True)
                db.add(destination)
            created += 1
            print(f"  + {city}, {country}")

        for destination in existing.values():
            if dry_run or _apply_profile(destination, profile, force):
                updated += 1
                print(f"  ~ {destination.city}, {country} (country profile)")

    return created, updated


async def seed_organizations(
    db: AsyncSession, force: bool = False, dry_run: bool = False
) -> tuple[int, int]:
    data = _load_json("organizations.json")
    created = updated = 0

    for item in data:
        org_id = UUID(item["id"])
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        existing = result.scalar_one_or_none()

        if existing is None:
            if not dry_run:
                db.add(
                    Organization(
                        id=org_id,
                        name=item["name"],
                        slug=item["slug"],
                        logo_url=item.get("logo_url"),
                        branding=item.get("branding") or {},
                        settings=item.get("settings") or {},
                        join_code=generate_join_code(),
                    )
                )
            created += 1
            print(f"  + {item['name']}")
        elif force:
            if not dry_run:
                existing.name = item["name"]
                existing.slug = item["slug"]
                existing.logo_url = item.get("logo_url")
                existing.branding = item.get("branding") or {}
                existing.settings = item.get("settings") or {}
            updated += 1
            print(f"  ~ {item['name']} (updated)")
        else:
            print(f"  · {item['name']} (existing)")

    return created, updated


async def run(
    do_dest: bool = True,
    do_org: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    if dry_run:
        print("Dry run — nothing is written to the database\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        if do_dest:
            print("── Destinations ─────────────────────────────────────────")
            created, updated = await seed_destinations(db, force=force, dry_run=dry_run)
            print(f"   → {created} created, {updated} updated\n")
            if not dry_run:
                await db.flush()

            print("── Country profiles ─────────────────────────────────────")
            created, updated = await seed_destination_profiles(db, force=force, dry_run=dry_run)
            print(f"   → {created} city(ies) created, {updated} enriched\n")

        if do_org:
            print("── Organizations ────────────────────────────────────────")
            created, updated = await seed_organizations(db, force=force, dry_run=dry_run)
            print(f"   → {created} created, {updated} updated\n")

        if not dry_run:
            await db.commit()
            print("Committed")
        else:
            print("Dry run finished — no data written")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed StudaFly database")
    parser.add_argument("--force", action="store_true", help="Update existing data")
    parser.add_argument("--dry-run", action="store_true", help="Simulate, write nothing")
    parser.add_argument("--dest", action="store_true", help="Destinations only")
    parser.add_argument("--org", action="store_true", help="Organizations only")
    args = parser.parse_args()

    do_dest = args.dest or (not args.dest and not args.org)
    do_org = args.org or (not args.dest and not args.org)

    asyncio.run(
        run(
            do_dest=do_dest,
            do_org=do_org,
            force=args.force,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
