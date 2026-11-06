"""Notifications: in-app list, push tokens, Expo delivery, deadline reminders, invitations."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from src.app.core.config import settings
from src.app.models.enums import NotificationType, PushPlatform, UserStatus
from src.app.models.mobility import Mobility
from src.app.models.notification import Notification
from src.app.models.push_token import PushToken
from src.app.models.task import Task
from src.app.services import invitation_service, notification_service

from tests.db.factories import (
    PASSWORD,
    auth_headers,
    make_destination,
    make_mobility,
    make_user,
)

TOKEN = "ExponentPushToken[device-one]"


class FakeExpo(list):
    """Messages sent to Expo; `errors` maps a token to the ticket error Expo answers for it."""

    def __init__(self):
        super().__init__()
        self.errors: dict[str, str] = {}


@pytest.fixture
def expo(monkeypatch) -> FakeExpo:
    """Fake Expo push API: records the messages and answers "ok" unless told otherwise."""
    sent = FakeExpo()
    errors = sent.errors

    async def post(messages):
        sent.extend(messages)
        return [
            {"status": "error", "message": "nope", "details": {"error": errors[m["to"]]}}
            if m["to"] in errors
            else {"status": "ok", "id": "ticket"}
            for m in messages
        ]

    monkeypatch.setattr(notification_service, "_post_to_expo", post)
    monkeypatch.setattr(settings, "PUSH_NOTIFICATIONS_ENABLED", True)
    return sent


@pytest.fixture
def links(monkeypatch) -> dict[str, str]:
    sent: dict[str, str] = {}
    monkeypatch.setattr(
        invitation_service, "_log_link", lambda email, token: sent.__setitem__(email, token)
    )
    return sent


async def _notify(db, user, title="Hello", **kwargs) -> Notification:
    notification = await notification_service.notify(
        db, user.id, NotificationType.TASK_DUE_SOON, title, "Body", {"taskId": "t"}, **kwargs
    )
    await db.commit()
    return notification


async def _task(db, student, deadline: date | None, **fields) -> Task:
    mobility = fields.pop("mobility", None) or await make_mobility(
        db, student, await make_destination(db)
    )
    task = Task(
        mobility_id=mobility.id,
        title=fields.pop("title", "Send the learning agreement"),
        category="admin",
        deadline=deadline,
        is_completed=fields.pop("is_completed", False),
        priority=1,
    )
    db.add(task)
    await db.flush()
    return task


async def _count(db, **filters) -> int:
    query = select(func.count()).select_from(Notification)
    for key, value in filters.items():
        query = query.where(getattr(Notification, key) == value)
    return await db.scalar(query)


# --- In-app list -------------------------------------------------------------------------------


async def test_list_is_newest_first_with_unread_count(api, db):
    student = await make_user(db)
    await _notify(db, student, "First")
    await _notify(db, student, "Second")
    await _notify(db, await make_user(db), "Someone else")

    response = await api.get("/notifications", headers=auth_headers(student))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [n["title"] for n in data["items"]] == ["Second", "First"]
    assert data["unreadCount"] == 2
    first = data["items"][0]
    assert first["type"] == "task_due_soon"
    assert first["data"] == {"taskId": "t"}
    assert (first["isRead"], first["readAt"]) == (False, None)


async def test_unread_only_filter_limit_and_count(api, db):
    student = await make_user(db)
    read = await _notify(db, student, "Read")
    await _notify(db, student, "Unread 1")
    await _notify(db, student, "Unread 2")
    headers = auth_headers(student)
    await api.patch(f"/notifications/{read.id}/read", headers=headers)

    unread = await api.get("/notifications", params={"unreadOnly": "true"}, headers=headers)
    limited = await api.get("/notifications", params={"limit": 1}, headers=headers)
    count = await api.get("/notifications/unread-count", headers=headers)

    assert {n["title"] for n in unread.json()["data"]["items"]} == {"Unread 1", "Unread 2"}
    assert len(limited.json()["data"]["items"]) == 1
    assert count.json()["data"] == {"count": 2}


async def test_mark_read_read_all_and_delete(api, db):
    student = await make_user(db)
    one = await _notify(db, student, "One")
    two = await _notify(db, student, "Two")
    headers = auth_headers(student)

    marked = await api.patch(f"/notifications/{one.id}/read", headers=headers)
    again = await api.patch(f"/notifications/{one.id}/read", headers=headers)
    read_all = await api.post("/notifications/read-all", headers=headers)
    deleted = await api.delete(f"/notifications/{two.id}", headers=headers)

    assert marked.json()["data"]["isRead"] is True
    assert marked.json()["data"]["readAt"] is not None
    assert again.json()["data"]["readAt"] == marked.json()["data"]["readAt"]
    assert read_all.json()["data"] == {"updated": 1}
    assert deleted.status_code == 204
    assert await _count(db, user_id=student.id) == 1
    assert await _count(db, user_id=student.id, is_read=False) == 0


async def test_cannot_touch_someone_elses_notification(api, db):
    owner = await make_user(db)
    notification = await _notify(db, owner)
    intruder = auth_headers(await make_user(db))
    await db.commit()

    read = await api.patch(f"/notifications/{notification.id}/read", headers=intruder)
    delete = await api.delete(f"/notifications/{notification.id}", headers=intruder)
    read_all = await api.post("/notifications/read-all", headers=intruder)

    assert (read.status_code, delete.status_code) == (404, 404)
    assert read_all.json()["data"] == {"updated": 0}
    assert await _count(db, user_id=owner.id, is_read=False) == 1


# --- Push tokens -------------------------------------------------------------------------------


async def test_register_is_idempotent_and_moves_the_device_to_the_new_account(api, db):
    first, second = await make_user(db), await make_user(db)
    await db.commit()
    body = {"token": TOKEN, "platform": "ios"}

    for _ in range(2):
        response = await api.post(
            "/notifications/push-tokens", json=body, headers=auth_headers(first)
        )
        assert response.status_code == 204, response.text
    await api.post(
        "/notifications/push-tokens",
        json={**body, "platform": "android"},
        headers=auth_headers(second),
    )

    tokens = (await db.scalars(select(PushToken))).all()
    assert [(t.user_id, t.platform) for t in tokens] == [(second.id, "android")]


@pytest.mark.parametrize(
    "body",
    [
        {"token": "not-an-expo-token", "platform": "ios"},
        {"token": TOKEN, "platform": "windows"},
        {"token": TOKEN, "platform": "ios", "extra": 1},
    ],
    ids=["bad-token", "bad-platform", "extra-field"],
)
async def test_register_validates_the_payload(api, db, body):
    student = await make_user(db)
    await db.commit()

    response = await api.post(
        "/notifications/push-tokens", json=body, headers=auth_headers(student)
    )

    assert response.status_code == 422


async def test_unregister_only_removes_your_own_device(api, db):
    owner, other = await make_user(db), await make_user(db)
    await db.commit()
    await notification_service.register_push_token(db, owner.id, TOKEN, PushPlatform.IOS)

    foreign = await api.delete(
        "/notifications/push-tokens", params={"token": TOKEN}, headers=auth_headers(other)
    )
    own = await api.delete(
        "/notifications/push-tokens", params={"token": TOKEN}, headers=auth_headers(owner)
    )

    assert (foreign.status_code, own.status_code) == (204, 204)
    assert await db.scalar(select(func.count()).select_from(PushToken)) == 0


# --- Delivery ----------------------------------------------------------------------------------


async def test_deliver_pushes_to_every_device_and_drops_dead_tokens(db, expo):
    student = await make_user(db)
    await db.commit()
    dead = "ExponentPushToken[dead]"
    await notification_service.register_push_token(db, student.id, TOKEN, PushPlatform.IOS)
    await notification_service.register_push_token(db, student.id, dead, PushPlatform.ANDROID)
    expo.errors[dead] = "DeviceNotRegistered"
    notification = await _notify(db, student, "Due soon")

    report = await notification_service.deliver(db, [notification])

    assert (report.sent, report.failed, report.removed_tokens) == (1, 1, 1)
    assert {m["to"] for m in expo} == {TOKEN, dead}
    assert expo[0]["title"] == "Due soon"
    assert expo[0]["data"]["notificationId"] == str(notification.id)
    assert expo[0]["data"]["taskId"] == "t"
    assert (await db.scalars(select(PushToken.token))).all() == [TOKEN]


async def test_no_push_when_the_user_disabled_notifications(db, expo):
    student = await make_user(db, enable_notifications=False)
    await db.commit()
    await notification_service.register_push_token(db, student.id, TOKEN, PushPlatform.IOS)

    report = await notification_service.deliver(db, [await _notify(db, student)])

    assert (report.sent, expo) == (0, [])
    assert await _count(db, user_id=student.id) == 1  # still in the in-app list


async def test_no_push_when_disabled_by_config(db, expo, monkeypatch):
    monkeypatch.setattr(settings, "PUSH_NOTIFICATIONS_ENABLED", False)
    student = await make_user(db)
    await db.commit()
    await notification_service.register_push_token(db, student.id, TOKEN, PushPlatform.IOS)

    await notification_service.deliver(db, [await _notify(db, student)])

    assert expo == []


async def test_expo_outage_does_not_raise(db, monkeypatch):
    import httpx

    async def down(messages):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(notification_service, "_post_to_expo", down)
    monkeypatch.setattr(settings, "PUSH_NOTIFICATIONS_ENABLED", True)
    student = await make_user(db)
    await db.commit()
    await notification_service.register_push_token(db, student.id, TOKEN, PushPlatform.IOS)

    report = await notification_service.deliver(db, [await _notify(db, student)])

    assert (report.sent, report.failed) == (0, 1)


async def test_dedupe_key_creates_the_notification_once(db):
    student = await make_user(db)
    await db.commit()

    first = await _notify(db, student, dedupe_key="same")
    second = await _notify(db, student, dedupe_key="same")
    other_user = await _notify(db, await make_user(db), dedupe_key="same")

    assert first is not None and other_user is not None
    assert second is None
    assert await _count(db, user_id=student.id) == 1


# --- Deadline reminders ------------------------------------------------------------------------


async def test_reminders_stages_and_idempotence(db, expo):
    today = date(2026, 11, 6)
    student = await make_user(db)
    week = await _task(db, student, today + timedelta(days=5), title="Week")
    tomorrow = await _task(db, student, today + timedelta(days=1), title="Tomorrow")
    due_today = await _task(db, student, today, title="Today")
    overdue = await _task(db, student, today - timedelta(days=2), title="Late")
    await _task(db, student, today + timedelta(days=30), title="Far")
    await _task(db, student, today - timedelta(days=60), title="Ancient")
    await _task(db, student, None, title="No deadline")
    await _task(db, student, today, title="Done", is_completed=True)
    await db.commit()
    await notification_service.register_push_token(db, student.id, TOKEN, PushPlatform.IOS)

    created = await notification_service.send_deadline_reminders(db, today=today)
    rerun = await notification_service.send_deadline_reminders(db, today=today)

    assert (created, rerun) == (4, 0)
    rows = {
        n.data["taskId"]: (n.type, n.body)
        for n in await db.scalars(select(Notification).where(Notification.user_id == student.id))
    }
    assert rows == {
        str(week.id): ("task_due_soon", "« Week » est à faire dans 5 jours."),
        str(tomorrow.id): ("task_due_soon", "« Tomorrow » est à faire pour demain."),
        str(due_today.id): ("task_due_today", "« Today » est à faire aujourd'hui."),
        str(overdue.id): ("task_overdue", "« Late » devait être faite il y a 2 jours."),
    }
    assert len(expo) == 4


async def test_next_stage_is_sent_and_a_new_deadline_restarts_the_reminders(db):
    today = date(2026, 11, 6)
    student = await make_user(db)
    task = await _task(db, student, today + timedelta(days=3))
    await db.commit()

    day_one = await notification_service.send_deadline_reminders(db, today=today)
    day_two = await notification_service.send_deadline_reminders(
        db, today=today + timedelta(days=1)
    )
    tomorrow = await notification_service.send_deadline_reminders(
        db, today=today + timedelta(days=2)
    )
    task.deadline = today + timedelta(days=10)
    await db.commit()
    rescheduled = await notification_service.send_deadline_reminders(
        db, today=today + timedelta(days=4)
    )

    assert (day_one, day_two, tomorrow, rescheduled) == (1, 0, 1, 1)


async def test_no_reminders_for_finished_mobilities_or_inactive_accounts(db):
    today = date(2026, 11, 6)
    student = await make_user(db)
    task = await _task(db, student, today)
    mobility = await db.get(Mobility, task.mobility_id)
    mobility.status = "completed"
    suspended = await make_user(db, status=UserStatus.SUSPENDED)
    await _task(db, suspended, today)
    await db.commit()

    assert await notification_service.send_deadline_reminders(db, today=today) == 0


# --- Invitations -------------------------------------------------------------------------------


async def test_existing_student_is_notified_of_an_invitation(api, db, school, links, expo):
    student = await make_user(db, email="known@example.com")
    await db.commit()
    await notification_service.register_push_token(db, student.id, TOKEN, PushPlatform.IOS)

    response = await api.post(
        "/org/invitations", json={"email": "Known@example.com"}, headers=school.headers("europe")
    )
    await api.post(
        "/org/invitations", json={"email": "nobody@example.com"}, headers=school.headers("europe")
    )

    assert response.status_code == 201, response.text
    notification = await db.scalar(select(Notification).where(Notification.user_id == student.id))
    assert notification.type == "organization_invitation"
    assert notification.title == "École Démo t'invite à rejoindre son espace"
    assert notification.data["organizationId"] == str(school.organization.id)
    assert [m["to"] for m in expo] == [TOKEN]
    assert await _count(db) == 1


async def test_csv_import_notifies_existing_students(api, db, school, links):
    student = await make_user(db, email="csv-known@example.com")
    await db.commit()

    response = await api.post(
        "/org/invitations/import",
        files={"file": ("s.csv", b"email\ncsv-known@example.com\nnew@example.com\n", "text/csv")},
        headers=school.headers("europe"),
    )

    assert response.status_code == 200, response.text
    assert await _count(db) == 1
    assert await _count(db, user_id=student.id, type="organization_invitation") == 1


async def test_the_inviter_is_notified_when_the_invitation_is_accepted(api, db, school, links):
    await api.post(
        "/org/invitations", json={"email": "lucas@example.com"}, headers=school.headers("europe")
    )
    register = await api.post(
        "/auth/register", json={"email": "lucas@example.com", "password": PASSWORD, "name": "Lucas"}
    )
    token = register.json()["data"]["accessToken"]
    assert await _count(db) == 0  # Lucas had no account when he was invited

    accepted = await api.post(
        f"/invitations/{links['lucas@example.com']}/accept",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert accepted.status_code == 200, accepted.text
    notification = await db.scalar(select(Notification))
    assert notification.user_id == school.staff["europe"].id
    assert notification.type == "invitation_accepted"
    assert notification.body == "Lucas a rejoint École Démo."
