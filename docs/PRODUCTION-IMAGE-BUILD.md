# Production API image release and test publication

This document defines the authoritative operator workflow for planning,
building, and publishing selected-app API images.

## Operator policy

All API image actions must be started from this repository's interactive
quick-start menu.

- Use **Validate API Docker image release plan** to inspect the selected app,
  version, image reference, source revision, and evidence paths.
- Use **Build API Docker image locally (no push)** to run the complete local
  build, runtime inspection, SBOM, and vulnerability gates without publishing.
- Press **`p` Production Release API Image** for `<version>` plus `latest`.
- Press **`t` Production-Connected Test API Image** for `<version>-test` plus
  `latest-test` without changing the source package version.

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

### 3. Publish through a direct-intent menu action

Press **`p` Production Release API Image** or **`t` Production-Connected Test
API Image**. These keys select the publication channel directly; no later
stable/test question appears.

The publisher first resolves the deployment-owned **API component minimum**.
Guided choices mean: keep that minimum, minimum plus patch, minimum plus minor,
or minimum plus major. They never start from an older package or test tag, and
another component's publication cannot force an artificial API patch bump.
Exact image input may intentionally be lower as an image-only override; that
choice changes neither source nor the minimum. An exact value equal to or above
the minimum follows the normal channel behavior. The resulting registry
digest, rather than the movable tag alone, is the immutable deployment
evidence.

Apps may opt into cross-repository coordination through
`[tool.fe_wi.release_stack]` in their own `pyproject.toml`. The matching Swarm
site profile is the single authority for component minimums. The menu discovers
it from the standard sibling workspace, or through
`RELEASE_STACK_PROFILE_PATH` / `RELEASE_STACK_DEPLOYMENT_ROOT` overrides. Both
stable and test publication validate the API minimum. An equal candidate
continues without rewriting it, and a higher candidate advances only the API
entry during the confirmed action. Legacy profiles without component overrides
continue using their shared compatibility floor.

Press Enter at the default-yes confirmation to continue, or enter `n` to
cancel. The menu then performs one ordered release:

1. reconciles an enrolled candidate with the deployment-owned API minimum and
   advances that component only when required;
2. for stable publication only, keeps the current manifest unchanged or
   updates it to the chosen non-override version;
3. for a stable increment, creates a version-bump commit containing only the
   selected app manifest, even when sibling-app files are already staged;
4. rebuilds and repeats all image proof gates against the exact selected HEAD;
5. pushes or replaces the selected semantic-version image tag;
6. records the registry-reported digest; and
7. pushes `latest` for stable publication or `latest-test` for test
   publication as a convenience tag.

Docker build and push output is streamed while the commands run. If a registry
push fails, the menu offers an interactive Docker login and one retry; pressing
Enter accepts that retry. Docker credentials remain owned by the Docker CLI.

The operation does not push Git source and never deploys the image. Push any
prepared stable source commit separately when ready. Neither convenience alias
is valid deployment evidence; Swarm must use the exact versioned tag and
resolved registry digest.

If any proof, image push, or digest extraction fails, the publisher exits
nonzero and does not report a completed publication.

## Version coordination and deployment hand-off

The Swarm site profile's `release.componentVersionFloors.api` value stores the
API minimum. `release.versionFloor` remains the compatibility fallback when an
API override is absent. Neither is a desired deployed version or an assertion
about existing Web, Android, iOS, or legacy WebApp artifacts. Stable and
`-test` API selectors share the API line; source repositories do not maintain
another copy.

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
- `latest` or `latest-test` publication as convenience only; and
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
