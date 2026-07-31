# Felix API Release Contract

## Purpose and ownership

`felix_api_contract.v1.json` is the API repository's public, secret-free export
for cross-repository release orchestration. It freezes the selected build and
runtime app IDs, production authentication provider, candidate Keycloak
identity, API-service route prefixes, and names of required environment and
secret-file fields.

The API repository owns these values. The Flutter compatibility checker reads
this file but never updates it.

## Structure

- `schemaVersion`, `owner`, and `appId` identify the contract.
- `appProfile` and `backendAppId` must both select `felix`.
- `candidate` identifies realm `felix` and its isolated public client
  `felix-new-frontend`.
- `routePrefixes` lists service-owned routes and must never use `/api/`.
- `publicFieldMap` names non-secret runtime settings.
- `requiredSecretFileFields` names mounted secret-file settings without
  containing secret values.

## Safe editing

Keep the file strict JSON. Do not add environment dumps, tokens, passwords,
client secrets, database URLs containing credentials, private keys, or user
records. Update the API fixture, its tests, and the Flutter snapshot together
when a public contract field intentionally changes.

Run the focused test with:

```powershell
python -m unittest tests.test_release_orchestration_contract
```
