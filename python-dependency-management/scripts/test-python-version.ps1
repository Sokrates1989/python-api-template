# test-python-version.ps1
# PowerShell version of test-python-version.sh
# Test script to verify Python version configuration

$ErrorActionPreference = "Stop"

# Change to project root (script is in python-dependency-management\scripts\)
Set-Location (Join-Path $PSScriptRoot "..\..") 

# Helper function for colored output
function Write-ColorOutput {
    param(
        [Parameter(Position=0)]
        [string]$Message,
        [Parameter(Position=1)]
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

# Function to provide diagnostic information
function Show-Diagnostics {
    Write-Host ""
    Write-ColorOutput "Diagnostic Information:" "Cyan"
    Write-ColorOutput "=======================" "Cyan"
    
    # Check Docker
    try {
        $null = & docker --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "[OK] Docker is installed" "Green"
            try {
                $null = & docker info 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-ColorOutput "[OK] Docker is running" "Green"
                } else {
                    Write-ColorOutput "[ERROR] Docker is not running" "Red"
                }
            } catch {
                Write-ColorOutput "[ERROR] Docker is not running" "Red"
            }
        } else {
            Write-ColorOutput "[ERROR] Docker is not installed" "Red"
        }
    } catch {
        Write-ColorOutput "[ERROR] Docker is not installed" "Red"
    }
    
    # Check .env file
    if (Test-Path .env) {
        Write-ColorOutput "[OK] .env file exists" "Green"
        $envContent = Get-Content .env -Raw
        if ($envContent -match "PYTHON_VERSION") {
            Write-ColorOutput "[OK] PYTHON_VERSION is defined in .env" "Green"
            $pythonVersionLine = (Get-Content .env | Where-Object { $_ -match "PYTHON_VERSION" }) -join ", "
            Write-ColorOutput "   Current value: $pythonVersionLine" "Gray"
        } else {
            Write-ColorOutput "[ERROR] PYTHON_VERSION not found in .env" "Red"
        }
    } else {
        Write-ColorOutput "[ERROR] .env file does not exist" "Red"
    }
    
    # Check required files
    if (Test-Path Dockerfile) {
        Write-ColorOutput "[OK] Main Dockerfile exists" "Green"
    } else {
        Write-ColorOutput "[ERROR] Main Dockerfile missing" "Red"
    }
    
    if (Test-Path python-dependency-management\Dockerfile) {
        Write-ColorOutput "[OK] Dependency management Dockerfile exists" "Green"
    } else {
        Write-ColorOutput "[ERROR] Dependency management Dockerfile missing" "Red"
    }
    
    if (Test-Path docker\docker-compose.yml) {
        Write-ColorOutput "[OK] Main docker-compose.yml exists" "Green"
    } else {
        Write-ColorOutput "[ERROR] Main docker\docker-compose.yml missing" "Red"
    }
    
    if (Test-Path docker\docker-compose-python-dependency-management.yml) {
        Write-ColorOutput "[OK] Dependency management docker-compose.yml exists" "Green"
    } else {
        Write-ColorOutput "[ERROR] Dependency management docker\docker-compose-python-dependency-management.yml missing" "Red"
    }
}

Write-ColorOutput "Testing Python version configuration..." "Cyan"
Write-ColorOutput "========================================" "Cyan"

# Load environment variables
if (Test-Path .env) {
    # Read .env file and set environment variables
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    
    $PYTHON_VERSION = $env:PYTHON_VERSION
    Write-ColorOutput "[OK] Loaded .env file" "Green"
    Write-ColorOutput "  PYTHON_VERSION: $PYTHON_VERSION" "Gray"
} else {
    Write-ColorOutput "[ERROR] .env file not found" "Red"
    Write-ColorOutput "   Please ensure .env file exists in the project root" "Yellow"
    Show-Diagnostics
    exit 1
}

