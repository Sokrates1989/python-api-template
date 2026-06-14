# Secure Messaging API Implementation Plan

## 1. Purpose

This document defines the API-side implementation plan for adding an internal-only secure messaging capability to `python-api-template`.

The secure messaging capability will let other Docker Swarm services send notification requests to one central internal API. The API will validate the caller, redact sensitive content, rate-limit requests per calling app, and deliver notifications through configured providers such as Telegram and SMTP email.

The implementation must reuse this repository. It must not create a standalone secure-messaging repository, CLI, CLI image, or client package.

Target internal call shape:

```text
Other Docker Swarm service
  -> internal Docker overlay network
  -> POST http://secure_messaging_api:8080/v1/notify
  -> Authorization: Bearer <client-specific-token>
  -> secure_messaging app profile validates and sends provider messages
```

---

## 2. Current Repository Findings

The current API repository already has a multi-app structure.

Important existing pieces:

```text
app/main.py
app/apps/registry.py
app/apps/contracts.py
app/apps/<app_id>/definition.py
app/apps/<app_id>/config/app_metadata.py
app/apps/<app_id>/routes/
app/apps/<app_id>/schemas/
app/apps/<app_id>/services/
```

The runtime app is selected by `APP_PROFILE`:

```text
settings.get_backend_app_definition()
```

The Docker build app is selected by `BACKEND_APP_ID`:

```text
Dockerfile build arg BACKEND_APP_ID
```

Existing app packages such as `postgres_template`, `mongodb_template`, and `mongo_db_test` provide app-specific `pyproject.toml` and `pdm.lock` files. The Dockerfile requires both files for the selected backend app.

Current startup behavior is database-oriented:

```text
- app/main.py always mounts shared routes.
- app/main.py always initializes Redis client behavior.
- api/config/lifecycle.py always initializes the configured database.
- health payload assumes a selected backend app and database provider.
```

This is not ideal for secure messaging because the service should not require a database just to start and should not expose unrelated shared database/demo routes.

---

## 3. Target API Design

Secure messaging should be implemented as a normal backend app profile:

```text
app/apps/secure_messaging/
```

Runtime identity:

```text
APP_PROFILE=secure_messaging
BACKEND_APP_ID=secure_messaging
DB_TYPE=none
PORT=8080
```

The endpoint must be:

```text
POST /v1/notify
```

Important route rule:

```text
Do not use /api/ as a route prefix.
```

Secure messaging should not be a globally mounted shared route because public API deployments may already be exposed through Traefik. Keeping it as an app profile makes it possible to run the same image as a dedicated internal-only service in Swarm.

---

## 4. Required Core Template Changes

The current app contract should be extended so an app can declare whether it needs shared infrastructure.

Recommended additions to `BackendAppDefinition`:

```python
requires_database: bool = True
requires_redis: bool = True
include_shared_routes: bool = True
```

Existing app definitions keep the default behavior.

The secure messaging definition should set:

```python
requires_database=False
requires_redis=False
include_shared_routes=False
```

This avoids:

```text
- database startup
- provider startup probes
- SQL migrations
- Redis initialization
- /cache/* routes
- unrelated /users, /examples, /database, /files, /packages routes
```

The health endpoint should still exist and should clearly report:

```json
{
  "status": "OK",
  "app_profile": "secure_messaging",
  "backend_app": "Secure Messaging",
  "backend_data_profile": "none",
  "database_type": "none",
  "startup_probe_status": "skipped"
}
```

---

## 5. Files To Add

Add this app package:

```text
app/apps/secure_messaging/__init__.py
app/apps/secure_messaging/definition.py
app/apps/secure_messaging/config/__init__.py
app/apps/secure_messaging/config/app_metadata.py
app/apps/secure_messaging/config/runtime.py
app/apps/secure_messaging/routes/__init__.py
app/apps/secure_messaging/routes/notifications.py
app/apps/secure_messaging/schemas/__init__.py
app/apps/secure_messaging/schemas/notifications.py
app/apps/secure_messaging/services/__init__.py
app/apps/secure_messaging/services/auth.py
app/apps/secure_messaging/services/notification_service.py
app/apps/secure_messaging/services/providers.py
app/apps/secure_messaging/services/telegram_provider.py
app/apps/secure_messaging/services/email_provider.py
app/apps/secure_messaging/services/redaction.py
app/apps/secure_messaging/services/rate_limiter.py
app/apps/secure_messaging/deployment/compose.override.yml
app/apps/secure_messaging/deployment/compose-files.txt
app/apps/secure_messaging/pyproject.toml
app/apps/secure_messaging/pdm.lock
docs/SECURE_MESSAGING.md
```

