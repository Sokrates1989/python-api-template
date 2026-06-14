<!--
Runtime logging directory documentation.
-->

# Runtime Logs

This directory is reserved for API runtime logs written by the Docker
container. The application writes combined logs to `api/log.txt`, warning and
error logs to `api/errorlog.txt`, and day-based copies under `api/dayBased/`.

The log files themselves are gitignored because they can contain operational
details. Deployment stacks can mount this directory to `/app/logs`, matching
the swarm pattern used by other services.
