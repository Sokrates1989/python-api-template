# Booking Service Backend Profile

## Purpose

This selected app package owns the authenticated PostgreSQL backend for
`booking_service`. BKG-100 introduced the authenticated coarse identity;
BKG-101 added tenant ownership, BKG-103 added scoped membership administration,
and BKG-200 adds tenant-owned company profiles, booking-policy defaults, and
one-or-more reversible locations. BKG-201 adds the first versioned service
catalog, and BKG-202 adds explicit worker profiles, locations, service
qualifications, and service-owned worker-selection policy. Booking,
availability, payments, and
notification delivery remain later focused slices.

## Ownership

Template V2 owns every file listed in `.template_v2/ownership.json`. The
adjacent public-runtime manifest is derived from the same connected/auth recipe
plans as Flutter output. `.template_v2/backend_foundation.json` records the
exact validated Python contract revision and canonical source digest used for
composition. Detached neutral starter files remain recorded in the ownership
manifest as lifecycle history, but they are not part of the product target.
Runtime credentials, database URLs, provider secrets, and CORS policy remain
deployment-owned.

## Product boundary

The selected definition keeps database, Redis, and app-owned migration
requirements enabled while publishing no shared routes. The BKG-100 principal
accepts only verified Keycloak access tokens, requires a non-empty `sub`, and
reads the four independent roles exclusively from
`resource_access[KEYCLOAK_CLIENT_ID].roles`. Realm-only, unknown, malformed,
or unconfigured roles grant nothing. The response contains only `subject_id`
and deterministic `roles`; it never returns raw claims or provider secrets.

`GET /v1/me/context` creates only the app-owned subject primitive and returns
active memberships whose PostgreSQL roles intersect the verified coarse roles.
The client-provided organization selection is never an authorization input.
Member reads require an explicit organization predicate, hide absent/foreign
scope as `404`, and reject known suspended scope as `403`.

Platform organization list/create/suspend/reactivate operations require both
the `platform_admin` coarse role and active `booking_platform_access`. Lifecycle
updates lock the organization, require an expected revision, preserve history,
and write a sanitized audit event in the same transaction. Revision conflicts
return retryable `409`. All routes are rooted at `/v1`; `/api` is forbidden.

Membership list/invite/update/retry operations share
`/v1/organizations/{organization_id}/memberships`. Platform administrators
require both platform gates and may manage all three organization roles.
Organization administrators require an active same-tenant membership and may
manage only `worker` and `customer`; they cannot manage another administrator
or platform access. The final active organization administrator cannot be
removed, suspended, or stripped of that role.

Invitations accept only an immutable provider subject ID and app-owned roles.
They commit the invitation, audit event, and opaque role-sync outbox before
Keycloak delivery. Failure leaves visible `pending`, `failed`, or `cancelled`
recovery state without storing passwords, tokens, email, username, or provider
payloads. Database role removal is immediate and authoritative. The adapter
grants only newly required client roles; it does not remove a coarse Keycloak
role that another organization may still require.

Company settings are read beneath
`/v1/organizations/{organization_id}/company-settings` by active compatible
members and replaced only by an active same-tenant organization administrator.
The complete replacement carries an expected revision and validates its IANA
timezone, generated-client locale, initial currency, booking horizon, notice
windows, and worker-selection policy. Payment configuration is explicitly
`not_configured`; BKG-200 accepts no provider or payment credential.

Location create/update/archive/reactivate operations remain beneath the same
organization boundary. Every lookup includes both organization and location
identifiers. Archive is a revision-checked lifecycle transition rather than a
physical delete, so current and future historical references remain intact;
the final active location cannot be archived. Every successful settings or
location mutation writes a sanitized audit event in the same transaction.
Ordinary members read active places only, while same-tenant administrators also
receive archived places required for explicit reactivation.

Service offerings live below
`/v1/organizations/{organization_id}/services`. Each offering owns normalized
name, description and category text; duration, setup and cleanup buffers; a
five-minute-aligned slot step; integer minor-unit price and ISO currency; an
explicit set of active same-tenant locations; and a published flag. The
offering currency must match the organization profile. Organization
administrators create, replace, archive, and reactivate offerings using an
expected revision. Ordinary active members see only active published entries;
administrators retain the unpublished and archived recovery view. Archive
always unpublishes, and reactivation deliberately remains unpublished until an
administrator reviews and republishes the offering. No catalog route grants
public customer discovery; that boundary belongs to BKG-203.

Worker profiles live below
`/v1/organizations/{organization_id}/workers`. Only active or invited
same-tenant memberships carrying the app-owned `worker` role may receive a
profile. Locations and service qualifications are always explicit: creating a
location never assigns a worker, and removing an assignment never deletes the
retained worker or service. Each qualification separately controls automatic
eligibility and deterministic priority. Public presentation is optional and
independent from automatic eligibility, so hiding a worker from individual
selection does not silently remove that worker from next-available searches.

Organization administrators manage the full workforce with optimistic
revisions and reversible activation. Workers may read only the profile tied to
their own active membership. Company policy may disable individual selection,
while each service owns its authoritative `auto_only`, `specific_only`, or
`specific_or_auto` mode after initialization. A mutation is rejected with a
dependent-service conflict when it would leave a published `specific_only`
service without a selectable worker. Archived services and inactive workers
remain retained for future appointment-history references.

Every later route must belong to an approved booking slice and must never use
a redundant `/api/` prefix. Production role delivery requires a dedicated
confidential client configured by the deployment with
`KEYCLOAK_ADMIN_CLIENT_ID` and a mounted
`KEYCLOAK_ADMIN_CLIENT_SECRET_FILE`. That client receives only the Keycloak
permissions needed to read the target subject/client roles and map roles; it
must not receive unrestricted realm administration. Production realm bootstrap
remains deployment-owned.

## Verification

Run `pdm lock --check --project app/apps/booking_service` and the Python API
template's selected-app contract tests before deployment. Compare the public
runtime example with deployment-owned configuration. Exercise health, auth
configuration, and migration upgrade/downgrade through the BKG-004 quality
entrypoint:

```powershell
python tools/booking_service_quality.py run
```

The command builds the Python 3.13 app image, starts disposable PostgreSQL,
Redis, and Keycloak fixtures, creates matching frontend client roles, verifies
issuer/audience plus four real `/v1/me/identity` projections, seeds two isolated
organizations from the projected non-personal subjects, and proves active
context, explicit multi-membership, dual platform access, foreign-scope `404`,
suspension `403`, reactivation, anonymous `401`, scoped membership denial,
last-admin lockout, provider-failure persistence, worker/customer transition,
explicit compensation, company-policy validation/revision conflicts,
same-tenant location isolation, soft archive, last-location protection, and
reactivation. It also proves catalog normalization, tenant/currency/location
validation, member visibility, administrator-only mutation, optimistic
revision conflicts, safe archive, and unpublished reactivation. Workforce
proofs cover tenant isolation, explicit assignments, worker self-only reads,
automatic versus individual eligibility, dependency conflicts, stale
replacement, and reversible activation. It runs focused contracts and the
route guard, scans logs
for invocation secrets, and removes its containers, network, volume, and
locally built images.
Keep later service routes relative to the API host and free of a redundant
`/api/` prefix.
