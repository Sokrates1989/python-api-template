# Template V2 records starter contract

`records_starter_contract.json` is the Python repository's canonical,
content-free B3 source contract. It pins the starter revision, the only
standard provider pair (`keycloak` plus `postgresql`), the public `/records`
route root, and every renderable source template by a line-ending-independent
SHA-256 digest.

The Flutter pair orchestrator may validate and substitute the declared
placeholders, but it must not carry a competing backend implementation. The
generated app identifier supplies the Python import root, table name, index
name, and Alembic revision. Credentials and environment values are never
template substitutions.

Safe edits require updating the changed template digest, the validator tests,
and both repositories' supported starter revision in one coordinated change.
Output paths must remain app-relative and must never introduce `/api/` routes.
