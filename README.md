# 🚀 FastAPI Redis API Template

A production-grade, Dockerized FastAPI template project using environment-based configuration, Redis cache support, and optional integrations like Neo4j or AWS – with full support for both **Docker Compose** and **Poetry**-based development.

## 📚 Table of Contents

1. [📖 Overview](#-overview)  
2. [🧑‍💻 Usage](#-usage)  
3. [🛠️ Configuration](#-configuration)  
   - [📁 1. Clone the Project](#-1-clone-the-project)  
   - [⚙️ 2. Setup the .env File](#-2-setup-the-env-file)  
   - [🔐 3. Secrets from 1Password](#-3-secrets-from-1password)  
   - [🧩 4. Environment Variable Reference](#-4-environment-variable-reference)  
   - [📝 Example .env File](#-example-env-file)  
4. [📦 Docker Deployment](#-docker-deployment)  
5. [🧪 Local Development](#-local-development)  
   - [🔹 With Poetry (recommended)](#-with-poetry-recommended)  
   - [🔹 Without Poetry (classic pip)](#-without-poetry-classic-pip)  
6. [🧪 API Testing](#-api-testing)  
7. [🗂️ Project Structure](#-project-structure)  
8. [📤 Build & Publish Docker Image](#-build--publish-docker-image)  
9. [🚀 Summary](#-summary)

<br>
<br>

# 📖 Overview

This template is a clean and extensible Python FastAPI project that includes:

- ✅ FastAPI framework with automatic docs
- ✅ Redis integration as a caching layer
- ✅ Docker & Docker Compose for reproducible environments
- ✅ Support for `.env`-based config via `pydantic-settings`
- ✅ Optional integrations for Neo4j and AWS
- ✅ Fully Poetry-compatible for Python dependency management

<br>
<br>

# 🧑‍💻 Usage

You can start the project using either:

- Docker Compose  
- Local Python environment using Poetry (or pip)

<br>
<br>

# 🛠️ Configuration

## 📁 1. Clone the Project

```bash
git clone https://gitlab.com/speedie3/fastapi-redis-api-test
cd fastapi-redis-api-test
```

<br>
<br>

## ⚙️ 2. Setup the `.env` File

Start by copying the template:

```bash
cp .env.template .env
```

Then fill in your actual values (see below).

<br>
<br>

## 🔐 3. Secrets from 1Password

Secrets like DB passwords or tokens are stored in the **1Password Vault `Fontanherzen`**:

- `NEO4J_URL`
- `DB_USER`
- `DB_PASSWORD`
- (optional) `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, etc.

<br>
<br>

## 🧩 4. Environment Variable Reference

| Variable               | Purpose                                |
|------------------------|----------------------------------------|
| `PORT`                | Port to expose API on (default: `8000`) |
| `REDIS_URL`           | URL to connect to Redis instance        |
| `NEO4J_URL`           | (optional) Neo4j DB connection URL      |
| `DB_USER`             | (optional) DB user                      |
| `DB_PASSWORD`         | (optional) DB password                  |

<br>
<br>

## 📝 Example `.env` File

```dotenv
PORT=8000
REDIS_URL=redis://redis:6379
NEO4J_URL=bolt://localhost:7687
DB_USER=neo4j
DB_PASSWORD=secret-password
```

<br>
<br>

# 📦 Docker Deployment

Run the app and Redis DB together:

```bash
docker-compose up --build
```

**Use this value in your `.env`:**
```
dotenv
REDIS_URL=redis://redis:6379
```

you can then access the app at [http://localhost:8000/docs](http://localhost:8000/docs)

<br>
<br>

# 🧪 Local Development

## 🔹 With Poetry (recommended)

1. Install Poetry (if not already installed):

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Start Redis manually (in another terminal):
```
bash
docker run --rm -p 6379:6379 redis:6.0
```

3. Use the following `.env` value:
```
dotenv
REDIS_URL=redis://localhost:6379
```

4. Generate new lockfile:

```bash
poetry lock
```

5. Install dependencies:

```bash
poetry install
```

6. Start the API server:

```bash
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

<br>
<br>

## 🔹 Without Poetry (classic pip)

1. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the server:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

<br>
<br>

# 🧪 API Testing

After the app is up:

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- OpenAPI JSON: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

Test routes:
- `GET /` – Increments Redis key `visits`
- `GET /cache/{key}` – Get cache value
- `POST /cache/{key}` – Set cache value
- `GET /health` – Health check
- `GET /version` – Shows current image tag

<br>
<br>

# 🗂️ Project Structure

```bash
.
├── main.py
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── files.py
│   │   └── test.py
│   └── settings.py
├── backend/
│   └── Neo4jHandler.py
├── .env.template
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── poetry.lock
└── README.md
```

<br>
<br>


# 📤 Build & Publish Docker Image

This section explains how to build and publish a **Linux/amd64-compatible Docker image** to GitLab's container registry for use in Azure Container Apps (ACA).

## ⚡ TL;DR

If everything is configured correctly, you can just run:

```bash
export IMAGE_TAG=0.1.0
docker login registry.gitlab.com -u gitlab+deploy-token-XXXXXX -p YOUR_DEPLOY_TOKEN
docker buildx build --platform linux/amd64 --build-arg IMAGE_TAG=$IMAGE_TAG -t registry.gitlab.com/speedie3/fastapi-redis-api-test:$IMAGE_TAG --push .
```


<br>

## 📋 Notes

- You **must** use `docker buildx` to ensure compatibility with Azure's Linux-based runtime.
- Your **IMAGE_TAG** should match the version you want to deploy (e.g. `0.1.0`).
- The final image will be pushed to:

```yaml
registry.gitlab.com/speedie3/fastapi-redis-api-test:<IMAGE_TAG>
```

<br>


## ✅ Precheck (Optional but Recommended)

Before building or pushing your image, verify the following:

### 🧱 Is `buildx` available?

```bash
docker buildx version
```

### 🔐 Test registry access

Get Deploy token username and pw from [1Password](https://engaigegmbh.1password.com/)

```bash
docker login registry.gitlab.com -u gitlab+deploy-token-123456 -p YOUR_GENERATED_TOKEN
```

### 🔑 How to Create a GitLab Deploy Token 

To publish Docker images to GitLab’s Container Registry, you need a **Deploy Token** with write access.

Follow these steps:

1. Go to your GitLab project  
   ➤ [GitLab Repo Settings → Repository](https://gitlab.com/pmichiels/fastapi-redis-api-test/-/settings/repository#js-deploy-tokens)

2. Scroll to **Deploy Tokens**.

3. Fill in:
   - **Name**: e.g. `Docker Push`
   - **Username**: Auto-generated
   - **Scopes**:
     - ✅ **Read Registry**
     - ✅ **Write Registry**

4. Click **Create Deploy Token**.

5. Copy the generated:
   - `username` (e.g. `gitlab+deploy-token-123456`)
   - `password` (will be shown **once**)

6. Use them in your Docker login step:

```bash
docker login registry.gitlab.com -u gitlab+deploy-token-123456 -p YOUR_GENERATED_TOKEN
```


<br>
<br>

## 🔐 0. Docker Login (required once)

Login using your **GitLab Deploy Token** (must have write access):

```bash
docker login registry.gitlab.com -u gitlab+deploy-token-XXXXXX -p YOUR_DEPLOY_TOKEN
```

<br>

## 🏗️ 1. Set the desired image tag

Set your version string (only the tag, not the full registry path):

```bash
export IMAGE_TAG=0.1.0
```

<br>

### 🧱 2. Build and push the image (Linux/amd64)

Use `docker buildx` to build for the correct platform and push directly to the registry:

;;;bash
docker buildx build --platform linux/amd64 --build-arg IMAGE_TAG=$IMAGE_TAG -t registry.gitlab.com/speedie3/fastapi-redis-api-test:$IMAGE_TAG --push .
;;;

> 📝 `--push` is required because `buildx` builds in a separate context and won't store the image locally unless you use `--load`.


<br>
<br>

# 🚀 Summary

✅ **FastAPI + Redis integrated template**  
✅ **Supports Docker, Poetry & pip workflows**  
✅ **Secure config with `.env` and 1Password usage**  
✅ **Extensible architecture for real-world use cases**  
✅ **Interactive docs out of the box**
