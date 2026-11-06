"""
Smoke check of a running API against a fresh roles demo (make seed-roles-demo).
Usage:
    python -m seeds.demo_check                                  # API on http://localhost:8080
    DEMO_API_URL=http://localhost:8090 python -m seeds.demo_check
    ADMIN_TOTP_SECRET=<secret> python -m seeds.demo_check       # also checks /admin with MFA

Leaves the demo data unchanged: the only writes go to a throwaway account
(smoke-<random>@demo.example.com) that is scheduled for deletion at the end.
Exits with status 1 when a check fails.
"""

import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx
import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seeds.roles_demo import DOMAIN, PASSWORD

BASE_URL = os.environ.get("DEMO_API_URL", "http://localhost:8080").rstrip("/")
API = f"{BASE_URL}/api/v1"

EXPECTED_ACCOUNTS = {
    "emma.durand": ("student", None, "École Démo", "organization"),
    "lucas.petit": ("student", None, "École Démo", "organization"),
    "pilote.alice": ("student", None, "École Pilote", "organization"),
    "expiree.encours": ("student", None, "École Expirée", "grandfathered"),
    "expiree.terminee": ("student", None, "École Expirée", None),
    "libre": ("student", None, None, None),
    "premium": ("student", None, None, "purchase"),
    "manager": ("org_staff", "manager", "École Démo", None),
    "conseiller.europe": ("org_staff", "advisor", "École Démo", None),
    "expiree.manager": ("org_staff", "manager", "École Expirée", None),
}

ADVISOR_VISIBILITY = {
    "manager": 13,
    "conseiller.europe": 5,
    "conseiller.amerique": 2,
    "conseiller.asie": 3,
}


def email(local: str) -> str:
    return f"{local}@{DOMAIN}"


def error_code(response: httpx.Response) -> str | None:
    try:
        return response.json().get("error", {}).get("code")
    except ValueError:
        return None


