# Production Image Builder

This directory contains everything needed to build production-ready Docker images for the API.

## 🚀 Quick Start

### Selected-App Release Flow (Recommended)

Use the selected-app quick-start menu and choose one explicit action:

1. validate the image release plan;
2. build locally without pushing; or
3. Build & Push after a version increment and final confirmation.

**Windows (PowerShell):**
```powershell
.\quick-start.ps1
# Select: Validate, local build, or explicit Build & Push
```

**Linux/macOS (Bash):**
```bash
./quick-start.sh
# Select: Validate, local build, or explicit Build & Push
```

### Direct Build

The containerized builder below is retained only for legacy compatibility. It
loads and mutates root `.env`, has no selected-app evidence contract, and
automatically publishes both tags. Do not use it for a production release.
The quick-start menu delegates to `tools/release_api_image.py`.

```bash
docker compose -f build-image/docker-compose.build.yml run --rm build-image
```

## 📋 Configuration

### 1. Configure Image Name and Version

Each backend app keeps its committed release version in its own
`pyproject.toml`, for example `app/apps/postgres_template/pyproject.toml`:

```toml
[project]
name = "postgres_template"
version = "1.0.0"
```

The Docker image name is derived from the selected backend app:
`sokrates1989/python-api-<app-name>`.

App `.env` files stay focused on local runtime settings and secret-bearing
values. They are intentionally not used as the release version source of truth.

### 2. Build Process

The release tool will:
1. use the active backend app selected in quick-start;
2. bind `BACKEND_APP_ID` and `APP_PROFILE` to that same app;
3. read the committed version and exact app-owned `pdm.lock`;
4. build for `linux/amd64` with pinned PDM and OCI revision/lock labels;
5. inspect the non-root runtime and container healthcheck;
6. generate dependency and full-image SPDX SBOM evidence;
7. enforce the HIGH/CRITICAL vulnerability policy; and
8. write a sanitized ignored receipt.

Build-only stops there. Explicit Build & Push first creates a greater version
commit locally, runs the build gates, pushes that proven source commit, then
pushes `IMAGE_NAME:VERSION` and the `latest` convenience tag. Deployment
evidence binds only the immutable version and registry digest; `latest` is
never a deployment input.

## 🏗️ Build System Architecture

The build system uses the root-level `Dockerfile` for both development and production:

- **Root `Dockerfile`**: Used for local development AND production builds
- **`build-image/Dockerfile`**: Alpine Linux + Docker CLI environment to run the build script
- **`build-image/build-image.sh`**: Build script that runs inside the Alpine container

This approach ensures:
- ✅ Single source of truth for the Docker image
- ✅ Same image tested locally works in production
- ✅ Platform-independent builds (runs in Docker container)
- ✅ No duplicate Dockerfiles to maintain

## 🔐 Pushing to Docker Registry

### Docker Hub

1. Login to Docker Hub:
   ```bash
   docker login
   ```

2. Build and push (script will prompt):
   ```bash
docker compose -f build-image/docker-compose.build.yml run --rm build-image
```

### GitHub Container Registry (ghcr.io)

1. Create a Personal Access Token with `write:packages` permission
2. Login:
   ```bash
   echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
   ```
3. For the app-aware quick-start flow, use the canonical Docker Hub name
   `sokrates1989/python-api-<app-name>`. The legacy direct builder still reads
   custom registry names from `.env`.
4. Build and push

### GitLab Container Registry

1. Login:
   ```bash
   docker login registry.gitlab.com
   ```
2. For the app-aware quick-start flow, use the canonical Docker Hub name
   `sokrates1989/python-api-<app-name>`. The legacy direct builder still reads
   custom registry names from `.env`.
3. Build and push

## 🧪 Testing the Built Image

After building, test the image locally using the development docker-compose:

```bash
# Run the production image locally
docker run -p 8000:8000 --env-file .env your-username/your-api-name:0.0.1

# Or test with the regular development setup
docker compose -f docker/docker-compose.yml up
```

For production-like testing with Docker Swarm, see the [swarm-python-api-template](https://github.com/Sokrates1989/swarm-python-api-template) repository.

## 🚢 Deploying to Production

### Option 1: Docker Compose on Server

Create a `docker-compose.prod.yml` on your production server:

```yaml
version: '3.8'

services:
  app:
    image: your-username/your-api-name:1.0.0
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/dbname
      - REDIS_URL=redis://redis:6379
    restart: unless-stopped
    
  # Add database, redis, etc. as needed
```

Deploy:
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Option 2: Kubernetes

Create Kubernetes manifests or use Helm charts to deploy the image.

### Option 3: Cloud Platforms

- **AWS ECS/Fargate**: Use the image in task definitions
- **Google Cloud Run**: Deploy directly from container registry
- **Azure Container Instances**: Deploy the image
- **DigitalOcean App Platform**: Deploy from Docker Hub

## 🔄 CI/CD Integration

### GitHub Actions

1. Copy `.github/workflows/build-and-push.yml.example` to `.github/workflows/build-and-push.yml`
2. Create `.ci.env` from `.ci.env.template`
3. Add secrets to GitHub repository:
   - `DOCKER_USERNAME`
   - `DOCKER_PASSWORD`
4. Push to main branch or create a tag

### GitLab CI

1. Copy `.gitlab-ci.yml.example` to `.gitlab-ci.yml`
2. Create `.ci.env` from `.ci.env.template`
3. Add CI/CD variables in GitLab:
   - `DOCKER_USERNAME`
   - `DOCKER_PASSWORD`
4. Push to main branch or create a tag

## 📁 Files in this Directory

- **`Dockerfile`** - Alpine Linux + Docker CLI environment for running build script
- **`build-image.sh`** - Build script (runs inside Docker container)
- **`docker-compose.build.yml`** - Docker Compose config for building
- **`README.md`** - This file

**Note**: The actual production Dockerfile is at the root level: `../Dockerfile`

## 🔧 Advanced Usage

### Build with Custom Python Version

Edit `.env`:
```env
PYTHON_VERSION=3.12
```

### Build without Pushing

The script will prompt whether to push. Answer "N" to build only.

### Manual Build

```bash
docker buildx build \
  --build-arg PYTHON_VERSION=3.13-slim \
  --build-arg IMAGE_TAG=0.0.1 \
  -t your-username/your-api-name:0.0.1 \
  -t your-username/your-api-name:latest \
  -f Dockerfile \
  .
```

## 🆘 Troubleshooting

### Legacy builder: "IMAGE_NAME not set in .env"

The app-aware quick-start build derives its image name from the selected app.
Only the legacy direct builder requires `IMAGE_NAME` in `.env`.

### "Docker login failed"

Make sure you have valid credentials for your Docker registry.

### "Permission denied" on Linux

Make sure the build script is executable:
```bash
chmod +x build-image/build-image.sh
```

### Image too large

The production image should be smaller than the development image. If it's too large:
- Ensure you're using `-slim` Python base image
- Check that dev dependencies aren't being installed
- Consider using multi-stage builds for additional optimization

## 📚 Additional Resources

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Docker Security](https://docs.docker.com/engine/security/)
- [Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
