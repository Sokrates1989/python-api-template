"""Tenant-bound persistence for workers, locations, and qualifications.

Composite foreign keys repeat the organization identifier so PostgreSQL rejects
cross-tenant membership, location, service, and worker associations.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from models.sql.base import Base


class BookingWorkerProfile(Base):
    """Store one versioned worker profile for an organization membership."""

    __tablename__ = "booking_worker_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            [
                "booking_organization_memberships.organization_id",
                "booking_organization_memberships.id",
            ],
            name="fk_booking_worker_membership_scope",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_booking_worker_status",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_booking_worker_org_id",
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            name="uq_booking_worker_org_membership",
        ),
        Index(
            "ix_booking_worker_org_visibility",
            "organization_id",
            "status",
            "is_publicly_bookable",
            "public_name",
        ),
    )

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), nullable=False)
    membership_id = Column(String(36), nullable=False)
    public_name = Column(String(160), nullable=True)
    public_description = Column(Text, nullable=True)
    is_publicly_bookable = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="active")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BookingWorkerLocationAssignment(Base):
    """Assign one worker explicitly to one same-tenant active location."""

    __tablename__ = "booking_worker_location_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "worker_profile_id"],
            ["booking_worker_profiles.organization_id", "booking_worker_profiles.id"],
            name="fk_booking_worker_location_worker_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["booking_locations.organization_id", "booking_locations.id"],
            name="fk_booking_worker_location_location_scope",
        ),
        Index(
            "ix_booking_worker_location_location",
            "organization_id",
            "location_id",
        ),
    )

    organization_id = Column(String(36), primary_key=True)
    worker_profile_id = Column(String(36), primary_key=True)
    location_id = Column(String(36), primary_key=True)


class BookingWorkerServiceQualification(Base):
    """Qualify one worker for one service with explicit auto participation."""

    __tablename__ = "booking_worker_service_qualifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "worker_profile_id"],
            ["booking_worker_profiles.organization_id", "booking_worker_profiles.id"],
            name="fk_booking_worker_qualification_worker_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "service_offering_id"],
            [
                "booking_service_offerings.organization_id",
                "booking_service_offerings.id",
            ],
            name="fk_booking_worker_qualification_service_scope",
        ),
        CheckConstraint(
            "priority BETWEEN 0 AND 1000",
            name="ck_booking_worker_qualification_priority",
        ),
        Index(
            "ix_booking_worker_qualification_service",
            "organization_id",
            "service_offering_id",
        ),
    )

    organization_id = Column(String(36), primary_key=True)
    worker_profile_id = Column(String(36), primary_key=True)
    service_offering_id = Column(String(36), primary_key=True)
    auto_eligible = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
