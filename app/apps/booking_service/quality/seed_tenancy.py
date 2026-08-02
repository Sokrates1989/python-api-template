"""Seed deterministic, non-personal tenants for disposable live proofs.

The command receives Keycloak subject identifiers from the quality runner only
after real token projection succeeds. It stores no token or credential and is
not registered as an API route or production startup hook.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.models.tenancy import (
    BookingOrganization,
    BookingPlatformAccess,
    BookingSubject,
    OrganizationMembership,
    OrganizationMembershipRole,
)
from apps.booking_service.repositories.company_settings_repository import (
    CompanySettingsRepository,
)
from backend.database import close_database, get_database_handler, initialize_database


def build_parser() -> argparse.ArgumentParser:
    """Build the exact command-line contract for tenancy fixture seeding.

    Returns:
        argparse.ArgumentParser: Parser requiring four subjects and two tenants,
            with an optional customer membership used by persistent manual tests.
    """
    parser = argparse.ArgumentParser(description="Seed Booking tenancy proof data.")
    for role in ("platform", "organization-admin", "worker", "customer"):
        parser.add_argument(f"--{role}-subject", required=True)
    parser.add_argument("--organization-a-id", required=True)
    parser.add_argument("--organization-a-name", required=True)
    parser.add_argument("--organization-b-id", required=True)
    parser.add_argument("--organization-b-name", required=True)
    parser.add_argument("--customer-organization-id")
    return parser


async def _ensure_subject(session: AsyncSession, subject_id: str) -> BookingSubject:
    """Load or stage one active non-personal proof subject.

    Args:
        session: Async SQLAlchemy session used by the seed transaction.
        subject_id: Real Keycloak subject projected by the live API.

    Returns:
        BookingSubject: Existing or newly staged active subject.
    """
    subject = await session.get(BookingSubject, subject_id)
    if subject is None:
        subject = BookingSubject(subject_id=subject_id, status="active", revision=1)
        session.add(subject)
        await session.flush()
    return subject


async def _ensure_organization(
    session: AsyncSession,
    organization_id: str,
    display_name: str,
) -> BookingOrganization:
    """Load or stage one active deterministic proof organization.

    Args:
        session: Async SQLAlchemy session used by the seed transaction.
        organization_id: Stable quality-only UUID.
        display_name: Neutral quality-only display name.

    Returns:
        BookingOrganization: Existing or staged active organization.
    """
    organization = await session.get(BookingOrganization, organization_id)
    if organization is None:
        organization = BookingOrganization(
            id=organization_id,
            display_name=display_name,
            status="active",
            revision=1,
        )
        session.add(organization)
        await session.flush()
    return organization


async def _ensure_membership(
    session: AsyncSession,
    organization_id: str,
    subject_id: str,
    role: str,
) -> None:
    """Ensure one active membership with exactly one role for live proofs.

    Args:
        session: Async SQLAlchemy session used by the seed transaction.
        organization_id: Tenant owning the membership and role.
        subject_id: Keycloak subject assigned to the tenant.
        role: Exact membership role compatible with the subject's coarse role.

    Returns:
        None: The idempotent membership and role remain staged.
    """
    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.subject_id == subject_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        membership_id = str(uuid5(NAMESPACE_URL, f"{organization_id}:{subject_id}"))
        membership = OrganizationMembership(
            id=membership_id,
            organization_id=organization_id,
            subject_id=subject_id,
            status="active",
            revision=1,
        )
        session.add(membership)
        await session.flush()
    role_key = (organization_id, membership.id, role)
    if await session.get(OrganizationMembershipRole, role_key) is None:
        session.add(
            OrganizationMembershipRole(
                organization_id=organization_id,
                membership_id=membership.id,
                role=role,
            )
        )


async def seed(args: argparse.Namespace) -> None:
    """Seed platform access plus two-tenant membership fixtures atomically.

    Args:
        args: Parsed subject and organization fixture values.

    Returns:
        None: Changes are committed once every fixture is staged.

    Raises:
        ValueError: When an optional customer organization is not one of the
            two deterministic fixture organizations.
        RuntimeError: When selected-app database startup is unavailable.
        SQLAlchemyError: When a constraint or database operation fails.
    """
    handler = get_database_handler()
    async with handler.AsyncSessionLocal() as session:
        for subject_id in (
            args.platform_subject,
            args.organization_admin_subject,
            args.worker_subject,
            args.customer_subject,
        ):
            await _ensure_subject(session, subject_id)
        if await session.get(BookingPlatformAccess, args.platform_subject) is None:
            session.add(
                BookingPlatformAccess(
                    subject_id=args.platform_subject,
                    status="active",
                    approved_by_subject_id=args.platform_subject,
                    revision=1,
                )
            )
        organization_a = await _ensure_organization(
            session,
            args.organization_a_id,
            args.organization_a_name,
        )
        organization_b = await _ensure_organization(
            session,
            args.organization_b_id,
            args.organization_b_name,
        )
        settings = CompanySettingsRepository(session)
        await settings.ensure_defaults(organization_a.id, organization_a.display_name)
        await settings.ensure_defaults(organization_b.id, organization_b.display_name)
        await _ensure_membership(
            session,
            args.organization_a_id,
            args.organization_admin_subject,
            "organization_admin",
        )
        await _ensure_membership(
            session,
            args.organization_b_id,
            args.organization_admin_subject,
            "organization_admin",
        )
        await _ensure_membership(session, args.organization_a_id, args.worker_subject, "worker")
        if args.customer_organization_id:
            if args.customer_organization_id not in {
                args.organization_a_id,
                args.organization_b_id,
            }:
                raise ValueError(
                    "Customer organization must be one of the fixture organizations."
                )
            await _ensure_membership(
                session,
                args.customer_organization_id,
                args.customer_subject,
                "customer",
            )
        await session.commit()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the bounded seed command and execute its async transaction.

    Args:
        argv: Optional argument sequence; defaults to process arguments.

    Returns:
        int: Zero after successful seeding.
    """
    asyncio.run(_run_seed(build_parser().parse_args(argv)))
    return 0


async def _run_seed(args: argparse.Namespace) -> None:
    """Own standalone database initialization around one seed transaction.

    Args:
        args: Parsed subject and organization fixture values.

    Returns:
        None: Database resources are closed after successful or failed seeding.

    Raises:
        RuntimeError: When the selected database does not initialize cleanly.
        SQLAlchemyError: When the seed transaction fails.
    """
    result = await initialize_database()
    if result.get("status") != "success":
        raise RuntimeError("Booking quality database initialization failed.")
    try:
        await seed(args)
    finally:
        await close_database()


if __name__ == "__main__":
    raise SystemExit(main())