Add tests:

```text
qa_pytest/unit/test_secure_messaging_auth.py
qa_pytest/unit/test_secure_messaging_redaction.py
qa_pytest/unit/test_secure_messaging_rate_limiter.py
qa_pytest/unit/test_secure_messaging_config.py
qa_pytest/unit/test_secure_messaging_providers.py
qa_pytest/unit/test_secure_messaging_routes.py
qa_pytest/unit/test_secure_messaging_startup_profile.py
```

---

## 6. Files To Change

Change these shared files:

```text
app/apps/contracts.py
app/apps/registry.py
app/main.py
app/api/config/lifecycle.py
app/api/settings.py
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/HOW_TO_ADD_ENDPOINT.md
```

Potentially change local deployment helpers:

```text
local-deployment/docker-compose.yml
local-deployment/base/api.compose.yml
```

Only change local deployment files if secure messaging needs a smoother local Compose entrypoint than the existing app-specific override model provides.

---

## 7. App Metadata And Definition

Create `SecureMessagingAppConfig` in:

```text
app/apps/secure_messaging/config/app_metadata.py
```

Recommended fields:

```python
app_id = "secure_messaging"
display_name = "Secure Messaging"
backend_data_profile = "none"
notify_mount_prefix = ""
notify_public_prefix = "/v1/notify"
exposes_sync_routes = False
```

Create `BACKEND_APP_DEFINITION` in:

```text
app/apps/secure_messaging/definition.py
```

The definition should register `notifications.router` with no external prefix.

---

## 8. Runtime Configuration

Create app-local config in:

```text
app/apps/secure_messaging/config/runtime.py
```

This module should load all secure-messaging settings lazily from environment variables and Docker secret files.

Required environment variables:

```text
SECURE_MESSAGING_ALLOWED_CLIENT_TOKENS_JSON
SECURE_MESSAGING_ALLOWED_CLIENT_TOKENS_FILE
SECURE_MESSAGING_RATE_LIMIT_PER_MINUTE
SECURE_MESSAGING_TELEGRAM_ENABLED
SECURE_MESSAGING_TELEGRAM_BOT_TOKEN
SECURE_MESSAGING_TELEGRAM_BOT_TOKEN_FILE
SECURE_MESSAGING_TELEGRAM_CHAT_ID
SECURE_MESSAGING_TELEGRAM_CHAT_ID_FILE
SECURE_MESSAGING_EMAIL_ENABLED
SECURE_MESSAGING_SMTP_HOST
SECURE_MESSAGING_SMTP_HOST_FILE
SECURE_MESSAGING_SMTP_PORT
SECURE_MESSAGING_SMTP_PORT_FILE
SECURE_MESSAGING_SMTP_USERNAME
SECURE_MESSAGING_SMTP_USERNAME_FILE
SECURE_MESSAGING_SMTP_PASSWORD
SECURE_MESSAGING_SMTP_PASSWORD_FILE
SECURE_MESSAGING_SMTP_USE_TLS
SECURE_MESSAGING_SMTP_USE_TLS_FILE
SECURE_MESSAGING_EMAIL_FROM
SECURE_MESSAGING_EMAIL_FROM_FILE
SECURE_MESSAGING_EMAIL_TO_DEFAULT
SECURE_MESSAGING_EMAIL_TO_DEFAULT_FILE
```

Rules:

```text
- *_FILE values take precedence over direct env vars.
- Missing allowed-token config is a service configuration error.
- Missing provider config only fails when that provider is enabled or requested.
- Never include secret values in raised error messages.
```

Recommended helper:

```python
read_env_or_file(value_name: str, file_name: str) -> str
```

The helper should:

```text
1. If file env var is set and exists, read and strip the file.
2. If file env var is set but missing, raise a sanitized config error.
3. Otherwise return the direct env var value.
4. Return empty string if neither exists.
```

---

## 9. Request And Response Schemas

Create schemas in:

```text
app/apps/secure_messaging/schemas/notifications.py
```

