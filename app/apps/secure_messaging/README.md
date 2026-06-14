# secure_messaging

Internal notification API for sending messages via Telegram and/or Email.

## API Format

### Request Schema

```json
{
  "app": "string (required) - Service identifier for internal logging only",
  "title": "string (optional) - Title rendered bold/larger. Becomes email subject",
  "message": "string (required) - Message content with markdown support",
  "provider": "string (optional) - 'telegram', 'email', or 'all' (default: 'all')",
  "sender": "string (optional) - Sender name from configured senders",
  "to": "string (optional) - Recipient key or direct address. Comma-separated for multiple"
}
```

### Markdown Support

- **Telegram**: HTML tags (`<b>`, `<i>`, `<u>`, `<code>`, `<pre>`) auto-converted to Telegram MarkdownV2
- **Email**: Markdown converted to HTML. Title becomes email subject.

### Examples

**Simple message (no title):**
```bash
curl -X POST http://localhost:8889/v1/notify \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"app":"backup","message":"Backup completed successfully","sender":"backup","to":"info"}'
```

**With title (sends to both providers if configured):**
```bash
curl -X POST http://localhost:8889/v1/notify \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"app":"backup","title":"Backup Completed","message":"Database backup finished","provider":"all","sender":"backup","to":"info"}'
```

**With HTML formatting:**
```bash
curl -X POST http://localhost:8889/v1/notify \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"app":"app","title":"Alert","message":"<b>Critical:</b> Disk usage at 90%","sender":"backup","to":"warning"}'
```

**Multiple recipients:**
```bash
curl -X POST http://localhost:8889/v1/notify \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"app":"app","message":"Announcement","sender":"backup","to":"info,warning,admin@example.com"}'
```

## Configuration

See `local.env` for environment variable templates. Key configs:

- `SECURE_MESSAGING_TELEGRAM_SENDERS_JSON` - Telegram sender configs with recipient keys
- `SECURE_MESSAGING_TELEGRAM_SENDER_TOKENS_JSON` - Bot tokens (gitignored in production)
- `SECURE_MESSAGING_EMAIL_SENDERS_JSON` - SMTP configs with recipient keys
- `SECURE_MESSAGING_EMAIL_SENDER_PASSWORDS_JSON` - SMTP passwords (gitignored in production)

### Sender Config Example

```json
{
  "backup": {
    "info": "-5109048777",
    "warning": "-5139430766",
    "error": "-4994923325"
  }
}
```

The `to` field in requests can reference these keys (`info`, `warning`, `error`) or provide direct addresses.
