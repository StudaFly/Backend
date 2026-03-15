"""
Seed principal — StudaFly
Usage :
    python -m seeds.seed                  # seed destinations + institutions (idempotent)
    python -m seeds.seed --force          # met à jour les données existantes
    python -m seeds.seed --dry-run        # simulation sans écriture
    python -m seeds.seed --dest           # destinations uniquement
    python -m seeds.seed --inst           # institutions uniquement

Prérequis :
    - alembic upgrade head (tables créées)
    - Variables d'environnement définies (DATABASE_URL)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.app.core.config import settings
from src.app.models.destination import Destination
from src.app.models.institution import Institution

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
                        city=item["city"],
                        image_url=item.get("image_url"),
                        cost_of_living=item.get("cost_of_living"),
                        guide_content=item.get("guide_content"),
                    )
                )
            created += 1
            print(f"  + {item['city']}, {item['country']}")
        elif force:
            if not dry_run:
                existing.country = item["country"]
                existing.city = item["city"]
                existing.image_url = item.get("image_url")
                existing.cost_of_living = item.get("cost_of_living")
                existing.guide_content = item.get("guide_content")
            updated += 1
            print(f"  ~ {item['city']}, {item['country']} (mis à jour)")
        else:
            print(f"  · {item['city']}, {item['country']} (existant)")

    return created, updated


async def seed_institutions(
    db: AsyncSession, force: bool = False, dry_run: bool = False
) -> tuple[int, int]:
    data = _load_json("institutions.json")
    created = updated = 0

    for item in data:
        inst_id = UUID(item["id"])
        result = await db.execute(select(Institution).where(Institution.id == inst_id))
        existing = result.scalar_one_or_none()

        if existing is None:
            if not dry_run:
                db.add(
                    Institution(
                        id=inst_id,
                        name=item["name"],
                        logo_url=item.get("logo_url"),
                        config=item.get("config"),
                    )
                )
            created += 1
            print(f"  + {item['name']}")
        elif force:
            if not dry_run:
                existing.name = item["name"]
                existing.logo_url = item.get("logo_url")
                existing.config = item.get("config")
            updated += 1
            print(f"  ~ {item['name']} (mis à jour)")
        else:
            print(f"  · {item['name']} (existant)")

    return created, updated


async def run(
    do_dest: bool = True,
    do_inst: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    if dry_run:
        print("Mode simulation — aucune écriture en base\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        if do_dest:
            print("── Destinations ─────────────────────────────────────────")
            created, updated = await seed_destinations(db, force=force, dry_run=dry_run)
            print(f"   → {created} créée(s), {updated} mise(s) à jour\n")

        if do_inst:
            print("── Institutions ─────────────────────────────────────────")
            created, updated = await seed_institutions(db, force=force, dry_run=dry_run)
            print(f"   → {created} créée(s), {updated} mise(s) à jour\n")

        if not dry_run:
            await db.commit()
            print("Commit effectué")
        else:
            print("Simulation terminée — aucune donnée écrite")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed StudaFly database")
    parser.add_argument("--force", action="store_true", help="Met à jour les données existantes")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans écriture")
    parser.add_argument("--dest", action="store_true", help="Destinations uniquement")
    parser.add_argument("--inst", action="store_true", help="Institutions uniquement")
    args = parser.parse_args()

    do_dest = args.dest or (not args.dest and not args.inst)
    do_inst = args.inst or (not args.dest and not args.inst)

    asyncio.run(
        run(
            do_dest=do_dest,
            do_inst=do_inst,
            force=args.force,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
