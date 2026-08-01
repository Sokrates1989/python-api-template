"""Persistence model for Booking Service identity and tenant ownership.

Composite constraints bind membership roles to their organization. This makes
cross-tenant role attachment invalid at the database boundary in addition to
the repository's mandatory organization predicates.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from models.sql.base import Base


class BookingSubject(Base):
    """Store app-owned lifecycle state keyed by immutable Keycloak subject."""

    __tablename__ = "booking_subjects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'deletion_pending')",
            name="ck_booking_subject_status",
        ),
    )

    subject_id = Column(String(255), primary_key=True)
    status = Column(String(32), nullable=False, default="active")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BookingPlatformAccess(Base):
    """Store the app-owned half of dual-gated platform administration."""

    __tablename__ = "booking_platform_access"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_booking_platform_access_status",
        ),
    )

    subject_id = Column(
        String(255), ForeignKey("booking_subjects.subject_id"), primary_key=True
    )
    status = Column(String(32), nullable=False, default="active")
    approved_by_subject_id = Column(String(255), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BookingOrganization(Base):
    """Represent one tenant and its reversible operational lifecycle."""

    __tablename__ = "booking_organizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_booking_organization_status",
        ),
    )

    id = Column(String(36), primary_key=True)
    display_name = Column(String(160), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrganizationMembership(Base):
    """Bind one Booking subject to one organization with lifecycle state."""

    __tablename__ = "booking_organization_memberships"
    __table_args__ = (
        CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'revoked')",
            name="ck_booking_membership_status",
        ),
        UniqueConstraint(
            "organization_id", "subject_id", name="uq_booking_membership_org_subject"
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_booking_membership_org_id"
        ),
        Index("ix_booking_membership_subject_status", "subject_id", "status"),
    )

    id = Column(String(36), primary_key=True)
    organization_id = Column(
        String(36), ForeignKey("booking_organizations.id"), nullable=False
    )
    subject_id = Column(String(255), ForeignKey("booking_subjects.subject_id"), nullable=False)
    status = Column(String(32), nullable=False, default="invited")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrganizationMembershipRole(Base):
    """Attach a constrained role to a membership in the same organization."""

    __tablename__ = "booking_organization_membership_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            [
                "booking_organization_memberships.organization_id",
                "booking_organization_memberships.id",
            ],
            name="fk_booking_role_membership_scope",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "role IN ('organization_admin', 'worker', 'customer')",
            name="ck_booking_membership_role",
        ),
    )

    organization_id = Column(String(36), primary_key=True)
    membership_id = Column(String(36), primary_key=True)
    role = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BookingIdentityRoleOutbox(Base):
    """Persist retryable Keycloak client-role synchronization intent."""

    __tablename__ = "booking_identity_role_outbox"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            [
                "booking_organization_memberships.organization_id",
                "booking_organization_memberships.id",
            ],
            name="fk_booking_identity_outbox_membership_scope",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_booking_identity_outbox_status",
        ),
        Index(
            "ix_booking_identity_outbox_status_created",
            "status",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), nullable=False)
    membership_id = Column(String(36), nullable=False)
    subject_id = Column(String(255), nullable=False)
    roles = Column(JSON, nullable=False)
    membership_revision = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error_code = Column(String(80), nullable=True)
    retryable = Column(Boolean, nullable=False, default=True)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BookingAuditEvent(Base):
    """Record immutable security-relevant Booking Service lifecycle events."""

    __tablename__ = "booking_audit_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('succeeded', 'denied')",
            name="ck_booking_audit_outcome",
        ),
        Index("ix_booking_audit_resource", "resource_type", "resource_id"),
    )

    id = Column(String(36), primary_key=True)
    actor_subject_id = Column(String(255), nullable=False)
    organization_id = Column(String(36), nullable=True)
    action = Column(String(80), nullable=False)
    resource_type = Column(String(80), nullable=False)
    resource_id = Column(String(255), nullable=False)
    outcome = Column(String(16), nullable=False)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
