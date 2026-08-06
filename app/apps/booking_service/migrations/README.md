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

`booking_service_003_company_settings` adds one settings row per organization
and tenant-scoped locations with optimistic revisions. It backfills every
existing organization with German-first neutral defaults and one address-free
primary location. The composite organization/location uniqueness boundary is
reserved for later same-tenant catalog and appointment foreign keys. Locations
use active/archive lifecycle state; application operations never hard-delete a
referenced location.

`booking_service_004_service_catalog` adds tenant-owned service offerings and
their explicit location assignments. Composite foreign keys bind every
offering and assignment to one organization, database checks preserve bounded
time/price fields and lifecycle state, and revisions support conflict-safe
complete replacement. Offerings use active/archive lifecycle state and retain
their location relationships for later booking-history references.

`booking_service_005_workforce` adds worker profiles, location assignments,
and service qualifications. `booking_service_006_canonical_company_name`
reconciles pre-fix organization labels with their canonical public names.
`booking_service_007_user_preferences` stores revisioned per-subject locale
preferences in the Booking backend rather than in Keycloak identity data.

Run revisions through the repository's selected-app migration command and
never share them with another app profile. Review destructive downgrades before
use: the BKG-201 downgrade removes service-catalog history, the BKG-103
downgrade removes pending identity-role delivery evidence, the BKG-200
downgrade removes company profile and location history, and the BKG-101
downgrade removes tenancy and audit history. Future booking tables must
reference both organization and owned location where applicable and preserve
the explicit scoped-repository boundary.
