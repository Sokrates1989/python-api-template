# Felix API release contract

## Purpose and ownership

`felix_api_contract.v2.json` is the API repository's public, secret-free export
for cross-repository release orchestration. It fixes the selected build and
runtime app IDs and production provider while expressing operator-selected
Keycloak identity through required fields, safety constraints, and relational
rules instead of one realm/domain/client tuple.

The API repository owns these requirements. Deployment defaults belong to the
Swarm site profile; Flutter/WebApp release profiles must use the same selected
public identity but do not modify this API contract.

## Structure

- `schemaVersion`, `owner`, and `appId` identify the contract.
- `fixedRuntimeIdentity` keeps the image bound to Felix, PostgreSQL, Keycloak,
  and explicit production mode.
- `keycloak.requiredFields` lists every public or file-path setting needed at
  startup.
- `keycloak.constraints` rejects unsafe URLs and identifiers while retaining
  strict audience enforcement and the mounted-secret boundary.
- `keycloak.relationships` derives issuer and JWKS endpoints from the selected
  server/realm and separates public frontend identity from backend access.
- `cors` accepts one or more exact public HTTPS origins without freezing a
  Felix hostname into the image.
- `routePrefixes` lists service-owned routes and must never use `/api/`.
- `publicFieldMap` names non-secret runtime settings.
- `requiredSecretFileFields` names mounted secret-file settings without
  containing secret values.

## Safe editing

Keep the file strict JSON. Do not add environment dumps, tokens, passwords,
client secrets, database URLs containing credentials, private keys, or user
records. Update the API fixture and its tests whenever this schema changes.

Run the focused test with:

```powershell
python -m unittest tests.test_release_orchestration_contract
```
