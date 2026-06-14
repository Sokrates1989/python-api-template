# Secure Messaging API

Internal-only notification API for Docker Swarm services.

## Purpose

The secure messaging app provides an internal API that allows other Docker Swarm services to send notifications via Telegram and email. It includes:

- Bearer token authentication per calling service
- Content redaction for sensitive data
- Per-app rate limiting (in-memory, per-replica)
- Support for Telegram Bot API and SMTP email

## Architecture

```
Other Swarm services
  -> internal Docker overlay network
  -> POST http://secure_messaging_api:8080/v1/notify
  -> Authorization: Bearer <client-specific-token>
  -> secure_messaging sends Telegram/email
```

**Important**: This API is designed to be internal-only. No public routes, Traefik labels, or published ports.

## Endpoint

### POST /v1/notify

Send a notification to configured providers.

**Headers:**
- `Authorization: Bearer <token>` (required)
- `Content-Type: application/json`

**Request Body:**
```json
{
  "app": "wikijs-backup",
  "level": "error",
  "title": "Wiki.js backup failed",
  "message": "Postgres dump failed on strato.",
  "tags": ["backup", "wikijs", "postgres"],
  "provider": "all",
  "sender": "bot-alerts",
  "to": "override@recipient.com"
}
```

**Supported Levels:**
- `info`, `success`, `warning`, `error`, `critical`

**Supported Providers:**
- `telegram` - Send only to Telegram
- `email` - Send only via email
- `all` - Send to all enabled providers

**Optional Fields:**
- `sender` - Name of configured sender to use (uses first available if not specified)
- `to` - Override recipient (email address or chat ID)

**Response (200 OK):**
```json
{
  "status": "sent",
  "providers": {
    "telegram": {"status": "sent"},
    "email": {"status": "sent"}
  }
}
```

**Response (207 Multi-Status - partial failure):**
```json
{
  "status": "partial_failure",
  "providers": {
    "telegram": {"status": "sent"},
    "email": {"status": "failed", "error": "SMTP connection failed"}
  }
}
```

**Error Responses:**
- `400` - Disabled provider requested, invalid sender, or invalid input
- `401` - Missing or malformed Authorization header
- `403` - Invalid authentication token
- `429` - Rate limit exceeded
- `502` - All selected providers failed
- `503` - Service configuration unavailable

## Authentication

A single bearer token protects the API. Any request with `Authorization: Bearer <token>` is authenticated.

```bash
SECURE_MESSAGING_AUTH_TOKEN=your-secret-token-here
```

The `app` field in request bodies is for **identification only** (appears in logs and notifications), not authentication.

## Environment Variables

### Core Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `APP_PROFILE` | - | Must be `secure_messaging` |
| `BACKEND_APP_ID` | - | Must be `secure_messaging` |
| `DB_TYPE` | - | Must be `none` |
| `PORT` | 8080 | API port |

### Authentication & Rate Limiting
| Variable | Default | Description |
|----------|---------|-------------|
| `SECURE_MESSAGING_AUTH_TOKEN` | - | Single bearer token for API auth |
| `SECURE_MESSAGING_RATE_LIMIT_PER_MINUTE` | `30` | Requests per minute per app |

### Telegram Settings (Split Configuration)
Security best practice: separate metadata from secrets.

| Variable | File Variant | Type | Description |
|----------|--------------|------|-------------|
| `SECURE_MESSAGING_TELEGRAM_SENDERS_JSON` | `_FILE` | Metadata | Sender names and chat IDs |
| `SECURE_MESSAGING_TELEGRAM_SENDER_TOKENS_JSON` | `_FILE` | Secrets | Bot tokens by sender name |

**Telegram Metadata (Safe):**
```json
{"bot-main": {"info": "-100123456", "warning": "-100123456", "error": "-100789012"}}
```
Keys can be: `info`, `warning`, `error`, or any custom name. The `level` field in the request selects the target automatically. Use `default` for a fallback target if level not found.

**Telegram Secrets (Protected):**
```json
{"bot-main": "bot-token-1", "bot-alerts": "bot-token-2"}
```

### Email Settings (Split Configuration)

| Variable | File Variant | Type | Description |
|----------|--------------|------|-------------|
| `SECURE_MESSAGING_EMAIL_SENDERS_JSON` | `_FILE` | Metadata | Host, port, username, from, default_to |
| `SECURE_MESSAGING_EMAIL_SENDER_PASSWORDS_JSON` | `_FILE` | Secrets | SMTP passwords by sender name |

