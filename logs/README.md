<!--
Runtime logging directory documentation.
-->

# Runtime Logs

This directory is reserved for API runtime logs written by the Docker
container. The application writes combined logs to `api/log.txt`, warning and
error logs to `api/errorlog.txt`, and day-based copies under `api/dayBased/`.
AI chat diagnostics are intentionally separated into `ai_chat/` so prompt,
context, provider, tool, moderation, and action traces can be inspected without
mixing them into the general API runtime stream.

The log files themselves are gitignored because they can contain operational
details. Deployment stacks can mount this directory to `/app/logs`, matching
the swarm pattern used by other services.
