"""
Roles demo data — StudaFly (local and test environments only)
Usage:
    python -m seeds.roles_demo            # create the demo (refused if it already exists)
    python -m seeds.roles_demo --reset    # delete the demo accounts and schools, then recreate

Prerequisites: alembic upgrade head, then python -m seeds.seed (destinations).
Every account uses the password printed at the end.
"""

import argparse
import asyncio
import hashlib
import secrets
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.app.core.config import settings
from src.app.core.security import hash_password
from src.app.core.zones import ZONES
from src.app.models.advisor_perimeter import AdvisorPerimeter
from src.app.models.contract import Contract
from src.app.models.destination import Destination
from src.app.models.enums import (
    AccountType,
    ContractStatus,
    EnrollmentSource,
    InvitationKind,
    OrgRole,
    PremiumSource,
    UserStatus,
)
from src.app.models.invitation import Invitation
from src.app.models.mobility import Mobility
from src.app.models.mobility_advisor_override import MobilityAdvisorOverride
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.premium_grant import PremiumGrant
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.student_note import StudentNote
from src.app.models.user import User
from src.app.services.organization_service import generate_join_code
from src.app.services.task_generation_service import build_template_tasks

DOMAIN = "demo.example.com"
PASSWORD = "Demo-pass-2026"
SLUGS = ("ecole-demo", "ecole-pilote", "ecole-expiree")
TODAY = date.today()

ADVISORS = [
    ("manager", "Camille Martin", OrgRole.MANAGER, ZONES["latin_america"]),
    ("conseiller.europe", "Hugo Bernard", OrgRole.ADVISOR, ZONES["europe"] + ZONES["africa"]),
    ("conseiller.amerique", "Léa Dubois", OrgRole.ADVISOR, ("US", "CA")),
    ("conseiller.asie", "Yuki Tanaka", OrgRole.ADVISOR, ZONES["asia"]),
]

STUDENTS = [
    ("lucas.petit", "Lucas Petit", "Montréal", "stage", 120, 0.4),
    ("emma.durand", "Emma Durand", "Madrid", "erasmus", 20, 0.1),
    ("jules.moreau", "Jules Moreau", "Berlin", "erasmus", 150, 0.6),
    ("chloe.laurent", "Chloé Laurent", "Lisbonne", "semestre", 100, 0.5),
    ("ines.garcia", "Inès Garcia", "Casablanca", "stage", 90, 0.3),
    ("tom.lefebvre", "Tom Lefebvre", "New York", "double_diplome", 45, 0.05),
    ("manon.roux", "Manon Roux", "Toronto", "semestre", 130, 0.7),
    ("louis.fournier", "Louis Fournier", "Tokyo", "semestre", 110, 0.45),
    ("sarah.morel", "Sarah Morel", "Séoul", "semestre", 160, 0.2),
    ("adam.girard", "Adam Girard", "Singapour", "stage", 75, 0.35),
    ("lina.andre", "Lina André", "Buenos Aires", "semestre", 140, 0.25),
    ("noah.mercier", "Noah Mercier", "Mexico", "stage", 95, 0.5),
    ("zoe.blanc", "Zoé Blanc", "Sydney", "semestre", 125, 0.3),
]

LATE_STUDENTS = {"tom.lefebvre", "sarah.morel"}


def email(local: str) -> str:
    return f"{local}@{DOMAIN}"