**Email Metadata (Safe):**
```json
{"gmail-primary": {"host": "smtp.gmail.com", "port": "587", "username": "user@gmail.com", "from": "user@gmail.com", "info": "info@example.com", "warning": "alerts@example.com", "error": "oncall@example.com"}}
```
Keys can be: `info`, `warning`, `error`, or any custom name. Use `default_to` for a fallback target if level not found.

**Email Secrets (Protected):**
```json
{"gmail-primary": "app-password-1", "strato-backup": "app-password-2"}
```

**Note:** `*_FILE` variables take precedence over direct values. Use for Docker secrets.

## Local Development

### Using Local Environment File (Recommended)

The secure_messaging app includes a `local.env` template with all configuration options documented.

```bash
# 1. Copy the template to your user-specific file (gitignored)
cd app/apps/secure_messaging
copy local.env local.env.user

# 2. Edit local.env.user with your tokens and settings
#    - Change the dev tokens to secure random values
#    - Enable/disable providers as needed
#    - Add your Telegram/email credentials if testing providers

# 3. Source the file and run
cd ../../../app  # Back to app/ directory
# On Windows PowerShell:
Get-Content apps/secure_messaging/local.env.user | ForEach-Object { if ($_ -match '^([^#][^=]*)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
pdm run uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# On Git Bash/WSL:
# set -a && source apps/secure_messaging/local.env.user && set +a
# pdm run uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

**Note:** `local.env.user` is gitignored and will NOT be committed. Never commit files containing secrets.

### Direct Python Run (Without Env File)

```bash
cd app
export APP_PROFILE=secure_messaging
export DB_TYPE=none
export PORT=8080
export SECURE_MESSAGING_AUTH_TOKEN='dev-token-change-me'
export SECURE_MESSAGING_TELEGRAM_SENDERS_JSON='{}'
export SECURE_MESSAGING_EMAIL_SENDERS_JSON='{}'
pdm run uvicorn main:app --host 0.0.0.0 --port 8080
```

### Test Request

```bash
curl -X POST "http://localhost:8080/v1/notify" \
  -H "Authorization: Bearer dev-token-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "app": "test-app",
    "level": "info",
    "title": "Test notification",
    "message": "This is a test message.",
    "tags": ["test"],
    "provider": "all"
  }'
```

## Redaction Behavior

Sensitive patterns are automatically redacted before logging and sending:

- `password`, `passwd`, `pwd`
- `token`, `secret`, `api_key`
- `authorization`, `cookie`, `set-cookie`
- `private_key`, `client_secret`

Patterns like `key=value`, `key: value`, and JSON `"key": "value"` are replaced with `***REDACTED***`.

## Rate Limiting

- Default: 30 requests per app per minute
- In-memory, per-process/per-replica
- Production should use `replicas: 1` until Redis-backed limiter is added

## Consuming Service Example

Docker Compose snippet for a service using secure messaging:

```yaml
services:
  my_backup_service:
    image: my-backup-image
    networks:
      - secure_messaging_internal
    secrets:
      - secure_messaging_auth_token
    environment:
      SECURE_MESSAGING_API_URL: http://secure_messaging_api:8080
      SECURE_MESSAGING_TOKEN_FILE: /run/secrets/secure_messaging_auth_token

networks:
  secure_messaging_internal:
    external: true

secrets:
  secure_messaging_auth_token:
    external: true
```

Example call from within the service:

```bash
TOKEN="$(cat /run/secrets/secure_messaging_auth_token)"
curl -X POST "$SECURE_MESSAGING_API_URL/v1/notify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "app": "my-backup-service",
    "level": "success",
    "title": "Backup completed",
    "message": "The backup finished successfully.",
    "tags": ["backup"],
    "provider": "all"
  }'
```

## Troubleshooting

### 503 Configuration Error
- Check that allowed client tokens JSON is valid
- Verify all required file paths exist when using `*_FILE` variables

### 429 Rate Limited
- Reduce request frequency
- Increase `SECURE_MESSAGING_RATE_LIMIT_PER_MINUTE`
- Consider if multiple replicas are causing per-replica limit issues

### Provider Failures
- Check provider credentials are configured correctly
- Verify network connectivity from container
- Review logs for sanitized error messages
