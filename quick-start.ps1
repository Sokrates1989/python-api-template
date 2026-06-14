# quick-start.ps1
# PowerShell version of quick-start.sh
# Complete onboarding tool for freshly cloned projects

$ErrorActionPreference = "Stop"

# Ensure UTF-8 encoding so emoji/icons render correctly
try {
    if ([Console]::OutputEncoding.WebName -ne "utf-8") {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    }
    if ([Console]::InputEncoding.WebName -ne "utf-8") {
        [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    }
} catch {
    Write-Verbose "UTF-8 encoding enforcement skipped: $_"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$setupDir = Join-Path $projectRoot "setup"
$activeBackendAppStateFile = ".active_backend_app"
$activeBackendAppId = "demo_app"
$activeBackendEnvFile = ".env.flutter.demo.mongodb"

# Ensure a unique Docker Compose project name per repository to avoid clashes.
$composeProjectName = Split-Path $projectRoot -Leaf
if (-not $composeProjectName) {
    $composeProjectName = "python-api-template-local"
}
$env:COMPOSE_PROJECT_NAME = $composeProjectName
Write-Host "Using Docker Compose project: $composeProjectName" -ForegroundColor Gray

# Import modules
Import-Module "$setupDir\modules\docker_helpers.ps1" -Force
Import-Module "$setupDir\modules\version_manager.ps1" -Force
Import-Module "$setupDir\modules\menu_handlers.ps1" -Force

# Source Cognito setup script if available
$cognitoScript = Join-Path $setupDir "modules\cognito_setup.ps1"
if (Test-Path $cognitoScript) {
    . $cognitoScript
}

Write-Host "FastAPI Redis API Test - Quick Start" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

function Resolve-BackendEnvFile {
    param([string]$AppId)

    # Sanitize app ID - remove any characters that could cause path issues
    $safeAppId = $AppId -replace '[\\/:*?"<>|]', '_'

    # First check for app-specific env file in app/apps/<app>/env/
    # Use Join-Path to build path safely (handles separators correctly)
    $appEnvDir = Join-Path (Join-Path (Join-Path "app" "apps") $safeAppId) "env"
    $appSpecificEnv = Join-Path $appEnvDir ".env.$safeAppId"
    $fullPath = Join-Path $projectRoot $appSpecificEnv

    # Validate path doesn't contain wildcards or other problematic characters
    if ($fullPath -notmatch '[\[\]*?]') {
        try {
            if (Test-Path -LiteralPath $fullPath -ErrorAction SilentlyContinue) {
                return $appSpecificEnv
            }
        }
        catch {
            # Path error, fallback to presets
        }
    }

    # Fallback to root preset files for backward compatibility
    switch ($AppId) {
        "demo_app" { return ".env.flutter.demo.mongodb" }
        "mongodb_template" { return ".env.flutter.mongodb_template.mongodb" }
        "postgres_template" { return ".env.flutter.postgres_template.postgresql" }
        "template_app" { return ".env.flutter.template.postgresql" }
        "secure_messaging" { return "app\apps\secure_messaging\local.env" }
        default { return ".env" }
    }
}

function Resolve-BackendDependencyProjectRoot {
    param([string]$AppId)

    $safeAppId = $AppId -replace '[\\/:*?"<>|]', '_'
    $appRoot = Join-Path (Join-Path (Join-Path $projectRoot "app") "apps") $safeAppId
    $appProjectFile = Join-Path $appRoot "pyproject.toml"
    if (Test-Path -LiteralPath $appProjectFile -ErrorAction SilentlyContinue) {
        return $appRoot
    }

    return $projectRoot
}

function Resolve-BackendDeploymentRoot {
    param([string]$AppId)

    # Sanitize app ID for path safety
    $safeAppId = $AppId -replace '[\/:*?"<>|]', '_'

    $appDeploymentRoot = Join-Path (Join-Path (Join-Path $projectRoot 'app') 'apps') $safeAppId
    $appDeploymentRoot = Join-Path $appDeploymentRoot 'deployment'

    try {
        if (Test-Path -LiteralPath $appDeploymentRoot -ErrorAction SilentlyContinue) {
            return $appDeploymentRoot
        }
    }
    catch {
        # Path error, fallback to local-deployment
    }

    return (Join-Path $projectRoot "local-deployment")
}

function Resolve-BackendComposeManifest {
    param(
        [string]$AppId,
        [string]$DbMode
    )

    # Sanitize app ID for path safety
    $safeAppId = $AppId -replace '[\\/:*?"<>|\[\]]', '_'

    $appDeploymentDir = Join-Path (Join-Path (Join-Path $projectRoot 'app') 'apps') $safeAppId
    $appDeploymentDir = Join-Path $appDeploymentDir 'deployment'

    $defaultManifestPath = Join-Path $appDeploymentDir 'compose-files.txt'

    if (-not [string]::IsNullOrWhiteSpace($DbMode)) {
        $modeManifestPath = Join-Path $appDeploymentDir "compose-files.$DbMode.txt"
        try {
            if (Test-Path -LiteralPath $modeManifestPath -ErrorAction SilentlyContinue) {
                return $modeManifestPath
            }
        }
        catch { }
    }

    try {
        if (Test-Path -LiteralPath $defaultManifestPath -ErrorAction SilentlyContinue) {
            return $defaultManifestPath
        }
    }
    catch { }

    return ""
}

<#
.SYNOPSIS
Builds Docker Compose environment file arguments.

.DESCRIPTION
Layers the repository .env before the active app env file so shared build-time
variables such as PYTHON_VERSION remain available while app-specific values can
override database, port, and provider settings.

.PARAMETER EnvFile
Absolute or relative path to the active backend app environment file.

.RETURNS
String[]. Docker Compose CLI arguments containing one or more --env-file pairs.
#>
function Get-ComposeEnvFileArgs {
    param([string]$EnvFile)

    $args = @()
    $rootEnvFile = Join-Path $projectRoot ".env"
    $activeEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
        $EnvFile
    } else {
        Join-Path $projectRoot $EnvFile
    }

    if (Test-Path -LiteralPath $rootEnvFile -PathType Leaf) {
        $args += @("--env-file", $rootEnvFile)
    }

    if (-not [string]::IsNullOrWhiteSpace($activeEnvFile)) {
        $rootEnvFullPath = [System.IO.Path]::GetFullPath($rootEnvFile)
        $activeEnvFullPath = [System.IO.Path]::GetFullPath($activeEnvFile)
        if ($activeEnvFullPath -ne $rootEnvFullPath) {
            $args += @("--env-file", $activeEnvFile)
        }
    }

    return $args
}

function Get-ComposeProjectName {
    param([string]$AppId)

    $repoName = Split-Path $projectRoot -Leaf
    if ([string]::IsNullOrWhiteSpace($repoName)) {
        $repoName = "python-api-template"
    }

    $normalizedRepoName = $repoName.ToLower().Replace("_", "-")
    $normalizedAppId = $AppId.ToLower().Replace("_", "-")
    return "$normalizedRepoName-$normalizedAppId"
}

function Resolve-ComposeFilePath {
    param([string]$ComposeFile)

    if ([System.IO.Path]::IsPathRooted($ComposeFile)) {
        return $ComposeFile
    }

    return Join-Path $projectRoot $ComposeFile
}

function Update-DockerComposeContext {
    param(
        [string]$AppId,
        [string]$EnvFile
    )

    $env:ACTIVE_BACKEND_APP_ID = $AppId
    $env:ACTIVE_BACKEND_ENV_FILE = $EnvFile
    $env:DOCKER_COMPOSE_ENV_FILE = Join-Path $projectRoot $EnvFile
    $env:COMPOSE_PROJECT_NAME = Get-ComposeProjectName -AppId $AppId
    $env:APP_ENV_FILE = Join-Path $projectRoot $EnvFile
    $env:PDM_MANAGER_PROJECT_ROOT = Resolve-BackendDependencyProjectRoot -AppId $AppId
    $env:ACTIVE_BACKEND_DEPLOYMENT_ROOT = Resolve-BackendDeploymentRoot -AppId $AppId
    $env:ACTIVE_BACKEND_COMPOSE_MANIFEST = Resolve-BackendComposeManifest -AppId $AppId -DbMode ""
    $env:ACTIVE_BACKEND_COMPOSE_FILES = ""
    $env:ACTIVE_BACKEND_PRIMARY_COMPOSE_FILE = ""
    $env:ACTIVE_BACKEND_BROWSER_TARGETS = ""
}

function Get-BackendBrowserTargets {
    param(
        [string]$EnvFile,
        [string]$DbType,
        [string]$DbMode
    )

    if ($DbMode -ne "local") {
        return @()
    }

    switch ($DbType) {
        "postgresql" {
            $pgAdminPort = Get-EnvVariable -VariableName "PGADMIN_PORT" -EnvFile $EnvFile -DefaultValue "5050"
            $env:PGADMIN_EMAIL = Get-EnvVariable -VariableName "PGADMIN_EMAIL" -EnvFile $EnvFile -DefaultValue "admin@local.dev"
            $env:PGADMIN_PASSWORD = Get-EnvVariable -VariableName "PGADMIN_PASSWORD" -EnvFile $EnvFile -DefaultValue "admin"
            return @([PSCustomObject]@{ Label = "pgAdmin"; Url = "http://localhost:$pgAdminPort" })
        }
        "postgres" {
            $pgAdminPort = Get-EnvVariable -VariableName "PGADMIN_PORT" -EnvFile $EnvFile -DefaultValue "5050"
            $env:PGADMIN_EMAIL = Get-EnvVariable -VariableName "PGADMIN_EMAIL" -EnvFile $EnvFile -DefaultValue "admin@local.dev"
            $env:PGADMIN_PASSWORD = Get-EnvVariable -VariableName "PGADMIN_PASSWORD" -EnvFile $EnvFile -DefaultValue "admin"
            return @([PSCustomObject]@{ Label = "pgAdmin"; Url = "http://localhost:$pgAdminPort" })
        }
        "mongodb" {
            $mongoExpressPort = Get-EnvVariable -VariableName "MONGO_EXPRESS_PORT" -EnvFile $EnvFile -DefaultValue "8081"
            $env:MONGO_EXPRESS_USERNAME = Get-EnvVariable -VariableName "MONGO_EXPRESS_USERNAME" -EnvFile $EnvFile -DefaultValue "admin"
            $env:MONGO_EXPRESS_PASSWORD = Get-EnvVariable -VariableName "MONGO_EXPRESS_PASSWORD" -EnvFile $EnvFile -DefaultValue "admin"
            return @([PSCustomObject]@{ Label = "Mongo Express"; Url = "http://localhost:$mongoExpressPort" })
        }
        "mongo" {
            $mongoExpressPort = Get-EnvVariable -VariableName "MONGO_EXPRESS_PORT" -EnvFile $EnvFile -DefaultValue "8081"
            $env:MONGO_EXPRESS_USERNAME = Get-EnvVariable -VariableName "MONGO_EXPRESS_USERNAME" -EnvFile $EnvFile -DefaultValue "admin"
            $env:MONGO_EXPRESS_PASSWORD = Get-EnvVariable -VariableName "MONGO_EXPRESS_PASSWORD" -EnvFile $EnvFile -DefaultValue "admin"
            return @([PSCustomObject]@{ Label = "Mongo Express"; Url = "http://localhost:$mongoExpressPort" })
        }
        default {
            return @()
        }
    }
}

function Resolve-BackendComposeFiles {
    param(
        [string]$AppId,
        [string]$DbType,
        [string]$DbMode
    )

    $composeManifest = Resolve-BackendComposeManifest -AppId $AppId -DbMode $DbMode
    if (-not [string]::IsNullOrWhiteSpace($composeManifest) -and (Test-Path $composeManifest -PathType Leaf)) {
        $resolvedFiles = @()
        foreach ($manifestLine in Get-Content $composeManifest) {
            $trimmedLine = $manifestLine.Trim()
            if ([string]::IsNullOrWhiteSpace($trimmedLine)) {
                continue
            }

            if ($trimmedLine.StartsWith("#")) {
                continue
            }

            $resolvedFiles += Resolve-ComposeFilePath -ComposeFile $trimmedLine
        }

        if ($resolvedFiles.Count -gt 0) {
            return $resolvedFiles
        }
    }

    return @(Resolve-ComposeFilePath -ComposeFile (Get-ComposeFile -DbType $DbType -DbMode $DbMode))
}

function Resolve-PrimaryComposeFile {
    param([string[]]$ComposeFiles)

    if ($null -eq $ComposeFiles -or $ComposeFiles.Count -eq 0) {
        return ""
    }

    return $ComposeFiles[0]
}

function Show-ComposeFileStack {
    param([string[]]$ComposeFiles)

    foreach ($composeFile in $ComposeFiles) {
        if (-not [string]::IsNullOrWhiteSpace($composeFile)) {
            Write-Host "   Using: $composeFile" -ForegroundColor Gray
        }
    }
}

function Invoke-BackendComposeStack {
    param(
        [string]$EnvFile,
        [string[]]$ComposeFiles,
        [string[]]$CommandArgs
    )

    $composeArgs = @("compose") + (Get-ComposeEnvFileArgs -EnvFile $EnvFile)
    foreach ($composeFile in $ComposeFiles) {
        if (-not [string]::IsNullOrWhiteSpace($composeFile)) {
            $composeArgs += @("-f", $composeFile)
        }
    }

    $composeArgs += $CommandArgs
    & docker @composeArgs
}

function Get-BackendAppRelativePath {
    param([string]$AppId)

    return $AppId
}

function Set-ActiveBackendApp {
    param([string]$AppId)

    $script:activeBackendAppId = $AppId
    $script:activeBackendEnvFile = Resolve-BackendEnvFile -AppId $AppId
    Set-Content -Path $activeBackendAppStateFile -Value $AppId -Encoding utf8
    Update-DockerComposeContext -AppId $script:activeBackendAppId -EnvFile $script:activeBackendEnvFile
}

function Select-ActiveBackendApp {
    param([string]$CurrentApp)

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Select Active Backend App" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    # Built-in apps
    $builtinApps = @("demo_app", "template_app", "mongodb_template", "postgres_template")

    # Discover custom apps (exclude __pycache__ and other system folders)
    $customApps = @()
    $appsDir = Join-Path $projectRoot 'app\apps'
    $excludedFolders = @('__pycache__', '.git', '.vscode', 'node_modules')
    if (Test-Path -LiteralPath $appsDir -ErrorAction SilentlyContinue) {
        $allDirs = Get-ChildItem -Path $appsDir -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
        $customApps = $allDirs | Where-Object { $_ -notin $builtinApps -and $_ -notin $excludedFolders }
    }

    # Combine all apps
    $allApps = $builtinApps + $customApps

    # Find current app index for default choice
    $defaultChoice = "1"
    for ($i = 0; $i -lt $allApps.Count; $i++) {
        if ($allApps[$i] -eq $CurrentApp) {
            $defaultChoice = [string]($i + 1)
            break
        }
    }

    # Display numbered list
    $menuItems = @()
    for ($i = 0; $i -lt $allApps.Count; $i++) {
        $appId = $allApps[$i]
        $displayNum = $i + 1
        $displayName = $appId

        # Try to get display name from definition.py
        $definitionPath = Join-Path (Join-Path $appsDir $appId) 'definition.py'
        if (Test-Path -LiteralPath $definitionPath -ErrorAction SilentlyContinue) {
            $content = Get-Content -LiteralPath $definitionPath -Raw -ErrorAction SilentlyContinue
            if ($content -match '(?:display_name|name)="([^"]+)"') {
                $displayName = "$appId ($($matches[1]))"
            }
        }

        if ($appId -eq $CurrentApp) {
            Write-Host ("  {0}) {1} (current)" -f $displayNum, $displayName)
        } else {
            Write-Host ("  {0}) {1}" -f $displayNum, $displayName)
        }
        $menuItems += $appId
    }

    Write-Host ""
    Write-Host "  n/c) Create New Backend App"
    Write-Host "  r/d) Remove a Backend App"
    Write-Host ""

    $validChoices = @("n", "c", "r", "d", "")
    for ($i = 1; $i -le $allApps.Count; $i++) {
        $validChoices += [string]$i
    }

    $choice = $null
    do {
        $choice = Read-Host ("Select backend app (1-$($allApps.Count), n/c, r/d) [default: $defaultChoice] [$defaultChoice]")
        if ([string]::IsNullOrWhiteSpace($choice)) {
            $choice = $defaultChoice
            break
        }
        if ($choice -notin $validChoices) {
            Write-Host "Invalid option '$choice'. Please try again." -ForegroundColor Red
            $choice = $null
        }
    } while (-not $choice)

    # Handle numeric choice
    $numChoice = 0
    if ([int]::TryParse($choice, [ref]$numChoice)) {
        if ($numChoice -ge 1 -and $numChoice -le $allApps.Count) {
            Set-ActiveBackendApp -AppId $menuItems[$numChoice - 1]
            return
        }
    }

    switch ($choice) {
        { $_ -in "n", "c" } {
            $newAppId = New-BackendApp
            if ($newAppId) {
                Set-ActiveBackendApp -AppId $newAppId
            } else {
                Select-ActiveBackendApp -CurrentApp $CurrentApp
            }
        }
        { $_ -in "r", "d" } {
            Remove-BackendApp
            Select-ActiveBackendApp -CurrentApp $CurrentApp
        }
        default { Set-ActiveBackendApp -AppId $CurrentApp }
    }
}

function New-BackendApp {
    """
    Create a new backend app from template with user-provided configuration.
    Asks for: display name, description, database type, uses default ports.
    """
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Create New Backend App" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    $displayName = Read-Host "Enter app display name (e.g., 'My New API')"
    if ([string]::IsNullOrWhiteSpace($displayName)) {
        Write-Host "App display name is required. Cancelled." -ForegroundColor Yellow
        return $null
    }

    # Sanitize app name for folder (lowercase, replace spaces/whitespace with underscores)
    $appId = $displayName.ToLower() -replace '\s+', '_' -replace '-', '_'

    $appDescription = Read-Host "Enter app description"
    if ([string]::IsNullOrWhiteSpace($appDescription)) {
        $appDescription = "Auto-generated backend app."
    }

    Write-Host ""
    Write-Host "Select database type:"
    Write-Host "  1) PostgreSQL"
    Write-Host "  2) MongoDB"
    $dbChoice = Read-Host "Database type (1-2) [default: 1]"

    switch ($dbChoice) {
        "2" { $dbType = "mongodb"; $sourceApp = "mongodb_template" }
        default { $dbType = "postgresql"; $sourceApp = "postgres_template" }
    }
    $composeDbType = if ($dbType -eq "postgresql") { "postgres" } else { $dbType }

    Write-Host ""
    Write-Host "Creating app: $appId ($dbType)..." -ForegroundColor Green

    $appDir = Join-Path (Join-Path $projectRoot 'app\apps') $appId
    if (Test-Path -LiteralPath $appDir -ErrorAction SilentlyContinue) {
        Write-Host "App directory already exists: $appDir" -ForegroundColor Red
        return $null
    }

    # Create directory structure
    New-Item -ItemType Directory -Path (Join-Path $appDir 'routes') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $appDir 'schemas') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $appDir 'services') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $appDir 'config') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $appDir "env") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $appDir "deployment") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path (Join-Path $projectRoot ".docker\apps") $appId) -Force | Out-Null

    # Copy pyproject.toml and pdm.lock from source template
    $sourceDir = Join-Path (Join-Path $projectRoot "app\apps") $sourceApp
    Copy-Item (Join-Path $sourceDir "pyproject.toml") (Join-Path $appDir "pyproject.toml")
    Copy-Item (Join-Path $sourceDir "pdm.lock") (Join-Path $appDir "pdm.lock")

    # Initialize committed package metadata for the generated app.
    $newPyprojectPath = Join-Path $appDir "pyproject.toml"
    $newPyprojectLines = Get-Content -LiteralPath $newPyprojectPath
    $newPyprojectLines = $newPyprojectLines | ForEach-Object {
        if ($_ -match '^name\s*=') {
            "name = `"$appId`""
        } elseif ($_ -match '^version\s*=') {
            'version = "0.1.0"'
        } else {
            $_
        }
    }
    Set-Content -LiteralPath $newPyprojectPath -Value $newPyprojectLines -Encoding utf8

    # Create definition.py
    $definitionContent = @"
"""
${displayName} backend definition.

This dynamically created app currently exposes only the shared core API
routers. App-specific routers can be added later by creating route modules and
registering them in route_registrations.
"""
from __future__ import annotations

from apps.contracts import BackendAppDefinition

BACKEND_APP_DEFINITION = BackendAppDefinition(
    app_id="${appId}",
    display_name="${displayName}",
    backend_data_profile="${dbType}",
    route_registrations=(),
    exposes_sync_routes=False,
)
"@
    Set-Content -Path (Join-Path $appDir "definition.py") -Value $definitionContent

    # Create __init__.py
    Set-Content -Path (Join-Path $appDir "__init__.py") -Value '"""Backend app package created by quick-start."""'

    # Create routes/__init__.py
    Set-Content -Path (Join-Path (Join-Path $appDir "routes") "__init__.py") -Value '"""Route modules for the generated backend app."""'

    # Create compose-files.txt
    $composeFilesContent = @"
local-deployment/base/api.compose.yml
local-deployment/base/redis.compose.yml
local-deployment/base/${composeDbType}.compose.yml
"@.Trim()
    Set-Content -Path (Join-Path (Join-Path $appDir "deployment") "compose-files.txt") -Value $composeFilesContent

    # Create compose.override.yml
    if ($dbType -eq "postgresql") {
        $overrideContent = @"
services:
  api:
    environment:
      APP_PROFILE: ${appId}
      BACKEND_APP_ID: ${appId}
    volumes:
      - ../../app/apps/${appId}:/app/apps/${appId}:ro
  postgres:
    volumes:
      - ../../.docker/apps/${appId}/postgres-data:/var/lib/postgresql/data
"@.Trim()
    } else {
        $overrideContent = @"
services:
  api:
    environment:
      APP_PROFILE: ${appId}
      BACKEND_APP_ID: ${appId}
    volumes:
      - ../../app/apps/${appId}:/app/apps/${appId}:ro
  mongodb:
    volumes:
      - ../../.docker/apps/${appId}/mongodb-data:/data/db
"@.Trim()
    }
    Set-Content -Path (Join-Path (Join-Path $appDir "deployment") "compose.override.yml") -Value $overrideContent

    # Create env file
    $envContent = @"
# ${displayName} Local Environment
# =============================================================================
# This file contains local runtime settings for the ${appId} backend app. It is
# ignored by git because it may contain credentials, local ports, and
# developer-specific service URLs.
#
# Release image metadata is stored in:
#   app/apps/${appId}/pyproject.toml
# Do not add IMAGE_NAME or IMAGE_VERSION here.
# =============================================================================

# =============================================================================
# Python Runtime
# =============================================================================
PYTHON_VERSION=3.13

# =============================================================================
# Backend App Selection
# =============================================================================
APP_ENV_FILE=../app/apps/${appId}/env/.env.${appId}
APP_PROFILE=${appId}
BACKEND_APP_ID=${appId}
APP_NAME=${displayName}
APP_DESCRIPTION=${appDescription}

# =============================================================================
# Database Configuration
# =============================================================================
# DB_MODE=local starts a Docker database; DB_MODE=external uses your own host.
DB_TYPE=${dbType}
DB_MODE=local
"@

    if ($dbType -eq "postgresql") {
        $envContent += @"

# Local Docker PostgreSQL connection.
# Use the Docker service name "postgres" from containers, not localhost.
DATABASE_URL=postgresql://postgres:postgres@postgres:5435/apidb
DB_HOST=postgres
DB_NAME=apidb
DB_USER=postgres
DB_PASSWORD=postgres
DB_PORT=5435

# =============================================================================
# API and Redis Ports
# =============================================================================
PORT=8086
REDIS_URL=redis://redis:6379
REDIS_PORT=6385

# =============================================================================
# PostgreSQL Admin UI
# =============================================================================
PGADMIN_PORT=5055
PGADMIN_EMAIL=admin@local.dev
PGADMIN_PASSWORD=admin
"@
    } else {
        $envContent += @"

# Local Docker MongoDB connection.
# Use the Docker service name "mongodb" from containers, not localhost.
MONGODB_URL=mongodb://mongo:mongo@mongodb:27017/?authSource=admin
MONGODB_DB_NAME=apidb
MONGODB_ROOT_USER=mongo
MONGODB_ROOT_PASSWORD=mongo
MONGODB_PORT=27021

# =============================================================================
# API and Redis Ports
# =============================================================================
PORT=8087
REDIS_URL=redis://redis:6379
REDIS_PORT=6386

# =============================================================================
# Mongo Express Admin UI
# =============================================================================
MONGO_EXPRESS_PORT=8088
MONGO_EXPRESS_USERNAME=admin
MONGO_EXPRESS_PASSWORD=admin
"@
    }

    $envContent += @"

# =============================================================================
# Debug and Request Logging
# =============================================================================
# Keep body/header logging disabled unless you are actively debugging because
# request data can contain credentials or personal information.
DEBUG=true
ENABLE_HTTP_DEBUG_LOGGING=false
LOG_REQUEST_HEADERS=false
LOG_REQUEST_BODY=false
LOG_RESPONSE_HEADERS=false
LOG_RESPONSE_BODY=false
DB_LOCK_FAIL_CLOSED=true
"@

    Set-Content -Path (Join-Path (Join-Path $appDir "env") ".env.${appId}") -Value $envContent

    Write-Host "Created: $appDir" -ForegroundColor Green
    Write-Host "App '$appId' created successfully!" -ForegroundColor Green
    Write-Host ""

    return $appId
}

function Remove-BackendApp {
    <#
    .SYNOPSIS
        Remove a custom backend app with confirmation.
    #>
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  Remove Backend App" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "WARNING: This will permanently delete the app and all its data." -ForegroundColor Yellow
    Write-Host ""

    # Get list of custom apps (exclude built-in templates and system folders)
    $appsDir = Join-Path $projectRoot "app\apps"
    $allApps = @(Get-ChildItem -Path $appsDir -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    $builtinApps = @("demo_app", "template_app", "mongodb_template", "postgres_template")
    $excludedFolders = @('__pycache__', '.git', '.vscode', 'node_modules')
    $customApps = @($allApps | Where-Object { $_ -notin $builtinApps -and $_ -notin $excludedFolders })

    if ($customApps.Count -eq 0) {
        Write-Host "No custom apps found to remove." -ForegroundColor Yellow
        return
    }

    Write-Host "Select app to remove:"
    for ($i = 0; $i -lt $customApps.Count; $i++) {
        $appName = $customApps[$i]
        $num = $i + 1
        Write-Host "  ${num}) ${appName}"
    }
    Write-Host "  c) Cancel"
    Write-Host ""

    $choice = Read-Host "Select app to remove (1-$($customApps.Count), c)"
    if ($choice -eq "c" -or [string]::IsNullOrWhiteSpace($choice)) {
        Write-Host "Cancelled." -ForegroundColor Yellow
        return
    }

    $idx = [int]$choice - 1
    if ($idx -lt 0 -or $idx -ge $customApps.Count) {
        Write-Host "Invalid selection. Cancelled." -ForegroundColor Red
        return
    }

    $targetApp = $customApps[$idx]

    # Get display name from definition.py if possible
    $displayName = $targetApp
    $definitionPath = Join-Path (Join-Path $appsDir $targetApp) "definition.py"
    if (Test-Path $definitionPath) {
        $content = Get-Content $definitionPath -Raw
        if ($content -match '(?:display_name|name)="([^"]+)"') {
            $displayName = $matches[1]
        }
    }

    Write-Host ""
    Write-Host "You are about to DELETE: $displayName ($targetApp)" -ForegroundColor Red
    Write-Host ""
    Write-Host "To confirm, type: DELETE $displayName" -ForegroundColor Yellow
    Write-Host ""
    $confirmation = Read-Host "Confirmation"

    if ($confirmation -ne "DELETE $displayName") {
        Write-Host "Confirmation failed. Deletion cancelled." -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "Removing $targetApp..." -ForegroundColor Red

    # Stop any running containers for this app
    $composeFile = Join-Path $projectRoot ".docker\apps\$targetApp\compose.yml"
    if (Test-Path $composeFile) {
        docker compose -f $composeFile down --volumes 2>$null
    }

    # Remove app directory
    $appDir = Join-Path $appsDir $targetApp
    if (Test-Path $appDir) {
        Remove-Item -Path $appDir -Recurse -Force
    }

    # Remove docker data directory
    $dockerDir = Join-Path $projectRoot ".docker\apps\$targetApp"
    if (Test-Path $dockerDir) {
        Remove-Item -Path $dockerDir -Recurse -Force
    }

    Write-Host "App '$targetApp' has been removed." -ForegroundColor Green
}

function Initialize-ActiveBackendAppSelection {
    $savedApp = "demo_app"
    if (Test-Path -LiteralPath $activeBackendAppStateFile -ErrorAction SilentlyContinue) {
        $savedApp = (Get-Content -LiteralPath $activeBackendAppStateFile -Raw).Trim()
    }

    # Sanitize the saved app ID to prevent path errors
    $savedApp = $savedApp -replace '[\/:?"<>|]', '_'

    if ($savedApp -ne "demo_app" -and $savedApp -ne "template_app" -and $savedApp -ne "mongodb_template" -and $savedApp -ne "postgres_template") {
        # It's a custom app, verify it exists
        $customAppDir = Join-Path (Join-Path $projectRoot 'app\apps') $savedApp
        if (-not (Test-Path -LiteralPath $customAppDir -ErrorAction SilentlyContinue)) {
            $savedApp = "demo_app"
        }
    }

    Select-ActiveBackendApp -CurrentApp $savedApp
}

function Read-ApiPortSelection {
    param([string]$EnvFile)

    return Read-EnvPortSelection -EnvFile $EnvFile -VariableName "PORT" -PromptLabel "API port" -DefaultValue "8000"
}

function Resolve-MonitoringUiPortVariableName {
    param([string]$DbType)

    switch ($DbType) {
        "postgresql" { return "PGADMIN_PORT" }
        "postgres" { return "PGADMIN_PORT" }
        "mongodb" { return "MONGO_EXPRESS_PORT" }
        "mongo" { return "MONGO_EXPRESS_PORT" }
        default { return "" }
    }
}

function Resolve-MonitoringUiPortPromptLabel {
    param([string]$DbType)

    switch ($DbType) {
        "postgresql" { return "pgAdmin port" }
        "postgres" { return "pgAdmin port" }
        "mongodb" { return "Mongo Express port" }
        "mongo" { return "Mongo Express port" }
        default { return "Monitoring UI port" }
    }
}

function Resolve-MonitoringUiPortDefaultValue {
    param([string]$DbType)

    switch ($DbType) {
        "postgresql" { return "5050" }
        "postgres" { return "5050" }
        "mongodb" { return "8081" }
        "mongo" { return "8081" }
        default { return "" }
    }
}

function Resolve-DatabasePortVariableName {
    param([string]$DbType)

    switch ($DbType) {
        "neo4j" { return "DB_PORT" }
        "postgresql" { return "DB_PORT" }
        "postgres" { return "DB_PORT" }
        "mysql" { return "DB_PORT" }
        "sqlite" { return "DB_PORT" }
        "mongodb" { return "MONGODB_PORT" }
        "mongo" { return "MONGODB_PORT" }
        default { return "" }
    }
}

function Resolve-DatabasePortPromptLabel {
    param([string]$DbType)

    switch ($DbType) {
        "neo4j" { return "Neo4j Bolt port" }
        "postgresql" { return "PostgreSQL port" }
        "postgres" { return "PostgreSQL port" }
        "mongodb" { return "MongoDB port" }
        "mongo" { return "MongoDB port" }
        default { return "Database port" }
    }
}

function Resolve-DatabasePortDefaultValue {
    param([string]$DbType)

    switch ($DbType) {
        "neo4j" { return "7687" }
        "postgresql" { return "5433" }
        "postgres" { return "5433" }
        "mysql" { return "5433" }
        "sqlite" { return "5433" }
        "mongodb" { return "27017" }
        "mongo" { return "27017" }
        default { return "5433" }
    }
}

function Read-EnvPortSelection {
    param(
        [string]$EnvFile,
        [string]$VariableName,
        [string]$PromptLabel,
        [string]$DefaultValue
    )

    $defaultPort = Get-EnvVariable -VariableName $VariableName -EnvFile $EnvFile -DefaultValue $DefaultValue

    while ($true) {
        $rawPort = Read-Host "$PromptLabel [$defaultPort]"
        if ([string]::IsNullOrWhiteSpace($rawPort)) {
            $rawPort = $defaultPort
        }

        $selectedPort = 0
        if ([int]::TryParse($rawPort, [ref]$selectedPort) -and $selectedPort -ge 1 -and $selectedPort -le 65535) {
            Update-EnvVariable -VariableName $VariableName -VariableValue "$selectedPort" -EnvFile $EnvFile
            return "$selectedPort"
        }

        Write-Host "Invalid port '$rawPort'. Please enter a number between 1 and 65535." -ForegroundColor Red
    }
}

function Sync-LocalDatabaseConnectionSettings {
    param(
        [string]$EnvFile,
        [string]$DbType,
        [string]$DbMode,
        [string]$SelectedPort
    )

    if ($DbMode -ne "local" -or [string]::IsNullOrWhiteSpace($SelectedPort)) {
        return
    }

    switch ($DbType) {
        "postgresql" {
            $dbHost = Get-EnvVariable -VariableName "DB_HOST" -EnvFile $EnvFile -DefaultValue "postgres"
            $dbName = Get-EnvVariable -VariableName "DB_NAME" -EnvFile $EnvFile -DefaultValue "apidb"
            $dbUser = Get-EnvVariable -VariableName "DB_USER" -EnvFile $EnvFile -DefaultValue "postgres"
            $dbPassword = Get-EnvVariable -VariableName "DB_PASSWORD" -EnvFile $EnvFile -DefaultValue "postgres"
            Update-EnvVariable -VariableName "DATABASE_URL" -VariableValue "postgresql://${dbUser}:${dbPassword}@${dbHost}:${SelectedPort}/${dbName}" -EnvFile $EnvFile
        }
        "postgres" {
            $dbHost = Get-EnvVariable -VariableName "DB_HOST" -EnvFile $EnvFile -DefaultValue "postgres"
            $dbName = Get-EnvVariable -VariableName "DB_NAME" -EnvFile $EnvFile -DefaultValue "apidb"
            $dbUser = Get-EnvVariable -VariableName "DB_USER" -EnvFile $EnvFile -DefaultValue "postgres"
            $dbPassword = Get-EnvVariable -VariableName "DB_PASSWORD" -EnvFile $EnvFile -DefaultValue "postgres"
            Update-EnvVariable -VariableName "DATABASE_URL" -VariableValue "postgresql://${dbUser}:${dbPassword}@${dbHost}:${SelectedPort}/${dbName}" -EnvFile $EnvFile
        }
        "neo4j" {
            $dbHost = Get-EnvVariable -VariableName "DB_HOST" -EnvFile $EnvFile -DefaultValue "neo4j"
            Update-EnvVariable -VariableName "NEO4J_URL" -VariableValue "bolt://${dbHost}:${SelectedPort}" -EnvFile $EnvFile
        }
    }
}

function Configure-ServicePorts {
    param(
        [string]$EnvFile,
        [string]$DbType,
        [string]$DbMode
    )

    $script:selectedDatabasePortVariable = ""
    $script:selectedDatabasePort = ""
    $script:selectedRedisPort = ""

    # Skip database port prompts if app doesn't need a database
    $requiresDatabase = ($DbType -ne "none" -and $DbType -ne "external")
    
    if ($requiresDatabase -and $DbMode -eq "local") {
        $databasePortVariable = Resolve-DatabasePortVariableName -DbType $DbType
        if (-not [string]::IsNullOrWhiteSpace($databasePortVariable)) {
            $databasePortLabel = Resolve-DatabasePortPromptLabel -DbType $DbType
            $databasePortDefault = Resolve-DatabasePortDefaultValue -DbType $DbType
            $script:selectedDatabasePortVariable = $databasePortVariable
            $script:selectedDatabasePort = Read-EnvPortSelection -EnvFile $EnvFile -VariableName $databasePortVariable -PromptLabel $databasePortLabel -DefaultValue $databasePortDefault
            Sync-LocalDatabaseConnectionSettings -EnvFile $EnvFile -DbType $DbType -DbMode $DbMode -SelectedPort $script:selectedDatabasePort
        }
    }

    # Skip Redis port if no database needed
    if ($requiresDatabase) {
        $script:selectedRedisPort = Read-EnvPortSelection -EnvFile $EnvFile -VariableName "REDIS_PORT" -PromptLabel "Redis port" -DefaultValue "6379"
    }

    # Prompt for monitoring UI port (pgAdmin for PostgreSQL, Mongo Express for MongoDB)
    $script:selectedMonitoringUiPortVariable = ""
    $script:selectedMonitoringUiPort = ""
    if ($requiresDatabase -and $DbMode -eq "local") {
        $monitoringPortVariable = Resolve-MonitoringUiPortVariableName -DbType $DbType
        if (-not [string]::IsNullOrWhiteSpace($monitoringPortVariable)) {
            $monitoringPortLabel = Resolve-MonitoringUiPortPromptLabel -DbType $DbType
            $monitoringPortDefault = Resolve-MonitoringUiPortDefaultValue -DbType $DbType
            $script:selectedMonitoringUiPortVariable = $monitoringPortVariable
            $script:selectedMonitoringUiPort = Read-EnvPortSelection -EnvFile $EnvFile -VariableName $monitoringPortVariable -PromptLabel $monitoringPortLabel -DefaultValue $monitoringPortDefault
        }
    }
}

# Check Docker availability
if (-not (Test-DockerInstallation)) {
    exit 1
}
Write-Host ""

# Check if initial setup is needed
if (-not (Test-Path .setup-complete)) {
    $existingEnvBeforePrompt = Test-Path .env
    Write-Host " First-time setup detected!" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This appears to be your first time running this project." -ForegroundColor Yellow
    Write-Host "Would you like to run the interactive setup wizard?" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The setup wizard will help you configure:" -ForegroundColor Gray
    Write-Host "  - Docker image name and version" -ForegroundColor Gray
    Write-Host "  - Python version" -ForegroundColor Gray
    Write-Host "  - Database type (PostgreSQL, Neo4j, or MongoDB)" -ForegroundColor Gray
    Write-Host "  - Database mode (local or external)" -ForegroundColor Gray
    Write-Host "  - API configuration" -ForegroundColor Gray
    Write-Host ""
    
    $runSetup = Read-Host "Run full interactive setup wizard in Docker? (y/N)"
    if ($runSetup -match "^[Yy]$") {
        Write-Host ""
        Write-Host "Starting setup wizard..." -ForegroundColor Cyan
        docker compose -f setup/docker-compose.setup.yml run --rm setup
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Setup wizard failed inside Docker (exit code: $LASTEXITCODE)." -ForegroundColor Red
            Write-Host "You can still continue with a simple setup using the .env template." -ForegroundColor Yellow
            $fallback = Read-Host "Create basic .env from template instead and continue? (Y/n)"
            if ($fallback -eq "n" -or $fallback -eq "N") {
                Write-Host "Setup aborted. Please inspect the setup container logs and fix the issues." -ForegroundColor Red
                exit 1
            }
            Write-Host ""
            Write-Host "Creating basic .env from template..." -ForegroundColor Yellow
            if (Test-Path setup\.env.template) {
                Copy-Item setup\.env.template .env
                Write-Host ".env file created from template." -ForegroundColor Green
                Write-Host "  Please edit .env to configure your environment before continuing." -ForegroundColor Yellow
                if (Get-Command Invoke-CognitoSetup -ErrorAction SilentlyContinue) {
                    Invoke-CognitoSetup
                    Write-Host "" -ForegroundColor Gray
                }
            } else {
                Write-Host "[ERROR] setup\.env.template not found!" -ForegroundColor Red
                exit 1
            }
        } else {
            Write-Host ""
            if (Get-Command Invoke-CognitoSetup -ErrorAction SilentlyContinue) {
                Invoke-CognitoSetup
                Write-Host "" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host ""
        if ($existingEnvBeforePrompt) {
            Write-Host "Skipping setup wizard. Existing .env detected, keeping current values." -ForegroundColor Yellow
        } else {
            Write-Host "Skipping setup wizard. Creating basic .env from template..." -ForegroundColor Yellow
            if (Test-Path setup\.env.template) {
                Copy-Item setup\.env.template .env -Force
                Write-Host ".env file created from template." -ForegroundColor Green
                Write-Host "  Please edit .env to configure your environment before continuing." -ForegroundColor Yellow

                $editor = $env:EDITOR
                if ([string]::IsNullOrWhiteSpace($editor)) { $editor = "notepad" }
                $openNow = Read-Host "Open .env now in $editor? (Y/n)"
                if ($openNow -notmatch "^[Nn]$") {
                    & $editor ".env"
                }
            } else {
                Write-Host "[ERROR] setup\.env.template not found!" -ForegroundColor Red
                exit 1
            }
        }

        if ($existingEnvBeforePrompt) {
            $recreateSetupFlag = Read-Host "Detected .env existed before prompt. Re-create .setup-complete now and skip the wizard? (y/N)"
            if ($recreateSetupFlag -match "^[Yy]$") {
                New-Item -ItemType File -Path .setup-complete -Force | Out-Null
                Write-Host ".setup-complete recreated from existing .env." -ForegroundColor Green
            }
        }

        if (Get-Command Invoke-CognitoSetup -ErrorAction SilentlyContinue) {
            Invoke-CognitoSetup
            Write-Host "" -ForegroundColor Gray
        }
    }
    Write-Host ""
} elseif (-not (Test-Path .env)) {
    # Setup complete but .env missing - recreate from template
    Write-Host " .env file missing. Creating from template..." -ForegroundColor Yellow
    if (Test-Path setup\.env.template) {
        Copy-Item setup\.env.template .env
        Write-Host ".env file created from template." -ForegroundColor Green
        Write-Host "Please check the values in .env if needed." -ForegroundColor Yellow
        if (Get-Command Invoke-CognitoSetup -ErrorAction SilentlyContinue) {
            Invoke-CognitoSetup
            Write-Host "" -ForegroundColor Gray
        }
    } else {
        Write-Host "[ERROR] setup\.env.template not found!" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

Initialize-ActiveBackendAppSelection

Write-Host ("Active backend app: {0}" -f (Get-BackendAppRelativePath -AppId $script:activeBackendAppId)) -ForegroundColor Gray
Write-Host ("Using env file: {0}" -f $script:activeBackendEnvFile) -ForegroundColor Gray
Write-Host ""

# Read API port from .env (default: 8000)
$PORT = Read-ApiPortSelection -EnvFile $script:activeBackendEnvFile
Write-Host ("API will use port: {0}" -f $PORT) -ForegroundColor Gray
Write-Host ""

# Read database configuration from .env
$DB_TYPE = Get-EnvVariable -VariableName "DB_TYPE" -EnvFile $script:activeBackendEnvFile -DefaultValue "neo4j"
$DB_MODE = Get-EnvVariable -VariableName "DB_MODE" -EnvFile $script:activeBackendEnvFile -DefaultValue "local"
$DB_TYPE = $DB_TYPE.ToLower().Trim()
$DB_MODE = $DB_MODE.ToLower().Trim()

Configure-ServicePorts -EnvFile $script:activeBackendEnvFile -DbType $DB_TYPE -DbMode $DB_MODE
if (-not [string]::IsNullOrWhiteSpace($script:selectedDatabasePort)) {
    Write-Host (("{0} will use port: {1}") -f (Resolve-DatabasePortPromptLabel -DbType $DB_TYPE), $script:selectedDatabasePort) -ForegroundColor Gray
}
if (-not [string]::IsNullOrWhiteSpace($script:selectedRedisPort)) {
    Write-Host (("Redis will use port: {0}") -f $script:selectedRedisPort) -ForegroundColor Gray
}
if (-not [string]::IsNullOrWhiteSpace($script:selectedMonitoringUiPort)) {
    Write-Host (("{0} will use port: {1}") -f (Resolve-MonitoringUiPortPromptLabel -DbType $DB_TYPE), $script:selectedMonitoringUiPort) -ForegroundColor Gray
}
Write-Host ""

# Determine Docker Compose file based on DB_TYPE and DB_MODE
$composeFiles = Resolve-BackendComposeFiles -AppId $script:activeBackendAppId -DbType $DB_TYPE -DbMode $DB_MODE
$COMPOSE_FILE = Resolve-PrimaryComposeFile -ComposeFiles $composeFiles
$env:ACTIVE_BACKEND_COMPOSE_MANIFEST = Resolve-BackendComposeManifest -AppId $script:activeBackendAppId -DbMode $DB_MODE
$env:ACTIVE_BACKEND_COMPOSE_FILES = ($composeFiles -join "`n")
$env:ACTIVE_BACKEND_PRIMARY_COMPOSE_FILE = $COMPOSE_FILE
$browserTargets = Get-BackendBrowserTargets -EnvFile $script:activeBackendEnvFile -DbType $DB_TYPE -DbMode $DB_MODE
$env:ACTIVE_BACKEND_BROWSER_TARGETS = (($browserTargets | ForEach-Object { "{0}|{1}" -f $_.Label, $_.Url }) -join "`n")

if ($DB_MODE -eq "external") {
    Write-Host "Detected external database mode" -ForegroundColor Cyan
    Write-Host "   Database Type: $DB_TYPE" -ForegroundColor Gray
    Write-Host "   Will connect to external database (no local DB container)" -ForegroundColor Gray
} elseif ($DB_TYPE -eq "neo4j") {
    Write-Host "Detected local Neo4j database" -ForegroundColor Cyan
    Write-Host "   Will start Neo4j container" -ForegroundColor Gray
} elseif ($DB_TYPE -eq "postgresql" -or $DB_TYPE -eq "postgres") {
    Write-Host "Detected local $DB_TYPE database" -ForegroundColor Cyan
    Write-Host "   Will start PostgreSQL container" -ForegroundColor Gray
} elseif ($DB_TYPE -eq "mysql" -or $DB_TYPE -eq "sqlite") {
    Write-Host "Detected DB_TYPE=$DB_TYPE (legacy compatibility mode)" -ForegroundColor Yellow
    Write-Host "   Official stability matrix is: postgresql, neo4j, mongodb" -ForegroundColor Yellow
    Write-Host "   Compose will use PostgreSQL profile for local development" -ForegroundColor Gray
} elseif ($DB_TYPE -eq "mongodb" -or $DB_TYPE -eq "mongo") {
    Write-Host "Detected local MongoDB database" -ForegroundColor Cyan
    Write-Host "   Will start MongoDB container" -ForegroundColor Gray
} else {
    Write-Host "Unknown DB_TYPE: $DB_TYPE, using default compose file" -ForegroundColor Yellow
}

Show-ComposeFileStack -ComposeFiles $composeFiles
Write-Host ""

# Check if this is the first setup run
if (-not (Test-Path .setup-complete)) {
    Write-Host "First setup detected!" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Would you like to run optional diagnostics and dependency checks?" -ForegroundColor Yellow
    Write-Host "  This can take 1-2 minutes but helps validate your configuration." -ForegroundColor Gray
    Write-Host "  You can skip this and dependencies will be installed during Docker build." -ForegroundColor Gray
    Write-Host ""
    
    $runDiagnostics = Read-Host "Run diagnostics and dependency checks? (y/N)"
    
    if ($runDiagnostics -match "^[Yy]$") {
        Write-Host ""
        Write-Host "Running diagnostics and dependency configuration..." -ForegroundColor Cyan
        Write-Host ""
        
        # Run diagnostics to validate Docker/build configuration first
        $diagnosticsScript = "run-docker-build-diagnostics.ps1"
        if (Test-Path $diagnosticsScript) {
            Write-Host "Running Docker/Build diagnostics..." -ForegroundColor Yellow
            Write-Host "Collecting diagnostic information..." -ForegroundColor Gray
            try {
                & .\$diagnosticsScript
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Diagnostics completed successfully" -ForegroundColor Green
                } else {
                    throw "Diagnostics reported issues"
                }
            } catch {
                Write-Host "Diagnostics reported issues with your Docker or build configuration!" -ForegroundColor Red
                Write-Host "Please address the reported problems before continuing." -ForegroundColor Yellow
                Write-Host ""
                Write-Host "Troubleshooting steps:" -ForegroundColor Yellow
                Write-Host "1. Ensure Docker Desktop/daemon is running" -ForegroundColor Gray
                Write-Host "2. Verify .env values (especially PYTHON_VERSION and DB settings)" -ForegroundColor Gray
                Write-Host "3. Review missing files noted in the diagnostics output" -ForegroundColor Gray
                Write-Host "4. Re-run manually via: .\$diagnosticsScript" -ForegroundColor Gray
                Write-Host "" -ForegroundColor Gray
                $continue = Read-Host "Continue anyway? (y/N)"
                if ($continue -notmatch "^[Yy]$") {
                    Write-Host "Setup aborted. Please fix the reported diagnostics issues first." -ForegroundColor Red
                    exit 1
                }
                Write-Host "Continuing with potentially broken configuration..." -ForegroundColor Yellow
            }
        } else {
            Write-Host "$diagnosticsScript not found - skipping diagnostics" -ForegroundColor Yellow
        }
        
        Write-Host ""
        
        # Run dependency management in initial-run mode
        if (Test-Path .\manage-python-project-dependencies.ps1) {
            Write-Host "Starting Dependency Management for initial setup..." -ForegroundColor Cyan
            try {
                & .\manage-python-project-dependencies.ps1 -InitialRun
            } catch {
                Write-Host "Error running dependency management: $_" -ForegroundColor Red
                Write-Host "Dependencies will be installed when Docker builds the container" -ForegroundColor Yellow
            }
        } else {
            Write-Host "manage-python-project-dependencies.ps1 not found - skipping" -ForegroundColor Yellow
            Write-Host "Dependencies will be installed when Docker builds the container" -ForegroundColor Yellow
        }
    } else {
        Write-Host ""
        Write-Host "Skipping diagnostics and dependency checks." -ForegroundColor Yellow
        Write-Host "Dependencies will be installed during Docker container build." -ForegroundColor Gray
    }

    # Mark setup as complete
    New-Item -ItemType File -Path .setup-complete -Force | Out-Null

    Write-Host ""
    Write-Host "First setup complete!" -ForegroundColor Green
    Write-Host "Starting backend now..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  API will be accessible at:" -ForegroundColor Cyan
    Write-Host "  http://localhost:$PORT/docs" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Press ENTER to open the API documentation in your browser..." -ForegroundColor Yellow
    Write-Host "(The API may take a few seconds to start. Please refresh the page if needed.)" -ForegroundColor Gray
    $null = Read-Host

    # Open browser in incognito/private mode
    Write-Host "Opening browser..." -ForegroundColor Cyan
    Start-Process "msedge" "--inprivate http://localhost:$PORT/docs" -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) {
        # Fallback to Chrome if Edge not available
        Start-Process "chrome" "--incognito http://localhost:$PORT/docs" -ErrorAction SilentlyContinue
        if ($LASTEXITCODE -ne 0) {
            # Fallback to default browser
            Start-Process "http://localhost:$PORT/docs"
        }
    }

    Write-Host ""
    # Check and generate app-specific lockfile if needed
    $appId = if ($env:BACKEND_APP_ID) { $env:BACKEND_APP_ID } else { "api" }
    $appLockfilePath = Join-Path $projectRoot "app\apps\$appId\pdm.lock"
    if (Test-Path $appLockfilePath) {
        $lockfileContent = Get-Content $appLockfilePath -Raw
        if ($lockfileContent -match "placeholder|PLACEHOLDER") {
            Write-Host "Generating dependencies for app '$appId'..." -ForegroundColor Yellow
            $pdmPath = Get-Command pdm -ErrorAction SilentlyContinue
            if ($pdmPath) {
                $appDir = Join-Path $projectRoot "app\apps\$appId"
                Push-Location $appDir
                try {
                    pdm lock 2>&1 | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        Write-Host "Lockfile generated successfully" -ForegroundColor Green
                    } else {
                        Write-Host "Warning: Failed to generate lockfile. Build may fail." -ForegroundColor Red
                    }
                } finally {
                    Pop-Location
                }
            } else {
                Write-Host "Warning: PDM not found. Cannot generate lockfile. Install PDM or run: pip install pdm" -ForegroundColor Red
            }
        }
    }

    $composeEnvFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } else { $script:activeBackendEnvFile }
    Invoke-BackendComposeStack -EnvFile $composeEnvFile -ComposeFiles $composeFiles -CommandArgs @("up", "--build", "--remove-orphans")
} else {
    Write-Host "Starting backend with Docker Compose..." -ForegroundColor Cyan
    Write-Host "Backend wird verfügbar sein auf: http://localhost:$PORT" -ForegroundColor Cyan
    Write-Host ""

    Show-MainMenu -Port $PORT -ComposeFile $COMPOSE_FILE
}