class Check:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.passed = 0
        self.failures: list[str] = []

    def section(self, title: str) -> None:
        print(f"\n{title}")

    def ok(self, label: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  ✓ {label}")
        else:
            self.failures.append(f"{label} — {detail}" if detail else label)
            print(f"  ✗ {label}  {detail}")
        return condition

    def status(self, label: str, response: httpx.Response, expected: int, code: str | None = None):
        got = (response.status_code, error_code(response))
        matches = response.status_code == expected and (code is None or got[1] == code)
        wanted = f"{expected} {code}" if code else str(expected)
        return self.ok(label, matches, f"expected {wanted}, got {got[0]} {got[1] or ''}".strip())

    def call(self, method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.request(method, f"{API}{path}", headers=headers, **kwargs)

    def login(self, local: str, password: str = PASSWORD) -> httpx.Response:
        return self.call("POST", "/auth/login", json={"email": email(local), "password": password})

    def token(self, local: str) -> str:
        response = self.login(local)
        if response.status_code != 200:
            raise SystemExit(
                f"Login failed for {email(local)} ({response.status_code}). "
                "Run `make seed-roles-demo` first, then retry."
            )
        return response.json()["data"]["accessToken"]


def check_public(c: Check) -> None:
    c.section("1. Public endpoints")
    for path in ("/health", "/reference", "/stats", "/destinations"):
        c.status(f"GET {path}", c.call("GET", path), 200)
    stats = c.call("GET", "/stats").json().get("data") or {}
    c.ok("stats count the demo students", stats.get("students", 0) >= 17, str(stats))


def check_accounts(c: Check, tokens: dict[str, str]) -> None:
    c.section("2. Accounts, organizations and Premium (/users/me)")
    for local, (account_type, org_role, org_name, source) in EXPECTED_ACCOUNTS.items():
        me = c.call("GET", "/users/me", tokens[local]).json()["data"]
        organization = (me.get("organization") or {}).get("name")
        premium = me.get("premium") or {}
        got = (me.get("accountType"), me.get("orgRole"), organization)
        c.ok(
            f"{local}: {account_type}/{org_role or '-'}/{org_name or '-'}",
            got == (account_type, org_role, org_name),
            str(got),
        )
        if account_type == "student":
            c.ok(
                f"{local}: Premium {source or 'inactive'}",
                premium.get("source") == source and premium.get("active") is (source is not None),
                str(premium),
            )
    c.status("suspendu: login refused", c.login("suspendu"), 403, "ACCOUNT_SUSPENDED")
    c.status("wrong password refused", c.login("emma.durand", "wrong-password"), 401)
    admin = c.login("admin").json().get("data") or {}
    c.ok(
        "admin: login asks for MFA", admin.get("mfaRequired") is True, str(admin.get("mfaRequired"))
    )


def students(c: Check, token: str, query: str = "") -> list[dict]:
    response = c.call("GET", f"/org/students?perPage=100{query}", token)
    return response.json().get("data", []) if response.status_code == 200 else []


def check_scoping(c: Check, tokens: dict[str, str]) -> dict:
    c.section("3. Organization scoping (/org)")
    for local, expected in ADVISOR_VISIBILITY.items():
        visible = students(c, tokens[local])
        c.ok(f"{local} sees {expected} students", len(visible) == expected, f"got {len(visible)}")
    europe = {s["name"]: s for s in students(c, tokens["conseiller.europe"])}
    lucas = europe.get("Lucas Petit", {}).get("mobility") or {}
    c.ok(
        "Lucas reaches conseiller.europe by manual assignment",
        lucas.get("assignment") == "override",
        str(lucas.get("assignment")),
    )
    unassigned = [s["name"] for s in students(c, tokens["manager"], "&unassigned=true")]
    c.ok("unassigned = Zoé Blanc", unassigned == ["Zoé Blanc"], str(unassigned))
    danger = sorted(s["name"] for s in students(c, tokens["manager"], "&status=danger"))
    c.ok("critical = Emma Durand", danger == ["Emma Durand"], str(danger))
    warning = sorted(s["name"] for s in students(c, tokens["manager"], "&status=warning"))
    c.ok(
        "late = Sarah Morel, Tom Lefebvre", warning == ["Sarah Morel", "Tom Lefebvre"], str(warning)
    )

    everyone = {s["name"]: s for s in students(c, tokens["manager"])}
    emma, louis = everyone.get("Emma Durand"), everyone.get("Louis Fournier")
    if not (emma and louis):
        c.ok("demo students found", False, "Emma or Louis missing")
        return {}
    c.status(
        "conseiller.europe: Tokyo student is out of scope",
        c.call("GET", f"/org/students/{louis['id']}", tokens["conseiller.europe"]),
        404,
    )
    detail = c.call("GET", f"/org/students/{emma['id']}", tokens["conseiller.europe"])
    c.status("conseiller.europe: Emma's file", detail, 200)
    documents = [
        d
        for m in (detail.json().get("data") or {}).get("mobilities", [])
        for d in m.get("documents", [])
    ]
    c.ok(
        "student file exposes no document URL",
        not any("url" in key.lower() for d in documents for key in d),
        str(documents[:1]),
    )
    notes = (
        c.call("GET", f"/org/students/{emma['id']}/notes", tokens["conseiller.europe"])
        .json()
        .get("data", [])
    )
    c.ok(
        "Emma has the demo note",
        any("visa" in n.get("body", "") for n in notes),
        f"{len(notes)} notes",
    )

    org = c.call("GET", "/org", tokens["conseiller.europe"]).json().get("data") or {}
    c.ok(
        "conseiller.europe zones = europe, africa",
        sorted(org.get("myZones", [])) == ["africa", "europe"],
        str(org.get("myZones")),
    )
    contract = c.call("GET", "/org/contract", tokens["manager"]).json().get("data") or {}
    c.ok(
        "École Démo contract is current, 13 students",
        (contract.get("state"), contract.get("activeStudents")) == ("current", 13),
        str(contract),
    )
    expired = c.call("GET", "/org/contract", tokens["expiree.manager"]).json().get("data") or {}
    c.ok(
        "École Expirée contract is read-only",
        expired.get("state") == "read_only",
        str(expired.get("state")),
    )
    members = c.call("GET", "/org/members", tokens["manager"]).json().get("data", [])
    manager_member = next((m["id"] for m in members if m["orgRole"] == "manager"), None)
    return {"emma": emma, "manager_member": manager_member}


def check_access(c: Check, tokens: dict[str, str], ids: dict) -> None:
    c.section("4. Access control")
    emma_mobility = (ids.get("emma") or {}).get("mobility", {}).get("id", str(uuid.uuid4()))
    join_code = (
        c.call("GET", "/org/join-code", tokens["manager"])
        .json()
        .get("data", {})
        .get("joinCode", "NOPE")
    )
    cases = [
        ("anonymous: /users/me", "GET", "/users/me", None, 401, None, None),
        ("student: /org", "GET", "/org", "emma.durand", 403, None, None),
        ("student: /admin/overview", "GET", "/admin/overview", "emma.durand", 403, None, None),
        ("student: MFA setup", "POST", "/auth/mfa/setup", "emma.durand", 403, None, None),
        (
            "student: another student's mobility",
            "GET",
            f"/mobilities/{emma_mobility}",
            "jules.moreau",
            404,
            None,
            None,
        ),
        ("manager: /admin/overview", "GET", "/admin/overview", "manager", 403, None, None),
        (
            "manager: join a school with a code",
            "POST",
            "/organizations/join",
            "manager",
            403,
            None,
            {"code": join_code},
        ),
        (
            "advisor: school audit log",
            "GET",
            "/org/audit-logs",
            "conseiller.europe",
            403,
            None,
            None,
        ),
        (
            "advisor: another member's perimeter",
            "GET",
            f"/org/members/{ids.get('manager_member')}/perimeter",
            "conseiller.europe",
            403,
            None,
            None,
        ),
        (
            "expired contract: reading still works",
            "GET",
            "/org/students",
            "expiree.manager",
            200,
            None,
            None,
        ),
        (
            "expired contract: inviting is refused",
            "POST",
            "/org/invitations",
            "expiree.manager",
            403,
            "CONTRACT_EXPIRED",
            {"email": "x@example.com"},
        ),
        (
            "admin without MFA: /admin/overview",
            "GET",
            "/admin/overview",
            "admin",
            403,
            "MFA_REQUIRED",
            None,
        ),
    ]
    for label, method, path, actor, expected, code, body in cases:
        token = tokens[actor] if actor else None
        c.status(
            label,
            c.call(method, path, token, json=body) if body else c.call(method, path, token),
            expected,
            code,
        )


def check_sessions(c: Check) -> None:
    c.section("5. Registration and per-device sessions (throwaway account)")
    local = f"smoke-{uuid.uuid4().hex[:8]}"
    registered = c.call(
        "POST",
        "/auth/register",
        json={
            "email": email(local),
            "password": PASSWORD,
            "name": "Smoke",
            "accountType": "platform_admin",
            "role": "superadmin",
        },
    )
    c.status("register", registered, 201)
    account_type = ((registered.json().get("data") or {}).get("user") or {}).get("accountType")
    c.ok("register always creates a student", account_type == "student", str(account_type))

    first, second = (c.login(local).json()["data"] for _ in range(2))
    rotated = c.call("POST", "/auth/refresh", json={"refreshToken": first["refreshToken"]})
    c.status("device 1 refresh still valid after device 2 login", rotated, 200)
    c.status(
        "replayed refresh token refused",
        c.call("POST", "/auth/refresh", json={"refreshToken": first["refreshToken"]}),
        401,
    )
    device_one = rotated.json()["data"]
    c.status("logout device 1", c.call("POST", "/auth/logout", device_one["accessToken"]), 200)
    c.status(
        "device 1 refresh refused after logout",
        c.call("POST", "/auth/refresh", json={"refreshToken": device_one["refreshToken"]}),
        401,
    )
    device_two = c.call("POST", "/auth/refresh", json={"refreshToken": second["refreshToken"]})
    c.status("device 2 still signed in", device_two, 200)
    access = device_two.json().get("data", {}).get("accessToken")
    c.status("export my data", c.call("GET", "/users/me/export", access), 200)
    c.status("delete my account", c.call("DELETE", "/users/me", access), 204)
    c.status(
        "login refused during the 30-day delay", c.login(local), 403, "ACCOUNT_PENDING_DELETION"
    )


def admin_token(c: Check) -> str | None:
    secret = os.environ.get("ADMIN_TOTP_SECRET")
    c.section("6. Platform admin with MFA")
    if not secret:
        print("  – skipped (set ADMIN_TOTP_SECRET to the key shown during the admin MFA setup)")
        return None
    pending = c.login("admin").json()["data"]["accessToken"]
    verified = c.call("POST", "/auth/mfa/verify", pending, json={"code": pyotp.TOTP(secret).now()})
    if error_code(verified) == "INVALID_MFA_CODE":
        print("  … code already used in this 30 s window, waiting for the next one")
        time.sleep(30 - time.time() % 30 + 1)
        verified = c.call(
            "POST", "/auth/mfa/verify", pending, json={"code": pyotp.TOTP(secret).now()}
        )
    if not c.status("MFA verification", verified, 200):
        return None
    token = verified.json()["data"]["accessToken"]
    c.status("GET /admin/overview", c.call("GET", "/admin/overview", token), 200)
    staff = c.call("GET", "/admin/users?q=demo&accountType=org_staff", token).json()
    c.ok("6 demo staff accounts", staff.get("total") == 6, str(staff.get("total")))
    purchases = c.call("GET", "/admin/purchases", token).text
    c.ok("demo purchase listed", "pi_demo_premium" in purchases)
    return token


def check_no_server_errors(c: Check, tokens: dict[str, str], ids: dict, admin: str | None) -> None:
    c.section("7. Every GET route × every profile: no 5xx")
    emma = ids.get("emma") or {}
    mobility_id = (emma.get("mobility") or {}).get("id")
    mobility = (
        c.call("GET", f"/mobilities/{mobility_id}", tokens["emma.durand"]).json().get("data") or {}
    )
    organizations = (
        c.call("GET", "/admin/organizations", admin).json().get("data", []) if admin else []
    )
    params = {
        "mobility_id": mobility_id,
        "destination_id": mobility.get("destinationId"),
        "student_id": emma.get("id"),
        "user_id": emma.get("id"),
        "member_id": ids.get("manager_member"),
        "organization_id": organizations[0]["id"] if organizations else None,
        "code": "UNKNOWN000",
        "token": "unknown-token",
    }
    actors = {
        "anonymous": None,
        **{k: tokens[k] for k in ("emma.durand", "manager", "conseiller.europe", "admin")},
    }
    if admin:
        actors["admin+mfa"] = admin
    spec = c.client.get(f"{BASE_URL}/openapi.json").json()
    routes = [p for p, ops in spec["paths"].items() if "get" in ops and p.startswith("/api/v1")]
    errors, not_implemented = [], set()
    for route in routes:
        path = re.sub(
            r"\{(\w+)\}",
            lambda m: str(params.get(m.group(1)) or uuid.uuid4()),
            route.removeprefix("/api/v1"),
        )
        for actor, token in actors.items():
            response = c.call("GET", path, token)
            if response.status_code == 501:
                not_implemented.add(route.removeprefix("/api/v1"))
            elif response.status_code >= 500:
                errors.append(f"{response.status_code} GET {path} as {actor}")
    c.ok(f"{len(routes)} routes × {len(actors)} profiles", not errors, "; ".join(errors))
    for route in sorted(not_implemented):
        print(f"  – not implemented yet (501): GET {route}")


def main() -> int:
    with httpx.Client(timeout=15) as client:
        c = Check(client)
        try:
            client.get(f"{API}/health")
        except httpx.ConnectError:
            print(f"API unreachable at {API} — start it with `make run`.")
            return 1
        print(f"StudaFly demo check — {API}")
        check_public(c)
        actors = {*EXPECTED_ACCOUNTS, *ADVISOR_VISIBILITY, "jules.moreau", "admin"}
        tokens = {local: c.token(local) for local in actors}
        check_accounts(c, tokens)
        ids = check_scoping(c, tokens)
        check_access(c, tokens, ids)
        check_sessions(c)
        admin = admin_token(c)
        check_no_server_errors(c, tokens, ids, admin)

    print(f"\n{c.passed} passed, {len(c.failures)} failed")
    for failure in c.failures:
        print(f"  ✗ {failure}")
    return 1 if c.failures else 0


if __name__ == "__main__":
    sys.exit(main())