class Demo:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.password_hash = hash_password(PASSWORD)
        self.destinations: dict[str, Destination] = {}
        self.summary: list[tuple[str, str]] = []

    async def load_destinations(self) -> None:
        rows = await self.db.scalars(select(Destination))
        self.destinations = {d.city: d for d in rows}
        needed = {student[2] for student in STUDENTS} | {"Dublin", "Lisbonne", "Madrid", "Berlin"}
        missing = sorted(needed - set(self.destinations))
        if missing:
            sys.exit(f"Missing destinations {missing}: run `python -m seeds.seed` first")

    async def user(self, local: str, name: str, account_type=AccountType.STUDENT, **fields) -> User:
        user = User(
            email=email(local),
            name=name,
            password_hash=self.password_hash,
            account_type=account_type,
            email_verified=True,
            **fields,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def organization(self, slug: str, name: str, color: str) -> Organization:
        organization = Organization(
            name=name,
            slug=slug,
            join_code=generate_join_code(),
            branding={"primary_color": color},
            settings={"alert_threshold": {"progress_below": 50, "days_before_departure": 30}},
        )
        self.db.add(organization)
        await self.db.flush()
        return organization

    async def member(self, organization, local, name, role, countries=()) -> OrganizationMember:
        user = await self.user(local, name, AccountType.ORG_STAFF)
        member = OrganizationMember(organization_id=organization.id, user_id=user.id, org_role=role)
        self.db.add(member)
        await self.db.flush()
        self.db.add_all(
            AdvisorPerimeter(organization_id=organization.id, member_id=member.id, country_code=c)
            for c in countries
        )
        self.summary.append((user.email, f"{role.value} — {organization.name}"))
        return member

    def contract(self, organization, status, start, end, quota=None) -> None:
        self.db.add(
            Contract(
                organization_id=organization.id,
                plan="pilot" if status == ContractStatus.PILOT else "standard",
                status=status,
                start_date=start,
                end_date=end,
                price_cents=0 if status == ContractStatus.PILOT else 120_000,
                student_quota=quota,
                notes="Demo contract",
            )
        )

    async def student(
        self,
        organization,
        local,
        name,
        city,
        mobility_type,
        departure_in_days,
        done_ratio,
        *,
        created_at: datetime | None = None,
        status: str = "preparing",
        return_date: date | None = None,
        joined_at: datetime | None = None,
        overdue: int = 0,
    ) -> tuple[User, Mobility]:
        user = await self.user(local, name)
        if organization:
            self.db.add(
                StudentEnrollment(
                    organization_id=organization.id,
                    student_id=user.id,
                    source=EnrollmentSource.ADMIN,
                    joined_at=joined_at or datetime.now(UTC) - timedelta(days=60),
                )
            )
        destination = self.destinations[city]
        mobility = Mobility(
            user_id=user.id,
            destination_id=destination.id,
            type=mobility_type,
            departure_date=TODAY + timedelta(days=departure_in_days),
            return_date=return_date or TODAY + timedelta(days=departure_in_days + 180),
            status=status,
        )
        if created_at:
            mobility.created_at = created_at
        self.db.add(mobility)
        await self.db.flush()
        tasks = build_template_tasks(
            mobility_id=mobility.id,
            mobility_type=mobility.type,
            departure_date=mobility.departure_date,
            country=destination.country,
        )
        done = round(len(tasks) * done_ratio)
        for task in tasks[:done]:
            task.is_completed = True
        for task in tasks[done : done + overdue]:
            task.deadline = TODAY - timedelta(days=5)
        self.db.add_all(tasks)
        return user, mobility

    def invitation(self, organization, local) -> str:
        token = secrets.token_urlsafe(32)
        self.db.add(
            Invitation(
                organization_id=organization.id,
                email=email(local),
                kind=InvitationKind.STUDENT,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=14),
            )
        )
        return token


async def reset(db: AsyncSession) -> None:
    await db.execute(delete(Organization).where(Organization.slug.in_(SLUGS)))
    await db.execute(delete(User).where(User.email.like(f"%@{DOMAIN}")))
    await db.commit()


