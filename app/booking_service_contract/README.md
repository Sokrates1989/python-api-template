# Booking Service Pair Contract

## Purpose

This package is the Python repository's canonical, secret-free compatibility
contract for the booking reference pair. It exists before the generated
`app/apps/booking_service` target so both repositories can reject incompatible
identity or transport assumptions before either final target is written.

The contract freezes application identity, Android package identity, public
API and Keycloak values, the Keycloak audience, shared multi-tenancy,
Android/web support, relative route rules, organization-context selection,
stable error and idempotency headers, time representations, capability
discovery, OpenAPI identity, and generated-versus-handwritten ownership.

## Ownership

- `pair_contract.json` is the canonical Python-owned machine contract.
- `contract.py` validates the canonical document using only the Python
  standard library and renders the OpenAPI info extension used by the backend.
- `__init__.py` exposes the supported public validation surface.
- `tests/test_booking_service_pair_contract.py` owns Python-side compatibility,
  route, secret-field, and OpenAPI identity evidence.
- The Flutter repository owns an independent validator and a pinned fixture;
  it does not import this Python implementation.

The JSON document cannot contain comments, so this file is its companion
documentation under the global non-commentable-file rule. Public endpoints and
client identifiers are configuration, not credentials. Passwords, client
secrets, bearer values, signing material, private keys, and proof-user data are
forbidden.

## Compatibility And Upgrade Rules

`contract_version` changes only for an incompatible machine schema.
`contract_revision` changes for compatible semantic additions or corrections
that both repositories explicitly adopt. The Flutter pin must be updated in a
separate compatible consumer commit before a newer revision may create or
update final targets. The validator's formatting-independent semantic SHA-256
prevents a document change from retaining the old revision accidentally.

Generated files remain governed by each target's
`.template_v2/ownership.json`. They change only through managed apply. An
owned file must be explicitly detached before handwritten takeover; detached
and unowned paths are preserved. New booking behavior should use the declared
handwritten roots and must not edit generated foundation files casually.

The active organization header is an untrusted selection hint. It never grants
membership or capability; backend authorization resolves the stored resource
tenant and current membership independently. Product routes are relative to
the configured API origin. A normalized route equal to `/api` or beginning
with `/api/` is always invalid.

## Verification

From the Python repository root, run:

```powershell
python tools/validate_booking_service_pair_contract.py
python -m unittest tests.test_booking_service_pair_contract
```

Use Python 3.13 for repository qualification. The validator itself remains
standard-library-only so the Flutter-side cross-repository preflight can read
the contract without installing backend dependencies or contacting a provider.

Rollback is a focused Git revert of this package, its validator entry point,
and tests. The contract creates no database, route, realm, credential, or
external side effect.
