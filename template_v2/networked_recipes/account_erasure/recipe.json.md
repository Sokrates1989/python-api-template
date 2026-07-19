# Account Erasure Source Manifest

## Purpose

`recipe.json` pins every generated source file for the Template V2
`account_erasure` backend recipe. The Flutter composer validates this manifest
and every LF-normalized template checksum before generation.

## Ownership and structure

The Python API template owns the adjacent three-template source tree: the
authenticated `/me` route, strict response schemas, and the product-neutral
orchestration service. The service deletes every generated app table carrying
the canonical `owner_subject` column before deleting the external Keycloak
identity. It fails preflight when an app-owned table is not covered.

## Security and retry boundary

The caller cannot submit a subject. Provider support and confidential-client
configuration are validated before product mutation. Keycloak `404` is treated
as idempotent success; an identity failure after product deletion carries only
a boolean partial-completion marker so the still-valid bearer session can retry.

## Safe editing

Change templates first, recalculate their normalized UTF-8 checksums, then
update `recipe.json` and both repositories' catalog compatibility pins in the
same coordinated slice. Never put a subject, table inventory, credential,
provider URL, row count, or customer schema in this manifest.
