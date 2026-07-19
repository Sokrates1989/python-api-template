# AI Chat Source Manifest

## Purpose

`recipe.json` pins every generated source file for the Template V2 `ai_chat`
backend recipe. The Flutter composer validates the manifest and every
LF-normalized template checksum before generating output.

## Ownership and structure

The Python API template owns the manifest and adjacent `templates/` tree. The
six ordered entries cover the migration, minimized exchange model,
owner-filtered repository, authenticated route, bounded schemas, and
provider-neutral orchestration service declared by the B4 catalog.

## Privacy and policy boundary

Generated persistence stores only app-owned opaque identifiers plus visible
user and assistant messages. Consent proofs, context hints, prompts, provider
and model information, credentials, bearer tokens, diagnostics, and raw errors
must never be added to the generated history table. Non-empty context remains
rejected until an app injects a reviewed minimization policy; quota decisions
remain an app-owned injectable seam.

## Safe editing

Change templates first, recalculate their normalized UTF-8 checksums, then
update this manifest and both repositories' catalog pins in one coordinated
slice. Never place prompts, provider credentials, user content, owner subjects,
or deployment-specific values in the manifest.
