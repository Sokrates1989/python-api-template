# 🚀 FastAPI Redis API Template

A production-grade, Dockerized FastAPI template project using environment-based configuration, Redis cache support, and optional integrations like Neo4j or AWS – with full support for both **Docker Compose** and **Poetry**-based development.

---

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
8. [🚀 Summary](#-summary)  

---

## 📖 Overview

This template is a clean and extensible Python FastAPI project that includes:

- ✅ FastAPI framework with automatic docs
- ✅ Redis integration as a caching layer
- ✅ Docker & Docker Compose for reproducible environments
- ✅ Support for `.env`-based config via `pydantic-settings`
- ✅ Optional integrations for Neo4j and AWS
- ✅ Fully Poetry-compatible for Python dependency management

---

## 🧑‍💻 Usage

You can start the project using either:

- Docker Compose  
- Local Python environment using Poetry (or pip)

---

## 🛠️ Configuration

### 📁 1. Clone the Project

```bash
git clone https://gitlab.com/speedie3/fastapi-redis-api-test
cd fastapi-redis-api-test
```

---

### ⚙️ 2. Setup the `.env` File

Start by copying the template:

```bash
cp .env.template .env
```

Then fill in your actual values (see below).

---

### 🔐 3. Secrets from 1Password

Secrets like DB passwords or tokens are stored in the **1Password Vault `Fontanherzen`**:

- `NEO4J_URL`
- `DB_USER`
- `DB_PASSWORD`
- (optional) `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, etc.

---

### 🧩 4. Environment Variable Reference

| Variable               | Purpose                                |
|------------------------|----------------------------------------|
| `PORT`                | Port to expose API on (default: `8000`) |
| `REDIS_URL`           | URL to connect to Redis instance        |
| `NEO4J_URL`           | (optional) Neo4j DB connection URL      |
| `DB_USER`             | (optional) DB user                      |
| `DB_PASSWORD`         | (optional) DB password                  |

---

### 📝 Example `.env` File

```dotenv
PORT=8000
REDIS_URL=redis://redis:6379
NEO4J_URL=bolt://localhost:7687
DB_USER=neo4j
DB_PASSWORD=secret-password
```

---

## 📦 Docker Deployment

Run the app and Redis DB together:

```bash
docker-compose up --build
```

**Use this value in your `.env`:**
```
dotenv
REDIS_URL=redis://redis:6379
```
---

You can then access the app at [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Local Development

### 🔹 With Poetry (recommended)

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

---

### 🔹 Without Poetry (classic pip)

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

---

## 🧪 API Testing

After the app is up:

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- OpenAPI JSON: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

Test routes:
- `GET /` – Increments Redis key `visits`
- `GET /cache/{key}` – Get cache value
- `POST /cache/{key}` – Set cache value
- `GET /health` – Health check
- `GET /version` – Shows current image tag

---

## 🗂️ Project Structure

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

---

## 🚀 Summary

✅ **FastAPI + Redis integrated template**  
✅ **Supports Docker, Poetry & pip workflows**  
✅ **Secure config with `.env` and 1Password usage**  
✅ **Extensible architecture for real-world use cases**  
✅ **Interactive docs out of the box**