Request:

```json
{
  "app": "wikijs-backup",
  "level": "error",
  "title": "Wiki.js backup failed",
  "message": "Postgres dump failed on strato.",
  "tags": ["backup", "wikijs", "postgres"],
  "provider": "all"
}
```

Supported levels:

```text
info
success
warning
error
critical
```

Supported providers:

```text
telegram
email
all
```

Recommended validation:

```text
- app: 1 to 100 chars, lowercase service identifier recommended.
- title: 1 to 200 chars.
- message: 1 to 4000 chars for v1.
- tags: max 20 tags, each max 50 chars.
- provider: default "all".
```

Successful response:

```json
{
  "status": "sent",
  "providers": {
    "telegram": "sent",
    "email": "sent"
  }
}
```

Partial failure response:

```json
{
  "status": "partial_failure",
  "providers": {
    "telegram": "sent",
    "email": "failed"
  }
}
```

---

## 10. Authentication Plan

Create auth logic in:

```text
app/apps/secure_messaging/services/auth.py
```

Rules:

```text
- Require Authorization header.
- Require Bearer scheme.
- Extract only the bearer token value.
- Load allowed client tokens from JSON.
- JSON maps app names to tokens.
- Submitted request.app must match the token owner.
- Compare tokens with secrets.compare_digest.
- Do not log raw tokens.
- Do not log full Authorization headers.
```

Response behavior:

```text
Missing Authorization header -> 401
Malformed Authorization header -> 401
Invalid token -> 403
Token/app mismatch -> 403
Token config missing or invalid -> 503
```

Allowed token JSON example:

```json
{
  "wikijs-backup": "client-token-for-wikijs-backup",
  "strato-backup": "client-token-for-strato-backup"
}
```

Return an authenticated caller object:

```python
AuthenticatedClient(app="wikijs-backup")
```

The route should compare the authenticated app against the request body app before dispatching providers.

---

## 11. Redaction Plan

Create redaction logic in:

```text
app/apps/secure_messaging/services/redaction.py
```

Sensitive keys and patterns:

```text
password
passwd
pwd
token
secret
api_key
apikey
authorization
cookie
set-cookie
private_key
client_secret
```

Replacement:

```text
***REDACTED***
```

Redaction should handle:

```text
- key=value
- key: value
- "key": "value"
- key=value&other=value
- Authorization: Bearer ...
- Cookie: ...
- Set-Cookie: ...
```

Redaction should run before:

```text
- logging request content
- formatting Telegram messages
- formatting email messages
- returning provider failure details
```

Do not rely only on HTTP middleware body logging flags. Secure messaging should sanitize its own content regardless of debug settings.

---

## 12. Rate Limiting Plan

Create a simple in-memory limiter in:

```text
app/apps/secure_messaging/services/rate_limiter.py
```

Phase 1 behavior:

```text
- Limit by app name.
- Default: 30 requests per app per minute.
- Use monotonic time.
- Keep only timestamps inside the active window.
- Return 429 when exceeded.
```

Config:

```text
SECURE_MESSAGING_RATE_LIMIT_PER_MINUTE=30
```

V1 caveat:

```text
In-memory rate limiting is per process and per replica. Production secure messaging should run with replicas=1 until a Redis-backed or shared limiter is added.
```

Future Phase:

```text
Add Redis-backed limiter if multi-replica secure messaging becomes necessary.
```

---

## 13. Provider Dispatch Plan

Create provider orchestration in:

```text
app/apps/secure_messaging/services/notification_service.py
app/apps/secure_messaging/services/providers.py
```

Provider selection rules:

```text
provider=telegram -> send only Telegram.
provider=email -> send only email.
provider=all -> send to all enabled providers.
```

Disabled provider behavior:

```text
- If explicitly requested provider is disabled, return 400.
- If provider=all and no providers are enabled, return 503.
- If provider=all and one provider is disabled, skip disabled providers only if at least one enabled provider exists.
```

Recommended provider result statuses:

```text
sent
failed
disabled
skipped
```

Recommended HTTP statuses:

```text
200 -> all requested providers sent.
207 -> at least one provider sent and at least one failed.
400 -> requested provider is disabled or unsupported.
429 -> rate limit exceeded.
502 -> all selected providers failed.
503 -> service provider configuration unavailable.
```

