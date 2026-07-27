# Production API image release

This document defines the authoritative operator workflow for planning,
building, and publishing selected-app API images.

## Operator policy

All API image actions must be started from this repository's interactive
quick-start menu.

- Use **Validate API Docker image release plan** to inspect the selected app,
  version, image reference, source revision, and evidence paths.
- Use **Build API Docker image locally (no push)** to run the complete local
  build, runtime inspection, SBOM, and vulnerability gates without publishing.
- Use **Build & Push API Docker Image (current or bump + version + latest)**
  for the only supported publication path.

Do not publish an API image by running `docker build`, `docker tag`,
`docker push`, Docker Compose build helpers, or
`tools/release_api_image.py` directly. Do not publish API images from GitHub
Actions, GitLab CI/CD, or another automatic pipeline. CI is quality-only.

The terminal is used only to launch the quick-start menu. The menu owns the
release sequence and its safety/evidence gates.

## Start the selected-app menu

Windows PowerShell:

```powershell
cd D:\Development\Code\python\python-api-template
.\quick-start.ps1
```

Linux, macOS, or WSL:

```bash
cd /path/to/python-api-template
./quick-start.sh
```

Before continuing, verify that the menu reports the intended active backend
app. For the Felix candidate release it must be `felix`; stop if another app
is selected.

Menu numbering may evolve, so select actions by their full labels rather than
relying on a fixed number.

## Recommended proof and publication sequence

### 1. Validate the release plan

Choose **Validate API Docker image release plan**.

This action is read-only. Confirm that the output identifies:

- app `felix`;
- image repository `sokrates1989/python-api-felix`;
- the expected current semantic version;
- the expected source and dependency-lock inputs; and
- ignored evidence paths below `build/release-evidence/api/felix/`.

### 2. Prove the current image locally

Choose **Build API Docker image locally (no push)**.

The action builds the selected version and then:

1. verifies the production/Felix OCI identity;
2. verifies the non-root `linux/amd64` runtime contract;
3. runs the applicable test and startup/health gates;
4. creates dependency and full-image SPDX evidence;
5. applies the fixable HIGH/CRITICAL vulnerability policy; and
6. writes a sanitized local receipt.

It does not change Git history, push source, push an image, update `latest`, or
deploy anything.

### 3. Publish through the menu

Choose **Build & Push API Docker Image (current or bump + version + latest)**.

The publisher offers the exact committed version plus patch, minor, major, and
manual greater-version choices. **Keep current** intentionally allows the
selected semantic-version tag to be published for the first time or replaced.
The resulting registry digest, rather than the movable tag alone, is the
immutable deployment evidence.

Press Enter at the default-yes confirmation to continue, or enter `n` to
cancel. The menu then performs one ordered release:

1. keeps the current manifest unchanged or updates it to the chosen increment;
2. creates a version-bump commit only for an incremented version;
3. rebuilds and repeats all image proof gates against the exact selected HEAD;
4. pushes or replaces the selected semantic-version image tag;
5. records the registry-reported digest; and
6. pushes `latest` as a convenience tag.

Docker build and push output is streamed while the commands run. If a registry
push fails, the menu offers an interactive Docker login and one retry; pressing
Enter accepts that retry. Docker credentials remain owned by the Docker CLI.

The operation does not push Git source and never deploys the image. Push the
prepared source commit separately when ready. `latest` is never valid
deployment evidence; Swarm must use the semantic version and resolved registry
digest.

If any proof, image push, or digest extraction fails, the publisher exits
nonzero and does not report a completed publication.

## Version hand-off to Swarm

The version published by the menu must exactly match
`site-configs/felix.json` in the Swarm deployment repository before preflight
or deployment begins.

For example, if the API repository currently contains `0.1.1`, choosing
**Keep current** publishes or replaces `0.1.1` without another version commit.
The Swarm Felix profile must then select `0.1.1`. If the operator instead
chooses the next patch `0.1.2`, the Swarm profile must be committed at `0.1.2`.
Never substitute `latest`.

The registry digest printed by the publication receipt is the value that the
strict Swarm preflight resolves and binds to deployment evidence.

## Evidence

Ignored release evidence is written below:

```text
build/release-evidence/api/<app_id>/
```

For a successful publication, the receipt must report:

- state `published`;
- the selected app and semantic version;
- the exact source revision and dependency-lock checksum;
- the selected version image reference and registry digest;
- successful runtime, SBOM, and vulnerability gates;
- version-tag publication and explicit republishing allowance;
- `latest` publication as convenience only; and
- confirmation that Git source was left local for the operator; and
- deployment authorization as false.

Evidence may contain public identifiers, revisions, checksums, image IDs, and
registry digests. It must never contain registry credentials, application
secrets, `.env` content, or unredacted logs.

## CI/CD boundary

Repository CI may validate source, tests, contracts, and release-tool
behavior. It must not:

- bump the application version;
- commit or push release source;
- build or publish a release image;
- update `latest`; or
- deploy to Docker Swarm.

Files under `ci-cd/` and historical pipeline templates are retained only as
legacy reference material. They are not an authorized Felix image release
path.

## Deployment

After the semantic version is published and the matching Swarm profile is
available on the server, use the Swarm repository's own `./quick-start.sh`.
Select the exact Felix candidate profile and then use
**Felix strict deploy / health / rollback**.

Image publication and Swarm deployment remain two separate, explicit menu
operations in their owning repositories.
