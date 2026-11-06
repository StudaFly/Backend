from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from src.app.core.zones import ZONES
from src.app.models.advisor_perimeter import AdvisorPerimeter
from src.app.models.enums import OrgRole
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.task import Task
from src.app.models.user import User

from tests.db.factories import (
    auth_headers,
    make_destination,
    make_enrollment,
    make_member,
    make_mobility,
    make_organization,
    make_user,
)


@dataclass
class School:
    organization: Organization
    members: dict[str, OrganizationMember] = field(default_factory=dict)
    staff: dict[str, User] = field(default_factory=dict)
    students: dict[str, User] = field(default_factory=dict)
    mobilities: dict = field(default_factory=dict)
    other_organization: Organization | None = None
    other_manager: User | None = None
    other_student: User | None = None

    def headers(self, who: str) -> dict[str, str]:
        return auth_headers(self.staff[who])


async def _staff(db: AsyncSession, school: School, key: str, role: OrgRole, countries):
    member = await make_member(db, school.organization, role)
    school.members[key] = member
    school.staff[key] = await db.get(User, member.user_id)
    for code in countries:
        db.add(
            AdvisorPerimeter(
                organization_id=school.organization.id, member_id=member.id, country_code=code
            )
        )


async def build_school(db: AsyncSession) -> School:
    school = School(organization=await make_organization(db, name="École Démo"))
    await _staff(db, school, "manager", OrgRole.MANAGER, ZONES["latin_america"])
    await _staff(db, school, "europe", OrgRole.ADVISOR, ZONES["europe"] + ZONES["africa"])
    await _staff(db, school, "north_america", OrgRole.ADVISOR, ("US", "CA"))
    await _staff(db, school, "asia", OrgRole.ADVISOR, ZONES["asia"])

    destinations = {
        "madrid": await make_destination(db, country="Espagne", country_code="ES", city="Madrid"),
        "new_york": await make_destination(
            db, country="États-Unis", country_code="US", city="New York"
        ),
        "tokyo": await make_destination(db, country="Japon", country_code="JP", city="Tokyo"),
        "sydney": await make_destination(db, country="Australie", country_code="AU", city="Sydney"),
        "lima": await make_destination(db, country="Pérou", country_code="PE", city="Lima"),
    }
    for key, destination in destinations.items():
        student = await make_user(db, name=f"Student {key}", email=f"{key}@example.com")
        await make_enrollment(db, school.organization, student)
        school.students[key] = student
        school.mobilities[key] = await make_mobility(db, student, destination)

    school.other_organization = await make_organization(db, name="École Pilote")
    other = await make_member(db, school.other_organization, OrgRole.MANAGER)
    school.other_manager = await db.get(User, other.user_id)
    school.other_student = await make_user(db, email="other-school@example.com")
    await make_enrollment(db, school.other_organization, school.other_student)
    await make_mobility(db, school.other_student, destinations["madrid"])
    await db.commit()
    return school


async def add_tasks(db: AsyncSession, mobility, *, done: int, todo: int, overdue: int = 0):
    for i in range(done):
        db.add(
            Task(
                mobility_id=mobility.id,
                title=f"Done {i}",
                category="admin",
                priority=2,
                is_completed=True,
            )
        )
    for i in range(todo):
        db.add(Task(mobility_id=mobility.id, title=f"Todo {i}", category="finance", priority=2))
    for i in range(overdue):
        db.add(
            Task(
                mobility_id=mobility.id,
                title=f"Late {i}",
                category="health",
                priority=1,
                deadline=date.today() - timedelta(days=3),
            )
        )
    await db.commit()
