import argparse
import asyncio
import getpass
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.core.config import settings
from src.app.core.exceptions import StudaFlyException
from src.app.services import (
    account_service,
    contract_service,
    notification_service,
    platform_admin_service,
)


async def _with_session(action: Callable[[AsyncSession], Awaitable]):
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await action(db)
    finally:
        await engine.dispose()


def _read_password() -> str:
    password = getpass.getpass("Password (min. 8 characters): ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters")
    if getpass.getpass("Confirm password: ") != password:
        sys.exit("Passwords do not match")
    return password


def create_platform_admin(email: str, name: str | None) -> None:
    existing = asyncio.run(
        _with_session(lambda db: platform_admin_service.find_by_email(db, email))
    )
    password = None if existing else _read_password()
    user, changed = asyncio.run(
        _with_session(
            lambda db: platform_admin_service.grant_platform_admin(db, email, name, password)
        )
    )
    if not changed:
        print(f"{user.email} is already a platform admin")
        return
    print(f"{user.email} is now a platform admin. MFA must be set up at the next sign-in.")


def revoke_platform_admin(email: str) -> None:
    user = asyncio.run(
        _with_session(lambda db: platform_admin_service.revoke_platform_admin(db, email))
    )
    print(f"{user.email} is no longer a platform admin (now a student account)")


async def _maintenance(db: AsyncSession, tasks: tuple[str, ...]) -> dict:
    results = {}
    if "contracts" in tasks:
        results["expired_contracts"] = await contract_service.expire_contracts(db)
    if "invitations" in tasks:
        results["expired_invitations"] = await account_service.expire_invitations(db)
    if "accounts" in tasks:
        report = await account_service.purge_due_accounts(db)
        results["purged_accounts"] = report.purged
        results["skipped_accounts"] = report.skipped
    if "audit" in tasks:
        results["purged_audit_logs"] = await account_service.purge_audit_logs(db)
    if "reminders" in tasks:
        results["deadline_reminders"] = await notification_service.send_deadline_reminders(db)
    return results


def run_maintenance(*tasks: str) -> None:
    results = asyncio.run(_with_session(lambda db: _maintenance(db, tasks)))
    for key, value in results.items():
        print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.cli", description="StudaFly administration commands"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    grant = commands.add_parser("create-platform-admin", help="Create or promote a platform admin")
    grant.add_argument("--email", required=True)
    grant.add_argument("--name")
    revoke = commands.add_parser("revoke-platform-admin", help="Remove the platform admin rights")
    revoke.add_argument("--email", required=True)
    commands.add_parser("expire-contracts", help="Mark ended contracts as expired")
    commands.add_parser("purge-deleted-users", help="Delete accounts whose grace period is over")
    commands.add_parser("send-reminders", help="Notify students about upcoming task deadlines")
    commands.add_parser(
        "maintenance", help="Daily jobs: contracts, invitations, purge, audit, reminders"
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "create-platform-admin":
            create_platform_admin(args.email, args.name)
        elif args.command == "revoke-platform-admin":
            revoke_platform_admin(args.email)
        elif args.command == "expire-contracts":
            run_maintenance("contracts")
        elif args.command == "purge-deleted-users":
            run_maintenance("accounts")
        elif args.command == "send-reminders":
            run_maintenance("reminders")
        else:
            run_maintenance("contracts", "invitations", "accounts", "audit", "reminders")
    except StudaFlyException as exc:
        sys.exit(f"Error: {exc.message}")


if __name__ == "__main__":
    main()
