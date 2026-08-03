"""Persistence models for tenant-owned timed service offerings.

Composite foreign keys repeat the organization identifier so a service cannot
reference a location belonging to another tenant, even if application checks
regress.
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from models.sql.base import Base


class BookingServiceOffering(Base):
    """Store one versioned timed service owned by an organization."""

    __tablename__ = "booking_service_offerings"
    __table_args__ = (
        CheckConstraint(
            "duration_minutes BETWEEN 5 AND 1440",
            name="ck_booking_service_duration",
        ),
        CheckConstraint(
            "setup_buffer_minutes BETWEEN 0 AND 1440",
            name="ck_booking_service_setup_buffer",
        ),
        CheckConstraint(
            "cleanup_buffer_minutes BETWEEN 0 AND 1440",
            name="ck_booking_service_cleanup_buffer",
        ),
        CheckConstraint(
            "slot_step_minutes BETWEEN 5 AND 60 AND slot_step_minutes % 5 = 0",
            name="ck_booking_service_slot_step",
        ),
        CheckConstraint(
            "price_minor_units BETWEEN 0 AND 1000000000",
            name="ck_booking_service_price",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_booking_service_status",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_booking_service_org_id",
        ),
        Index(
            "ix_booking_service_org_visibility_name",
            "organization_id",
            "status",
            "is_published",
            "name",
        ),
    )

    id = Column(String(36), primary_key=True)
    organization_id = Column(
        String(36),
        ForeignKey("booking_organizations.id"),
        nullable=False,
    )
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(120), nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    setup_buffer_minutes = Column(Integer, nullable=False, default=0)
    cleanup_buffer_minutes = Column(Integer, nullable=False, default=0)
    slot_step_minutes = Column(Integer, nullable=False, default=15)
    price_minor_units = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    is_published = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="active")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BookingServiceLocationOffering(Base):
    """Assign one service explicitly to one same-tenant location."""

    __tablename__ = "booking_service_location_offerings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "service_offering_id"],
            [
                "booking_service_offerings.organization_id",
                "booking_service_offerings.id",
            ],
            name="fk_booking_service_location_service_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["booking_locations.organization_id", "booking_locations.id"],
            name="fk_booking_service_location_location_tenant",
        ),
        Index(
            "ix_booking_service_location_location",
            "organization_id",
            "location_id",
        ),
    )

    organization_id = Column(String(36), primary_key=True)
    service_offering_id = Column(String(36), primary_key=True)
    location_id = Column(String(36), primary_key=True)
