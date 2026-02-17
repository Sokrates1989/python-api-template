ARG BASE_IMAGE=python:3.12-alpine
FROM ${BASE_IMAGE}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY keycloak_bootstrap.py .

ENTRYPOINT ["python", "keycloak_bootstrap.py"]
