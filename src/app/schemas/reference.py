from src.app.schemas.common import StudaFlyBaseModel


class MobilityTypeOption(StudaFlyBaseModel):
    key: str
    label: str
    description: str


class LabelledKey(StudaFlyBaseModel):
    key: str
    label: str


class PriorityOption(StudaFlyBaseModel):
    value: int
    label: str


class ReferenceData(StudaFlyBaseModel):
    mobility_types: list[MobilityTypeOption]
    task_categories: list[LabelledKey]
    task_priorities: list[PriorityOption]
    avatar_emojis: list[str]


class PublicStats(StudaFlyBaseModel):
    countries: int
    destinations: int
    students: int
    preparation_steps: int
