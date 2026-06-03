# Use the official Python base image
# Build argument for Python version (defaults to 3.13 if not provided)
ARG PYTHON_VERSION=3.13-slim
ARG BACKEND_APP_ID=demo_app
ARG BACKEND_DATA_PROFILE=
FROM python:${PYTHON_VERSION}

# Bake Image tag into the image.
ARG IMAGE_TAG=local_docker
ENV IMAGE_TAG=$IMAGE_TAG
ARG BACKEND_APP_ID=demo_app
ENV BACKEND_APP_ID=$BACKEND_APP_ID
ARG BACKEND_DATA_PROFILE=

# Set the working directory in the container
WORKDIR /app

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

# Install PDM and project dependencies (creates a fresh .venv)
RUN if [ -f "/tmp/backend-apps/${BACKEND_APP_ID}/pyproject.toml" ] && [ -f "/tmp/backend-apps/${BACKEND_APP_ID}/pdm.lock" ]; then \
        cp "/tmp/backend-apps/${BACKEND_APP_ID}/pyproject.toml" /app/pyproject.toml && \
        cp "/tmp/backend-apps/${BACKEND_APP_ID}/pdm.lock" /app/pdm.lock; \
    else \
        echo "Missing dependency files for backend app: ${BACKEND_APP_ID}" >&2 && \
        echo "Expected app/apps/${BACKEND_APP_ID}/pyproject.toml and app/apps/${BACKEND_APP_ID}/pdm.lock" >&2 && \
        exit 1; \
    fi && \
    pip install pdm && pdm sync --prod --no-self

# Copy application code directly to /app
COPY app/ ./

# Copy Alembic migration files
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Add app directory to PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app

# Expose the port that the FastAPI application will run on
EXPOSE 8000

# Use 'pdm run' to execute uvicorn from within the project's virtual environment.
ENTRYPOINT ["pdm", "run"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
