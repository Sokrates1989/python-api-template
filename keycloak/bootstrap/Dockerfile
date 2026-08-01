ARG BASE_IMAGE=python:3.13-alpine
FROM ${BASE_IMAGE}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY keycloak_bootstrap.py bootstrap_safety.py bootstrap_errors.py keycloak_admin_operations.py ./

ENTRYPOINT ["python", "keycloak_bootstrap.py"]