Never expose raw provider responses if they could contain secrets.

---

## 14. Telegram Provider Plan

Create:

```text
app/apps/secure_messaging/services/telegram_provider.py
```

Config:

```text
SECURE_MESSAGING_TELEGRAM_ENABLED=true
SECURE_MESSAGING_TELEGRAM_BOT_TOKEN_FILE=/run/secrets/secure_messaging_telegram_bot_token
SECURE_MESSAGING_TELEGRAM_CHAT_ID_FILE=/run/secrets/secure_messaging_telegram_chat_id
```

Implementation:

```text
- Use Telegram Bot API sendMessage.
- Use redacted message content.
- Use a short timeout.
- Return sanitized failure details.
```

Recommended message format:

```text
[ERROR] Wiki.js backup failed

App: wikijs-backup
Level: error
Tags: backup, wikijs, postgres

Postgres dump failed on strato.
```

Dependency choice:

```text
Use httpx for async HTTP if added to secure_messaging pyproject.toml.
If avoiding a new dependency, use requests in asyncio.to_thread.
```

Recommended:

```text
Add httpx to the secure_messaging app dependency manifest.
```

---

## 15. SMTP Email Provider Plan

Create:

```text
app/apps/secure_messaging/services/email_provider.py
```

Config:

```text
SECURE_MESSAGING_EMAIL_ENABLED=true
SECURE_MESSAGING_SMTP_HOST_FILE=/run/secrets/secure_messaging_smtp_host
SECURE_MESSAGING_SMTP_PORT_FILE=/run/secrets/secure_messaging_smtp_port
SECURE_MESSAGING_SMTP_USERNAME_FILE=/run/secrets/secure_messaging_smtp_username
SECURE_MESSAGING_SMTP_PASSWORD_FILE=/run/secrets/secure_messaging_smtp_password
SECURE_MESSAGING_SMTP_USE_TLS_FILE=/run/secrets/secure_messaging_smtp_use_tls
SECURE_MESSAGING_EMAIL_FROM_FILE=/run/secrets/secure_messaging_email_from
SECURE_MESSAGING_EMAIL_TO_DEFAULT_FILE=/run/secrets/secure_messaging_email_to_default
```

Implementation:

```text
- Use Python stdlib smtplib.
- Use EmailMessage.
- Plain text only for v1.
- Use STARTTLS when configured.
- Run blocking SMTP work in asyncio.to_thread.
- Never log SMTP password or server auth failures with secrets.
```

Subject:

```text
[ERROR] wikijs-backup: Wiki.js backup failed
```

Body:

```text
App: wikijs-backup
Level: error
Title: Wiki.js backup failed
Tags: backup, wikijs, postgres

Postgres dump failed on strato.
```

---

## 16. Route Plan

Create route in:

```text
app/apps/secure_messaging/routes/notifications.py
```

Router:

```python
router = APIRouter(tags=["secure-messaging"], prefix="/v1")
```

Endpoint:

```text
POST /v1/notify
```

Route responsibilities:

```text
1. Parse and validate request body through Pydantic.
2. Authenticate bearer token.
3. Enforce token/app match.
4. Apply per-app rate limit.
5. Redact message content.
6. Dispatch selected providers.
7. Return full provider result map.
```

The route should stay thin. Provider and auth logic belongs in service modules.

---

## 17. Dependency Manifest Plan

Create:

```text
app/apps/secure_messaging/pyproject.toml
app/apps/secure_messaging/pdm.lock
```

Recommended dependencies:

```toml
[project]
name = "secure_messaging"
version = "0.1.0"
description = "Internal-only secure messaging backend app."
requires-python = ">=3.13,<3.14"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn>=0.30.1",
    "pydantic-settings>=2.3.4",
    "python-dotenv>=1.0.1",
    "python-multipart>=0.0.20",
    "httpx>=0.27.0"
]
```

Do not include SQL, MongoDB, Neo4j, Alembic, or Redis unless the core runtime still requires them. The whole point of the secure profile is to avoid unnecessary provider dependencies.

If `main.py` keeps importing `redis` at module import time, either:

```text
- keep redis as a dependency, or
- refactor main.py to import redis only when the selected app requires Redis.
```

Recommended:

```text
Refactor main.py so redis is imported lazily only when required.
```

---

## 18. Local Development Plan

Local direct Python run:

