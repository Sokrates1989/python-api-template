# PostgreSQL Web Push Dependency Profile

## Purpose

This PDM project extends the standard Template V2 PostgreSQL backend dependency
set with the bounded `pywebpush` transport used by the authenticated Web Push
recipe. The pair composer selects it only when that recipe is enabled.

## Ownership

The Python API template owns `pyproject.toml` and its generated `pdm.lock`.
The networked-recipe catalog pins this directory and the one additional direct
dependency. Ordinary Connected and hybrid-sync output continue using the
standard PostgreSQL lock and therefore do not receive Web Push transport code.

## Safe editing

Change dependency declarations intentionally, regenerate the lock with Python
3.13 and PDM, and update both repositories' catalog compatibility tests in the
same slice. Do not add provider credentials, VAPID keys, endpoints, subjects,
or machine-specific indexes. Never hand-edit `pdm.lock`.
