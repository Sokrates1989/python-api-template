# Authenticated Web Push Source Manifest

## Purpose

`recipe.json` pins every generated source file for the Template V2
`authenticated_web_push` backend recipe. The Flutter composer validates the
manifest and each normalized template checksum before generating output.

## Ownership and structure

The Python API template owns the manifest and adjacent `templates/` tree. Each
entry maps one portable template path to its app-relative generated path and
SHA-256 digest. The ordered entries must exactly cover the catalog migration
and service paths.

## Safe editing

Change implementation templates first, recalculate their normalized UTF-8
checksums, then update this manifest and both repositories' catalog pins in one
coordinated slice. Never place VAPID keys, browser endpoints, account subjects,
notification payloads, or deployment-specific values in the manifest.
