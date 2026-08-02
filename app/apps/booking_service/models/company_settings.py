"""Persistence models for tenant-owned company settings and locations.

Every row carries an explicit organization identifier. Locations use a
composite organization/identifier uniqueness boundary so later service and
appointment foreign keys can preserve tenant ownership at the database layer.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from models.sql.base import Base


class BookingCompanySettings(Base):
    """Store one mutable company profile and booking policy per tenant."""

    __tablename__ = "booking_company_settings"
    __table_args__ = (
        CheckConstraint(
            "booking_horizon_days BETWEEN 1 AND 730",
            name="ck_booking_company_horizon",
        ),
        CheckConstraint(
            "minimum_notice_minutes BETWEEN 0 AND 43200",
            name="ck_booking_company_minimum_notice",
        ),
        CheckConstraint(
            "cancellation_notice_minutes BETWEEN 0 AND 43200",
            name="ck_booking_company_cancellation_notice",
        ),
        CheckConstraint(
            "reschedule_notice_minutes BETWEEN 0 AND 43200",
            name="ck_booking_company_reschedule_notice",
        ),
        CheckConstraint(
            "worker_selection_mode IN "
            "('next_available_only', 'specific_worker_only', "
            "'next_available_or_specific')",
            name="ck_booking_company_worker_selection",
        ),
    )

    organization_id = Column(
        String(36),
        ForeignKey("booking_organizations.id"),
        primary_key=True,
    )
    public_name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    contact_email = Column(String(254), nullable=True)
    contact_phone = Column(String(40), nullable=True)
    website_url = Column(String(500), nullable=True)
    default_timezone = Column(String(64), nullable=False)
    default_locale = Column(String(16), nullable=False)
    currency = Column(String(3), nullable=False)
    booking_horizon_days = Column(Integer, nullable=False, default=90)
    minimum_notice_minutes = Column(Integer, nullable=False, default=120)
    cancellation_notice_minutes = Column(Integer, nullable=False, default=1440)
    reschedule_notice_minutes = Column(Integer, nullable=False, default=1440)
    worker_selection_mode = Column(String(40), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BookingLocation(Base):
    """Store one reversible tenant-scoped place where services are offered."""

    __tablename__ = "booking_locations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_booking_location_status",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_booking_location_org_id",
        ),
        Index(
            "ix_booking_location_org_status_name",
            "organization_id",
            "status",
            "display_name",
        ),
    )

    id = Column(String(36), primary_key=True)
    organization_id = Column(
        String(36),
        ForeignKey("booking_organizations.id"),
        nullable=False,
    )
    display_name = Column(String(160), nullable=False)
    timezone = Column(String(64), nullable=False)
    address_line_1 = Column(String(200), nullable=True)
    address_line_2 = Column(String(200), nullable=True)
    postal_code = Column(String(32), nullable=True)
    locality = Column(String(120), nullable=True)
    region = Column(String(120), nullable=True)
    country_code = Column(String(2), nullable=True)
    contact_email = Column(String(254), nullable=True)
    contact_phone = Column(String(40), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
