"""Persistence model for authenticated Booking Service user preferences.

Preferences are application data keyed by the immutable identity-provider
subject. Keycloak remains responsible only for authentication and identity.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from models.sql.base import Base


class BookingUserPreferences(Base):
    """Store revisioned account presentation preferences.

    Attributes:
        subject_id: Immutable verified identity-provider subject.
        preferred_locale: Generated client locale selected by the account.
        revision: Monotonic optimistic-concurrency revision.
        created_at: Database-owned creation timestamp.
        updated_at: Database-owned latest mutation timestamp.
    """

    __tablename__ = "booking_user_preferences"
    __table_args__ = (
        CheckConstraint(
            "preferred_locale IN ('de', 'en')",
            name="ck_booking_user_preferences_locale",
        ),
    )

    subject_id = Column(
        String(255),
        ForeignKey("booking_subjects.subject_id", ondelete="CASCADE"),
        primary_key=True,
    )
    preferred_locale = Column(String(16), nullable=False, default="de")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