```bash
cd D:/Development/Code/python/python-api-template/app
set APP_PROFILE=secure_messaging
set DB_TYPE=none
set PORT=8080
set SECURE_MESSAGING_ALLOWED_CLIENT_TOKENS_JSON={"wikijs-backup":"dev-token"}
set SECURE_MESSAGING_TELEGRAM_ENABLED=false
set SECURE_MESSAGING_EMAIL_ENABLED=false
pdm run uvicorn main:app --host 0.0.0.0 --port 8080
```

Local Docker Compose run should use:

```text
ACTIVE_BACKEND_APP_ID=secure_messaging
APP_PROFILE=secure_messaging
DB_TYPE=none
PORT=8080
```

Create local app override:

```text
app/apps/secure_messaging/deployment/compose.override.yml
```

It should set:

```yaml
services:
  api:
    environment:
      APP_PROFILE: secure_messaging
      BACKEND_APP_ID: secure_messaging
      DB_TYPE: none
    volumes:
      - ../../app/apps/secure_messaging:/app/apps/secure_messaging:ro
```

Test request:

```bash
curl -X POST "http://localhost:8080/v1/notify" ^
  -H "Authorization: Bearer dev-token" ^
  -H "Content-Type: application/json" ^
  -d "{\"app\":\"wikijs-backup\",\"level\":\"success\",\"title\":\"Wiki.js backup completed\",\"message\":\"The backup finished successfully.\",\"tags\":[\"backup\",\"wikijs\"],\"provider\":\"all\"}"
```

For local provider behavior:

```text
- Keep providers disabled for auth/schema/rate-limit tests.
- Use mocked HTTP for Telegram tests.
- Use mocked smtplib for SMTP tests.
- Optionally test real SMTP against a local debug server in a later phase.
```

---

## 19. Testing Plan

Run existing tests before major refactoring:

```bash
pytest
```

Add targeted unit tests.

Authentication:

```text
- missing Authorization returns 401.
- non-Bearer Authorization returns 401.
- invalid token returns 403.
- valid token with wrong app returns 403.
- valid token with matching app succeeds.
- token JSON from file takes precedence over direct JSON.
- invalid JSON returns sanitized config error.
```

Redaction:

```text
- password=abc -> password=***REDACTED***
- token: abc -> token: ***REDACTED***
- "api_key": "abc" -> "api_key": "***REDACTED***"
- Authorization: Bearer abc -> Authorization: ***REDACTED***
- Cookie and Set-Cookie are redacted.
- private_key and client_secret are redacted.
```

Rate limiting:

```text
- under limit succeeds.
- over limit returns 429.
- app A does not consume app B budget.
- old timestamps are purged.
```

Provider orchestration:

```text
- provider=telegram sends only Telegram.
- provider=email sends only email.
- provider=all sends all enabled providers.
- disabled explicit provider returns 400.
- one success and one failure returns partial_failure.
- all failures return failed status and 502.
```

Startup:

```text
- secure_messaging app definition is discovered.
- secure_messaging starts without database init.
- secure_messaging does not mount shared database routes.
- health returns database_type none and probe skipped.
```

---

## 20. Documentation Plan

Create:

```text
docs/SECURE_MESSAGING.md
```

Include:

```text
- Purpose and architecture.
- Internal-only deployment warning.
- Endpoint contract.
- Request and response examples.
- Auth token JSON format.
- Environment variables.
- Docker Swarm secret names.
- Local development instructions.
- Provider configuration.
- Redaction behavior.
- Rate limiting behavior.
- Consuming service curl example.
- Troubleshooting.
```

Update:

```text
docs/ARCHITECTURE.md
docs/PROJECT_STRUCTURE.md
docs/HOW_TO_ADD_ENDPOINT.md
```

Only update these enough to explain app profiles that do not require a database.

---

## 21. Security Requirements

The API implementation must enforce:

```text
- No route prefix /api.
- Bearer token required even on internal network.
- Per-app token ownership.
- Constant-time token comparison.
- No full token logging.
- No Authorization header logging.
- Provider secrets loaded only in secure messaging service.
- Sensitive message content redacted before logging and sending.
- Provider failures sanitized.
- Clear disabled-provider errors.
```

Deployment must enforce internal-only exposure, but API code should still be secure if accidentally reachable.

---

## 22. Phased Implementation

