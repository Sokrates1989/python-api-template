# Release Checklist

Use this checklist before cutting a release tag for `python-api-template`.

## 1) Code and quality gates

- [ ] `python -m compileall app qa_pytest`
- [ ] Run local release gate (recommended one-command flow):
  - [ ] `.\local-deployment\run-release-gate.ps1 -NoBuild`
- [ ] CI integration matrix validates provider contract endpoints on each profile:
  - [ ] `/health` provider profile
  - [ ] `/database/provider-info`
  - [ ] `/database/lock`
  - [ ] `/database/unlock`
- [ ] `pytest` passes for:
  - [ ] unit tests
  - [ ] provider contract tests
  - [ ] integration matrix (`postgresql`, `neo4j`, `mongodb`)
- [ ] CI pipeline is green for lint/type/test prior to image build/deploy

## 2) Provider startup readiness

- [ ] API startup passes provider probe for active profile
- [ ] `GET /health` returns:
  - [ ] `status=OK`
  - [ ] expected `provider_profile`
  - [ ] `startup_probe_status=success`
- [ ] `GET /database/provider-info` returns expected capabilities

## 3) External backup/restore compatibility

- [ ] Run local provider drill:
  - [ ] `.\local-deployment\run-phase5-drill.ps1 -Profile all`
- [ ] Verify `backup-restore` route preflight rejects mismatched provider targets
- [ ] Verify lock/unlock contract:
  - [ ] `POST /database/lock`
  - [ ] `GET /database/lock-status`
  - [ ] `POST /database/unlock`

## 4) Deployment assets

- [ ] `swarm-backup-restore` env and stack templates include current provider variables
- [ ] `docker compose config` renders successfully for all deployment templates
- [ ] No stale compose/profile drift in local deployment docs

## 5) Security and observability

- [ ] Sensitive request/response body/header logging stays disabled by default
- [ ] Admin/restore keys are sourced from secure env/secrets in deployment pipelines
- [ ] Startup/shutdown and probe diagnostics appear in logs with structured events

## 6) Documentation

- [ ] `docs/IMPROVEMENT_PLAN_PROGRESS.md` updated with release-ready status
- [ ] `docs/SUPPORT_MATRIX.md` reflects officially supported backends
- [ ] `docs/STARTUP_PROBES.md` and `docs/DATABASE_LOCK.md` align with current behavior
