# Legacy CI/CD scaffolding

The files in this directory are retained as historical template material.
They are not an authorized production API image release or deployment path.

## Current policy

CI is quality-only. It may run source checks, tests, contract validation, and
release-tool tests. It must not:

- bump an app version;
- commit or push release source;
- build or publish a production API image;
- update an image's `latest` tag;
- deploy Docker Swarm; or
- store credentials that enable those release mutations.

Production API images are planned, proved locally, and published only through
the selected-app actions in `quick-start.ps1` or `quick-start.sh`. See
[`../docs/PRODUCTION-IMAGE-BUILD.md`](../docs/PRODUCTION-IMAGE-BUILD.md).

Swarm configuration, secrets, deployment, health, and rollback are separate
operator actions in the Swarm repository's own `quick-start.sh`.

## Archived files

Subdirectories may still contain build/push or deployment pipeline examples.
They are intentionally non-authoritative and must not be copied into active
GitHub Actions or GitLab CI configuration for Felix.

The active GitHub workflow in `.github/workflows/main.yml` explicitly leaves
image build/push disabled. Any future CI redesign must preserve this
quality-only boundary unless the release policy is deliberately revised and
approved.