### Phase 1. Core Profile Support

Deliver:

```text
- BackendAppDefinition infrastructure flags.
- main.py conditional shared routes.
- main.py conditional Redis setup.
- lifecycle.py no-database startup path.
- health endpoint support for skipped database probe.
```

Acceptance criteria:

```text
- Existing app profiles behave as before.
- A no-db app profile can start.
- Tests cover both default and no-db profile behavior.
```

### Phase 2. Secure Messaging Minimal API

Deliver:

```text
- secure_messaging app package.
- POST /v1/notify.
- request/response schemas.
- token loading.
- bearer authentication.
- token/app matching.
- redaction.
- in-memory per-app rate limiting.
- provider abstraction with disabled-provider handling.
```

Acceptance criteria:

```text
- Valid local request authenticates.
- Invalid and mismatched tokens are rejected.
- Redaction tests pass.
- Rate-limit tests pass.
- No unrelated routes are mounted.
```

### Phase 3. Provider Implementations

Deliver:

```text
- Telegram provider.
- SMTP provider.
- provider=telegram/email/all behavior.
- partial failure handling.
- sanitized provider errors.
```

Acceptance criteria:

```text
- Mocked Telegram and SMTP tests pass.
- Partial failure response matches contract.
- No secret values appear in errors or logs.
```

### Phase 4. Local Development And Documentation

Deliver:

```text
- local compose override.
- docs/SECURE_MESSAGING.md.
- updated architecture docs.
```

Acceptance criteria:

```text
- Developer can run secure messaging locally without real provider credentials.
- Documentation includes copy-pasteable curl examples.
```

### Phase 5. Deployment Integration Verification

Deliver:

```text
- API image builds with BACKEND_APP_ID=secure_messaging.
- API runs with APP_PROFILE=secure_messaging and DB_TYPE=none.
- Health endpoint works on port 8080.
```

Acceptance criteria:

```text
- Container starts without DB, Redis, or public dependencies.
- /v1/notify works in a local container.
```

---

## 23. API-Level Acceptance Criteria

The API-side work is complete when:

```text
- POST /v1/notify exists.
- No /api/ route prefix is introduced.
- secure_messaging app is discovered by the registry.
- secure_messaging starts with DB_TYPE=none.
- Shared template demo/database routes are not mounted for secure_messaging.
- Missing auth returns 401.
- Invalid token returns 403.
- Token/app mismatch returns 403.
- Valid token and enabled providers return status sent.
- One provider failure returns partial_failure.
- All provider failures return failed.
- Disabled requested provider returns a clear error.
- Redaction covers all required sensitive patterns.
- Rate limiting returns 429 when exceeded.
- Provider credentials are never logged or returned.
- Unit tests cover auth, config, redaction, rate limiting, providers, and startup profile behavior.
- Documentation explains local and Swarm usage.
```

---

## 24. Future Enhancements

Potential later improvements:

```text
- Redis-backed distributed rate limiting.
- Per-app provider permissions.
- Per-app default recipients.
- Per-app severity thresholds.
- Deduplication windows for repeated notifications.
- Optional persistence for redacted delivery audit events.
- Optional provider dry-run mode for staging.
- Optional message templates.
```

Do not implement these in Phase 1 unless they become necessary for production safety.

---

## 25. Implementation Prompt For Codex

```text
Implement secure_messaging inside python-api-template.

Do not create a new repository.
Do not create a CLI.
Do not create a client package.
Do not use /api/ as a route prefix.

Add a new backend app profile:
app/apps/secure_messaging

Add:
POST /v1/notify

Support:
- Bearer token auth.
- JSON app-to-token map.
- _FILE secret loading with file precedence.
- token/app matching.
- levels: info, success, warning, error, critical.
- providers: telegram, email, all.
- Telegram Bot API provider.
- SMTP plain text email provider.
- redaction before logs and provider sends.
- per-app in-memory rate limit, default 30/minute.
- partial provider failure responses.

Refactor the template so secure_messaging can run with:
APP_PROFILE=secure_messaging
BACKEND_APP_ID=secure_messaging
DB_TYPE=none
PORT=8080

The secure_messaging profile must not initialize database, run migrations, initialize Redis, or mount unrelated shared database/demo routes.

Keep existing app profiles working.
Add focused pytest coverage.
Update docs.
```
