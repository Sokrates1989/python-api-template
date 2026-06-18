# Deprecated – Native PowerShell Runtime Implementations

## Purpose

This directory archives the original native PowerShell runtime scripts that were
replaced during the **Bash-first migration**. They are kept here for reference
only and are **not maintained**.

## Why archived

The repository moved to a Bash-first model where:

- Bash scripts under `setup/modules/*.sh`, `quick-start.sh`, etc. are the
  **source of truth** for all runtime logic.
- PowerShell entry points in the repository root (`quick-start.ps1`,
  `manage-python-project-dependencies.ps1`, `run-docker-build-diagnostics.ps1`)
  are now thin WSL wrappers. They detect a WSL distro, convert the Windows
  repo path, and delegate immediately to the matching Bash script.

## Do not re-introduce

Do not copy logic from these files back into the active PowerShell wrappers.
If behaviour is missing from the Bash scripts, add it to the Bash scripts first.

## Directory structure

```
deprecated/powershell/
  setup/modules/       <- Archived module .ps1 files (docker_helpers, browser_helpers,
                          menu_handlers, version_manager, auth_provider,
                          bootstrap_utils, cognito_setup)
  local-deployment/    <- Archived local-deployment drill / gate / verify scripts
  testing/             <- Archived testing helper scripts
```

## Archive date

Archived as part of the Bash-first migration.