# Test main Dockerfile
Write-Host ""
Write-ColorOutput "Testing main Dockerfile..." "Cyan"
try {
    $null = & docker build --build-arg PYTHON_VERSION=$env:PYTHON_VERSION -t test-main . 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "[OK] Main Dockerfile builds successfully with Python $env:PYTHON_VERSION" "Green"
    } else {
        throw "Build failed"
    }
} catch {
    Write-ColorOutput "[ERROR] Main Dockerfile build failed" "Red"
    Write-ColorOutput "   Error: Docker build failed for main application" "Yellow"
    Write-ColorOutput "   Possible causes:" "Yellow"
    Write-ColorOutput "   - Docker not running" "Gray"
    Write-ColorOutput "   - Invalid PYTHON_VERSION in .env file" "Gray"
    Write-ColorOutput "   - Network connectivity issues" "Gray"
    Write-ColorOutput "   - Insufficient disk space" "Gray"
    Show-Diagnostics
    exit 1
}

# Test python-dependency-management Dockerfile
Write-Host ""
Write-ColorOutput "Testing python-dependency-management Dockerfile..." "Cyan"
Push-Location python-dependency-management
try {
    $null = & docker build --build-arg PYTHON_VERSION=$env:PYTHON_VERSION -t test-dev . 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "[OK] Dependency management Dockerfile builds successfully with Python $env:PYTHON_VERSION" "Green"
    } else {
        throw "Build failed"
    }
} catch {
    Write-ColorOutput "[ERROR] Dependency management Dockerfile build failed" "Red"
    Write-ColorOutput "   Error: Docker build failed for dependency management" "Yellow"
    Write-ColorOutput "   Possible causes:" "Yellow"
    Write-ColorOutput "   - Docker not running" "Gray"
    Write-ColorOutput "   - Invalid PYTHON_VERSION in .env file" "Gray"
    Write-ColorOutput "   - Network connectivity issues" "Gray"
    Write-ColorOutput "   - Insufficient disk space" "Gray"
    Pop-Location
    Show-Diagnostics
    exit 1
} finally {
    Pop-Location
}

# Test docker-compose builds
Write-Host ""
Write-ColorOutput "Testing docker-compose builds..." "Cyan"
try {
    $null = & docker compose -f docker\docker-compose.yml build --no-cache 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "[OK] Main docker-compose builds successfully" "Green"
    } else {
        throw "Build failed"
    }
} catch {
    Write-ColorOutput "[ERROR] Main docker\docker-compose.yml build failed" "Red"
    Write-ColorOutput "   Error: Docker compose build failed for main application" "Yellow"
    Write-ColorOutput "   Possible causes:" "Yellow"
    Write-ColorOutput "   - Docker not running" "Gray"
    Write-ColorOutput "   - Invalid environment variables in .env file" "Gray"
    Write-ColorOutput "   - Network connectivity issues" "Gray"
    Write-ColorOutput "   - Insufficient disk space" "Gray"
    Show-Diagnostics
    exit 1
}

try {
    $null = & docker compose -f docker\docker-compose-python-dependency-management.yml build --no-cache 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "[OK] Dependency management docker-compose builds successfully" "Green"
    } else {
        throw "Build failed"
    }
} catch {
    Write-ColorOutput "[ERROR] Dependency management docker\docker-compose-python-dependency-management.yml build failed" "Red"
    Write-ColorOutput "   Error: Docker compose build failed for dependency management" "Yellow"
    Write-ColorOutput "   Possible causes:" "Yellow"
    Write-ColorOutput "   - Docker not running" "Gray"
    Write-ColorOutput "   - Invalid environment variables in .env file" "Gray"
    Write-ColorOutput "   - Insufficient disk space" "Gray"
    Show-Diagnostics
    exit 1
}

Write-Host ""
Write-ColorOutput "[SUCCESS] Python version configuration test completed!" "Green"
Write-ColorOutput "======================================================" "Green"
