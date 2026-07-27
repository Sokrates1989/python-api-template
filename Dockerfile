# Use the official Python base image.
# Release tooling passes exact public build inputs and records them in OCI labels.
ARG PYTHON_VERSION=3.13-slim
ARG BACKEND_APP_ID=demo_app
FROM python:${PYTHON_VERSION}

# Bind build and runtime identity to the same selected backend app.
ARG IMAGE_TAG=local_docker
ARG APP_PROFILE=demo_app
ARG BACKEND_APP_ID=demo_app
ARG BACKEND_DATA_PROFILE=
ARG PDM_VERSION=2.27.0
ARG SOURCE_REVISION=unknown
ARG DEPENDENCY_LOCK_SHA256=unknown
ENV IMAGE_TAG=$IMAGE_TAG
ENV BACKEND_APP_ID=$BACKEND_APP_ID
ENV APP_PROFILE=$APP_PROFILE

LABEL org.opencontainers.image.title="Python API selected-app runtime" \
      org.opencontainers.image.description="Production API image for one explicitly selected backend app" \
      org.opencontainers.image.version="${IMAGE_TAG}" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.vendor="Felicitas & Wisdom" \
      com.fe-wi.backend-app-id="${BACKEND_APP_ID}" \
      com.fe-wi.app-profile="${APP_PROFILE}" \
      com.fe-wi.dependency-lock-sha256="${DEPENDENCY_LOCK_SHA256}" \
      com.fe-wi.pdm-version="${PDM_VERSION}"

# Set the working directory in the container
WORKDIR /app

# A production image must never contain mismatched build/runtime selectors.
RUN test "${BACKEND_APP_ID}" = "${APP_PROFILE}"

# Copy app dependency files first for better build caching. Dockerfile COPY
# instructions cannot use shell redirection or fallback operators, so the
# selected backend app must provide its own dependency manifest.
COPY app/apps /tmp/backend-apps

# Install only the database client tools needed by the selected backend app.
# PostgreSQL/MySQL backup and restore helpers shell out to provider CLIs, while
# MongoDB currently exposes stats through the Python driver and no CLI backups.
RUN set -eux; \
    db_profile="$(printf '%s' "${BACKEND_DATA_PROFILE}" | tr '[:upper:]' '[:lower:]')"; \
    if [ -z "${db_profile}" ]; then \
        db_profile="$( \
            for metadata_file in \
                "/tmp/backend-apps/${BACKEND_APP_ID}/definition.py" \
                "/tmp/backend-apps/${BACKEND_APP_ID}/config/app_metadata.py"; do \
                if [ -f "${metadata_file}" ]; then \
                    sed -n -E 's/.*(backend_data_profile|db_type)[[:space:]:=]+[^"]*"([^"]+)".*/\2/p' "${metadata_file}"; \
                fi; \
            done | head -n 1 | tr '[:upper:]' '[:lower:]' \
        )"; \
    fi; \
    case "${db_profile}" in \
        postgresql|postgres) database_client_packages="postgresql-client" ;; \
        mysql|mariadb) database_client_packages="mariadb-client" ;; \
        sql) database_client_packages="postgresql-client mariadb-client" ;; \
        *) database_client_packages="" ;; \
    esac; \
    if [ -n "${database_client_packages}" ]; then \
        apt-get update && \
        apt-get install -y --no-install-recommends ${database_client_packages} && \
        rm -rf /var/lib/apt/lists/*; \
    else \
        echo "No database client packages required for backend data profile: ${db_profile:-unknown}"; \
    fi

# Install a pinned PDM release and the exact app-owned production lock.
RUN if [ -f "/tmp/backend-apps/${BACKEND_APP_ID}/pyproject.toml" ] && [ -f "/tmp/backend-apps/${BACKEND_APP_ID}/pdm.lock" ]; then \
        cp "/tmp/backend-apps/${BACKEND_APP_ID}/pyproject.toml" /app/pyproject.toml && \
        cp "/tmp/backend-apps/${BACKEND_APP_ID}/pdm.lock" /app/pdm.lock; \
    else \
        echo "Missing dependency files for backend app: ${BACKEND_APP_ID}" >&2 && \
        echo "Expected app/apps/${BACKEND_APP_ID}/pyproject.toml and app/apps/${BACKEND_APP_ID}/pdm.lock" >&2 && \
        exit 1; \
    fi && \
    python -m pip install --no-cache-dir "pdm==${PDM_VERSION}" && \
    pdm sync --prod --no-self

# Copy application code directly to /app
COPY app/ ./

# Copy Alembic migration files
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Add app directory to PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app

# Create a stable unprivileged runtime identity after all root-owned build work.
RUN groupadd --gid 10001 api && \
    useradd --uid 10001 --gid api --no-create-home --shell /usr/sbin/nologin api && \
    mkdir -p /app/logs /app/ai_chat_logs && \
    chown api:api /app/logs /app/ai_chat_logs

USER 10001:10001

# Expose the port that the FastAPI application will run on
EXPOSE 8000

# Health checking uses the Python standard library already present in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health',timeout=4).read()"]

# Execute uvicorn directly from the immutable app virtual environment. PDM is a
# build tool and is not invoked by the unprivileged runtime user.
# UVICORN_RELOAD is injected by local-dev compose stacks to enable in-process
# hot-reload (--reload). Production stacks leave it unset so --reload is never
# active in production. The ${UVICORN_RELOAD:+--reload} expansion is empty when
# UVICORN_RELOAD is unset or empty, and becomes "--reload" when it has any value.
ENTRYPOINT ["sh", "-c"]
CMD ["exec /app/.venv/bin/uvicorn main:app --host 0.0.0.0 --port \"${PORT:-8000}\" ${UVICORN_RELOAD:+--reload}"]