async def build(db: AsyncSession) -> None:
    demo = Demo(db)
    await demo.load_destinations()

    admin = await demo.user("admin", "Admin StudaFly", AccountType.PLATFORM_ADMIN)
    demo.summary.append((admin.email, "platform_admin — MFA à configurer à la 1re connexion"))

    school = await demo.organization("ecole-demo", "École Démo", "#33518A")
    demo.contract(
        school, ContractStatus.ACTIVE, TODAY - timedelta(days=60), TODAY + timedelta(days=300), 50
    )
    members = {
        local: await demo.member(school, local, name, role, countries)
        for local, name, role, countries in ADVISORS
    }
    mobilities = {}
    for local, name, city, mobility_type, departure, done in STUDENTS:
        user, mobility = await demo.student(
            school,
            local,
            name,
            city,
            mobility_type,
            departure,
            done,
            overdue=3 if local in LATE_STUDENTS else 0,
        )
        mobilities[local] = (user, mobility)
        demo.summary.append((user.email, f"student — École Démo — {city}"))
    db.add(
        MobilityAdvisorOverride(
            mobility_id=mobilities["lucas.petit"][1].id,
            member_id=members["conseiller.europe"].id,
            set_by=members["manager"].user_id,
        )
    )
    db.add(
        StudentNote(
            organization_id=school.id,
            student_id=mobilities["emma.durand"][0].id,
            author_member_id=members["conseiller.europe"].id,
            body="Rendez-vous visa à confirmer avant la fin du mois.",
        )
    )
    links = [demo.invitation(school, "futur.etudiant1"), demo.invitation(school, "futur.etudiant2")]

    pilot = await demo.organization("ecole-pilote", "École Pilote", "#CC9C40")
    demo.contract(
        pilot, ContractStatus.PILOT, TODAY - timedelta(days=10), TODAY + timedelta(days=80)
    )
    await demo.member(pilot, "pilote.manager", "Paul Pilote", OrgRole.MANAGER, ZONES["europe"])
    for local, name, city in (
        ("pilote.alice", "Alice Pilote", "Dublin"),
        ("pilote.bruno", "Bruno Pilote", "Lisbonne"),
    ):
        user, _ = await demo.student(pilot, local, name, city, "erasmus", 70, 0.3)
        demo.summary.append((user.email, f"student — École Pilote — {city}"))

    expired = await demo.organization("ecole-expiree", "École Expirée", "#6B7280")
    start, end = TODAY - timedelta(days=400), TODAY - timedelta(days=10)
    demo.contract(expired, ContractStatus.EXPIRED, start, end)
    await demo.member(expired, "expiree.manager", "Eva Expirée", OrgRole.MANAGER, ZONES["europe"])
    during = datetime.combine(end - timedelta(days=90), datetime.min.time(), UTC)
    joined = during - timedelta(days=30)
    kept, _ = await demo.student(
        expired,
        "expiree.encours",
        "Élise En-cours",
        "Madrid",
        "semestre",
        -20,
        0.9,
        created_at=during,
        status="departed",
        return_date=TODAY + timedelta(days=150),
        joined_at=joined,
    )
    lost, _ = await demo.student(
        expired,
        "expiree.terminee",
        "Théo Terminé",
        "Berlin",
        "erasmus",
        -200,
        1.0,
        created_at=during,
        status="completed",
        return_date=TODAY - timedelta(days=20),
        joined_at=joined,
    )
    demo.summary.append(
        (kept.email, "student — École Expirée — Premium conservé (mobilité en cours)")
    )
    demo.summary.append((lost.email, "student — École Expirée — Premium perdu (mobilité terminée)"))

    free, _ = await demo.student(None, "libre", "Léo Libre", "Dublin", "erasmus", 100, 0.2)
    paying, _ = await demo.student(None, "premium", "Pia Premium", "Lisbonne", "stage", 80, 0.4)
    db.add(
        PremiumGrant(
            user_id=paying.id,
            source=PremiumSource.PURCHASE,
            stripe_payment_ref="pi_demo_premium",
            amount_cents=999,
            currency="EUR",
        )
    )
    suspended = await demo.user(
        "suspendu",
        "Sam Suspendu",
        status=UserStatus.SUSPENDED,
        suspended_at=datetime.now(UTC),
        suspended_reason="Compte de démonstration suspendu",
    )
    demo.summary += [
        (free.email, "student B2C — gratuit"),
        (paying.email, "student B2C — Premium acheté"),
        (suspended.email, "student — suspendu (connexion refusée)"),
    ]
    await db.commit()

    print(f"\nRoles demo created — password for every account: {PASSWORD}\n")
    for address, role in demo.summary:
        print(f"  {address:<45} {role}")
    print("\nSchool codes:")
    for organization in (school, pilot, expired):
        print(f"  {organization.name:<15} {organization.join_code}")
    print("\nPending invitations (École Démo):")
    for local, token in zip(("futur.etudiant1", "futur.etudiant2"), links, strict=True):
        print(f"  {email(local):<45} /invitations/{token}")
    print()


async def run(reset_first: bool) -> None:
    if settings.APP_ENV == "production":
        sys.exit("The roles demo cannot run in production")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            if reset_first:
                await reset(db)
            elif await db.scalar(select(Organization.id).where(Organization.slug == "ecole-demo")):
                sys.exit("The roles demo already exists: use --reset to recreate it")
            await build(db)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the StudaFly roles demo")
    parser.add_argument("--reset", action="store_true", help="Delete then recreate the demo")
    asyncio.run(run(parser.parse_args().reset))


if __name__ == "__main__":
    main()
