# quick-start.ps1
# PowerShell version of quick-start.sh
# Complete onboarding tool for freshly cloned projects

$ErrorActionPreference = "Stop"

Write-Host "FastAPI Redis API Test - Quick Start" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check Docker availability
Write-Host "Checking Docker installation..." -ForegroundColor Yellow
try {
    $null = docker --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker not found" }
} catch {
    Write-Host "[ERROR] Docker is not installed!" -ForegroundColor Red
    Write-Host "Please install Docker from: https://www.docker.com/get-started" -ForegroundColor Yellow
    exit 1
}

# Check Docker daemon
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon not running" }
} catch {
    Write-Host "[ERROR] Docker daemon is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop or the Docker service" -ForegroundColor Yellow
    exit 1
}

# Check Docker Compose
try {
    $null = docker compose version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose not available" }
} catch {
    Write-Host "[ERROR] Docker Compose is not available!" -ForegroundColor Red
    Write-Host "Please install a current Docker version with Compose plugin" -ForegroundColor Yellow
    exit 1
}

Write-Host "Docker is installed and running" -ForegroundColor Green
Write-Host ""

# Check if initial setup is needed
if (-not (Test-Path .setup-complete)) {
    Write-Host " First-time setup detected!" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This appears to be your first time running this project." -ForegroundColor Yellow
    Write-Host "Would you like to run the interactive setup wizard?" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The setup wizard will help you configure:" -ForegroundColor Gray
    Write-Host "  - Docker image name and version" -ForegroundColor Gray
    Write-Host "  - Python version" -ForegroundColor Gray
    Write-Host "  - Database type (PostgreSQL or Neo4j)" -ForegroundColor Gray
    Write-Host "  - Database mode (local or external)" -ForegroundColor Gray
    Write-Host "  - API configuration" -ForegroundColor Gray
    Write-Host ""
    
    $runSetup = Read-Host "Run setup wizard now? (Y/n)"
    if ($runSetup -ne "n" -and $runSetup -ne "N") {
        Write-Host ""
        Write-Host "Starting setup wizard..." -ForegroundColor Cyan
        docker compose -f interactive-scripts/docker-compose.setup.yml run --rm setup
        Write-Host ""
    } else {
        Write-Host ""
        Write-Host "Skipping setup wizard. Creating basic .env from template..." -ForegroundColor Yellow
        if (Test-Path config\.env.template) {
            Copy-Item config\.env.template .env
            Write-Host ".env file created from template." -ForegroundColor Green
            Write-Host "  Please edit .env to configure your environment before continuing." -ForegroundColor Yellow
        } else {
            Write-Host "[ERROR] config\.env.template not found!" -ForegroundColor Red
            exit 1
        }
    }
    Write-Host ""
} elseif (-not (Test-Path .env)) {
    # Setup complete but .env missing - recreate from template
    Write-Host " .env file missing. Creating from template..." -ForegroundColor Yellow
    if (Test-Path config\.env.template) {
        Copy-Item config\.env.template .env
        Write-Host ".env file created from template." -ForegroundColor Green
        Write-Host "Please check the values in .env if needed." -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] config\.env.template not found!" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

# Read PORT from .env (default: 8000)
$PORT = "8000"
if (Test-Path .env) {
    $envContent = Get-Content .env -ErrorAction SilentlyContinue
    $portLine = $envContent | Where-Object { $_ -match "^PORT=" }
    if ($portLine) {
        $PORT = ($portLine -split "=", 2)[1].Trim().Trim('"')
    }
}

# Read database configuration from .env
$DB_TYPE = "neo4j"
$DB_MODE = "local"
if (Test-Path .env) {
    $envContent = Get-Content .env -ErrorAction SilentlyContinue
    
    $dbTypeLine = $envContent | Where-Object { $_ -match "^DB_TYPE=" }
    if ($dbTypeLine) {
        $DB_TYPE = ($dbTypeLine -split "=", 2)[1].Trim().Trim('"')
    }
    
    $dbModeLine = $envContent | Where-Object { $_ -match "^DB_MODE=" }
    if ($dbModeLine) {
        $DB_MODE = ($dbModeLine -split "=", 2)[1].Trim().Trim('"')
    }
}

# Determine Docker Compose file based on DB_TYPE and DB_MODE
if ($DB_MODE -eq "external") {
    $COMPOSE_FILE = "docker\docker-compose.yml"
    Write-Host "Detected external database mode" -ForegroundColor Cyan
    Write-Host "   Database Type: $DB_TYPE" -ForegroundColor Gray
    Write-Host "   Will connect to external database (no local DB container)" -ForegroundColor Gray
} elseif ($DB_TYPE -eq "neo4j") {
    $COMPOSE_FILE = "docker\docker-compose.neo4j.yml"
    Write-Host "Detected local Neo4j database" -ForegroundColor Cyan
    Write-Host "   Will start Neo4j container" -ForegroundColor Gray
} elseif ($DB_TYPE -eq "postgresql" -or $DB_TYPE -eq "mysql") {
    $COMPOSE_FILE = "docker\docker-compose.postgres.yml"
    Write-Host "Detected local $DB_TYPE database" -ForegroundColor Cyan
    Write-Host "   Will start PostgreSQL container" -ForegroundColor Gray
} else {
    $COMPOSE_FILE = "docker\docker-compose.yml"
    Write-Host "Unknown DB_TYPE: $DB_TYPE, using default docker\docker-compose.yml" -ForegroundColor Yellow
}

Write-Host "   Using: $COMPOSE_FILE" -ForegroundColor Gray
Write-Host ""

# Check if this is the first setup run
if (-not (Test-Path .setup-complete)) {
    Write-Host "First setup detected - Running automatic dependency configuration..." -ForegroundColor Cyan
    Write-Host "The first start may take a bit longer, but it will be much faster afterwards." -ForegroundColor Yellow
    Write-Host ""
    
    # Test Python version configuration first
    if (Test-Path python-dependency-management\scripts\test-python-version.ps1) {
        Write-Host "Testing Python version configuration..." -ForegroundColor Yellow
        Write-Host "Running Python version tests..." -ForegroundColor Gray
        try {
            & .\python-dependency-management\scripts\test-python-version.ps1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Python version configuration test passed" -ForegroundColor Green
            } else {
                Write-Host ""
                Write-Host "Python version configuration test failed!" -ForegroundColor Red
                Write-Host "This indicates a problem with your .env file or Docker setup." -ForegroundColor Yellow
                Write-Host ""
                Write-Host "Troubleshooting steps:" -ForegroundColor Yellow
                Write-Host "1. Check if .env file exists and contains PYTHON_VERSION=3.13" -ForegroundColor Gray
                Write-Host "2. Ensure Docker is running: docker --version" -ForegroundColor Gray
                Write-Host "3. Verify .env file format: Get-Content .env" -ForegroundColor Gray
                Write-Host ""
                Write-Host "The following steps may fail if Python version is not configured correctly." -ForegroundColor Yellow
                $continue = Read-Host "Continue anyway? (y/N)"
                if ($continue -notmatch "^[Yy]$") {
                    Write-Host "Setup aborted. Please fix the Python version configuration first." -ForegroundColor Red
                    exit 1
                }
                Write-Host "Continuing with potentially broken configuration..." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "Error running Python version test: $_" -ForegroundColor Red
            Write-Host "Skipping version test..." -ForegroundColor Yellow
        }
    } else {
        Write-Host "python-dependency-management\scripts\test-python-version.ps1 not found - skipping version test" -ForegroundColor Yellow
    }
    
    Write-Host ""
    
    # Run Dependency Management in initial-run mode
    if (Test-Path python-dependency-management\scripts\manage-python-project-dependencies.ps1) {
        Write-Host "Starting Dependency Management for initial setup..." -ForegroundColor Cyan
        try {
            & .\python-dependency-management\scripts\manage-python-project-dependencies.ps1 -InitialRun
        } catch {
            Write-Host "Error running dependency management: $_" -ForegroundColor Red
            Write-Host "Dependencies will be installed when Docker builds the container" -ForegroundColor Yellow
        }
    } else {
        Write-Host "python-dependency-management\scripts\manage-python-project-dependencies.ps1 not found - skipping" -ForegroundColor Yellow
        Write-Host "Dependencies will be installed when Docker builds the container" -ForegroundColor Yellow
    }
    
    # Mark setup as complete
    New-Item -ItemType File -Path .setup-complete -Force | Out-Null
    
    Write-Host ""
    Write-Host "First setup complete!" -ForegroundColor Green
    Write-Host "Starting backend now..." -ForegroundColor Cyan
    Write-Host "Backend will be available at: http://localhost:$PORT" -ForegroundColor Cyan
    Write-Host ""
    docker compose -f $COMPOSE_FILE up --build
} else {
    Write-Host "Starting backend with Docker Compose..." -ForegroundColor Cyan
    Write-Host "Backend will be available at: http://localhost:$PORT" -ForegroundColor Cyan
    Write-Host ""

    # Selection menu for subsequent starts
    Write-Host "Choose an option:" -ForegroundColor Yellow
    Write-Host "1) Start backend directly (docker compose up)" -ForegroundColor Gray
    Write-Host "2) Open Dependency Management first" -ForegroundColor Gray
    Write-Host "3) Both - Dependency Management and then start backend" -ForegroundColor Gray
    Write-Host "4) Test Python Version Configuration" -ForegroundColor Gray
    Write-Host "5) Build Production Docker Image" -ForegroundColor Gray
    Write-Host ""
    $choice = Read-Host "Your choice (1-5)"

    switch ($choice) {
        "1" {
            Write-Host "Starting backend directly..." -ForegroundColor Cyan
            docker compose -f $COMPOSE_FILE up --build
        }
        "2" {
            if (Test-Path python-dependency-management\scripts\manage-python-project-dependencies.ps1) {
                Write-Host "Opening Dependency Management..." -ForegroundColor Cyan
                & .\python-dependency-management\scripts\manage-python-project-dependencies.ps1
            } else {
                Write-Host "python-dependency-management\scripts\manage-python-project-dependencies.ps1 not found" -ForegroundColor Red
            }
            Write-Host ""
            Write-Host "To start the backend, run: docker compose -f $COMPOSE_FILE up --build" -ForegroundColor Yellow
        }
        "3" {
            if (Test-Path python-dependency-management\scripts\manage-python-project-dependencies.ps1) {
                Write-Host "Opening Dependency Management first..." -ForegroundColor Cyan
                & .\python-dependency-management\scripts\manage-python-project-dependencies.ps1
            } else {
                Write-Host "python-dependency-management\scripts\manage-python-project-dependencies.ps1 not found" -ForegroundColor Red
                Write-Host "Skipping dependency management." -ForegroundColor Yellow
            }
            Write-Host ""
            Write-Host "Starting backend now..." -ForegroundColor Cyan
            docker compose -f $COMPOSE_FILE up --build
        }
        "4" {
            if (Test-Path python-dependency-management\scripts\test-python-version.ps1) {
                Write-Host "Testing Python version configuration..." -ForegroundColor Yellow
                & .\python-dependency-management\scripts\test-python-version.ps1
            } else {
                Write-Host "python-dependency-management\scripts\test-python-version.ps1 not found" -ForegroundColor Red
            }
        }
        "5" {
            Write-Host "Building production Docker image..." -ForegroundColor Cyan
            Write-Host ""
            if (Test-Path build-image\docker-compose.build.yml) {
                docker compose -f build-image\docker-compose.build.yml run --rm build-image
            } else {
                Write-Host "build-image\docker-compose.build.yml not found" -ForegroundColor Red
                Write-Host "Please ensure the build-image directory exists" -ForegroundColor Yellow
            }
        }
        default {
            Write-Host "Invalid selection. Starting backend directly..." -ForegroundColor Yellow
            docker compose -f $COMPOSE_FILE up --build
        }
    }
}