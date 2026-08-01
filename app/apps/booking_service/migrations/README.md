# Booking Service migrations

This directory owns only the selected app's Alembic revisions. The first
product revision is `booking_service_001_tenancy`; it has no predecessor and
creates subjects, platform access, organizations, memberships, tenant-bound
membership roles, and immutable audit events. The composite membership-role
foreign key prevents roles from being attached across organization scope.

`booking_service_002_membership_identity_outbox` adds the durable BKG-103
client-role delivery intent. Its composite foreign key binds every item to the
same organization and membership, while `membership_revision` makes the newest
command deterministic and prevents a stale provider response from activating a
newer membership state. Payloads contain only an opaque subject ID, allowlisted
role names, delivery state, attempt count, and a sanitized error code.

Run revisions through the repository's selected-app migration command and
never share them with another app profile. Review destructive downgrades before
use: the BKG-103 downgrade removes pending identity-role delivery evidence, and
the BKG-101 downgrade removes tenancy and audit history in reverse dependency
order. Future booking tables must reference the organization and preserve the
explicit scoped-repository boundary.
