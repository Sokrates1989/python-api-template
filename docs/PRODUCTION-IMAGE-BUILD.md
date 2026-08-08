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
`docker push`, Docker Compose build helpers, or the release tool's `publish`
action directly. The failure diagnostic may print a `release_api_image.py
build` command; that command is an explicitly supported local, non-publishing
reproduction of the same proof gates. Do not publish API images from GitHub
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

The selected app, shared image inputs, and release machinery must be committed.
Uncommitted files below another app's `app/apps/<sibling_app>/` directory—and
other files unrelated to the selected image or release mechanism—do not block
the release. When such work exists, the publisher automatically creates a
temporary detached build context at the exact recorded Git revision. This
prevents Docker's repository-level build context from copying unrelated changes
into the selected app image. Selected-app files and shared runtime, migration,
Docker, or release-tool files remain blocking because silently omitting those
changes would publish or validate source different from the intended release.

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
3. runs an app-owned production startup import with deliberately non-default,
   coherent public identity when the selected app declares that fixture;
4. runs the remaining applicable test and health gates;
5. creates dependency and full-image SPDX evidence;
6. applies the fixable HIGH/CRITICAL vulnerability policy; and
7. writes a sanitized local receipt.

It does not change Git history, push source, push an image, update `latest`, or
deploy anything.

### Vulnerability rejection diagnostics

The vulnerability gate does not collapse every nonzero scanner result into a
generic failure. A rejection identifies:

- the scanner and exact image;
- whether fixable HIGH/CRITICAL findings were present or the scanner failed
  operationally (for example, registry authentication or database failure);
- each blocking CVE/rule, affected package, installed version, and available
  fixed version when the scanner supplies them;
- the complete ignored machine report at
  `build/release-evidence/api/<app_id>/<version>.vulnerabilities.json`;
- an interactive scanner command that prints findings, plus the exact
  machine-report gate command; and
- a copy-paste `release_api_image.py build` command that repeats the complete
  local proof without a registry push.

The terminal shows up to 30 findings so a large report remains readable. The
retained JSON report is complete. The gate remains fail-closed: a malformed or
missing report is reported as a scanner operational error, never as a clean
image. Fix the findings or scanner failure and rerun the menu action; do not
disable the policy to make publication continue.

### 3. Publish through the menu

Choose **Build & Push API Docker Image (current or bump + version + latest)**.

The publisher offers the exact committed version plus patch, minor, major, and
manual greater-version choices. **Keep current** intentionally allows the
selected semantic-version tag to be published for the first time or replaced.
The resulting registry digest, rather than the movable tag alone, is the
immutable deployment evidence.

Apps may opt into cross-repository coordination through
`[tool.fe_wi.release_stack]` in their own `pyproject.toml`. The matching Swarm
site profile is the single authority for the minimum version of the next
release. The menu discovers it from the standard sibling workspace, or through
`RELEASE_STACK_PROFILE_PATH` / `RELEASE_STACK_DEPLOYMENT_ROOT` overrides. An
equal candidate continues silently. A lower candidate defaults upward to the
minimum. A higher candidate offers to advance the deployment profile during
the already confirmed publication action. This mechanism is app-neutral.

Press Enter at the default-yes confirmation to continue, or enter `n` to
cancel. The menu then performs one ordered release:

1. reconciles an enrolled candidate with the deployment-owned next-release
   minimum and advances that profile only when required;
2. keeps the current manifest unchanged or updates it to the chosen increment;
3. creates a version-bump commit containing only the selected app manifest for
   an incremented version, even when sibling-app files are already staged;
4. rebuilds and repeats all image proof gates against the exact selected HEAD;
5. pushes or replaces the selected semantic-version image tag;
6. records the registry-reported digest; and
7. pushes `latest` as a convenience tag.

Docker build and push output is streamed while the commands run. If a registry
push fails, the menu offers an interactive Docker login and one retry; pressing
Enter accepts that retry. Docker credentials remain owned by the Docker CLI.

The operation does not push Git source and never deploys the image. Push the
prepared source commit separately when ready. `latest` is never valid
deployment evidence; Swarm must use the semantic version and resolved registry
digest.

If any proof, image push, or digest extraction fails, the publisher exits
nonzero and does not report a completed publication.

## Version coordination and deployment hand-off

The Swarm site profile's compatibility field `release.versionFloor` stores the
minimum version for the next release. It is not a desired deployed version and
does not imply that every existing API, Web, Android, or iOS artifact already
has that version. Source repositories do not maintain another copy.

After publication, choose the real published image tag in the Swarm image
update menu. The deployment profile's `image.defaultVersion` is the deployment
default and is deliberately separate from the next-release minimum. Never
substitute `latest`.

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
- the retained vulnerability-report path, format, and checksum;
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
