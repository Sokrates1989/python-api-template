# menu_handlers.ps1
# PowerShell module for handling menu actions in quick-start script

# Source browser helpers for auto-open functionality
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BrowserHelpersPath = Join-Path $ScriptDir "browser_helpers.ps1"
if (Test-Path $BrowserHelpersPath) {
    . $BrowserHelpersPath
}

# Source auth provider module if available
$AuthProviderPath = Join-Path $ScriptDir "auth_provider.ps1"
if (Test-Path $AuthProviderPath) {
    . $AuthProviderPath
}

# Source Keycloak bootstrap utilities if available
$BootstrapUtilsPath = Join-Path $ScriptDir "bootstrap_utils.ps1"
if (Test-Path $BootstrapUtilsPath) {
    . $BootstrapUtilsPath
}

function Resolve-DependencyManagementProjectRoot {
    $configuredRoot = if ($env:PDM_MANAGER_PROJECT_ROOT) { $env:PDM_MANAGER_PROJECT_ROOT } else { "." }

    if ([System.IO.Path]::IsPathRooted($configuredRoot)) {
        return $configuredRoot
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $configuredRoot))
}

function Show-ActiveBackendContext {
    param(
        [string]$ComposeFile
    )

    $appId = if ($env:ACTIVE_BACKEND_APP_ID) { $env:ACTIVE_BACKEND_APP_ID } else { "demo_app" }
    $dependencyRoot = Resolve-DependencyManagementProjectRoot
    $appRoot = Join-Path (Get-Location) "app\apps\$appId"
    $deploymentRoot = if ($env:ACTIVE_BACKEND_DEPLOYMENT_ROOT) { $env:ACTIVE_BACKEND_DEPLOYMENT_ROOT } else { Join-Path (Get-Location) "local-deployment" }
    $composeManifest = $env:ACTIVE_BACKEND_COMPOSE_MANIFEST
    $envFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } elseif ($env:ACTIVE_BACKEND_ENV_FILE) { $env:ACTIVE_BACKEND_ENV_FILE } else { ".env" }

    Write-Host ""
    Write-Host "Active backend app context" -ForegroundColor Cyan
    Write-Host "  App id: $appId" -ForegroundColor Gray
    Write-Host "  App folder: $appRoot" -ForegroundColor Gray
    Write-Host "  Deployment root: $deploymentRoot" -ForegroundColor Gray
    Write-Host "  Dependency root: $dependencyRoot" -ForegroundColor Gray
    Write-Host "  Env file: $envFile" -ForegroundColor Gray
    if (-not [string]::IsNullOrWhiteSpace($composeManifest)) {
        Write-Host "  Compose manifest: $composeManifest" -ForegroundColor Gray
    }
    if (-not [string]::IsNullOrWhiteSpace($ComposeFile)) {
        Write-Host "  Compose file: $ComposeFile" -ForegroundColor Gray
    }
    Write-Host ""
}

<#
.SYNOPSIS
Returns the active list of Docker Compose files.

.DESCRIPTION
Reads the newline-delimited compose stack exported by quick-start so menu actions
operate on the same app-specific stack that was selected during startup.

.PARAMETER FallbackComposeFile
Single compose file path used when no active compose stack has been exported.

.RETURNS
String[]. The active compose files in the order they should be passed to Docker.
#>
function Get-ActiveComposeFiles {
    param(
        [string]$FallbackComposeFile
    )

    if (-not [string]::IsNullOrWhiteSpace($env:ACTIVE_BACKEND_COMPOSE_FILES)) {
        return ($env:ACTIVE_BACKEND_COMPOSE_FILES -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }

    if (-not [string]::IsNullOrWhiteSpace($FallbackComposeFile)) {
        return @($FallbackComposeFile)
    }

    return @()
}

<#
.SYNOPSIS
Determines whether the active compose stack includes Neo4j.

.DESCRIPTION
Checks the active compose file list for Neo4j-related stack fragments so browser
helpers keep opening the Neo4j browser when the selected app stack needs it.

.PARAMETER ComposeFile
Fallback primary compose file path.

.RETURNS
Boolean. True when a compose file path in the active stack references Neo4j.
#>
function Test-ComposeIncludesNeo4j {
    param(
        [string]$ComposeFile
    )

    foreach ($activeComposeFile in Get-ActiveComposeFiles -FallbackComposeFile $ComposeFile) {
        if ($activeComposeFile -like "*neo4j*") {
            return $true
        }
    }

    return $false
}

<#
.SYNOPSIS
Runs Docker Compose against the full active compose stack.

.DESCRIPTION
Builds a Docker Compose invocation using the active app-specific compose files so
start, stop, and rebuild actions stay aligned with the selected backend app.

.PARAMETER EnvFile
Absolute or relative env file passed to Docker Compose.

.PARAMETER ComposeFile
Fallback primary compose file when no active compose stack has been exported.

.PARAMETER CommandArgs
Arguments appended after the compose file list, such as `up` or `down`.

.RETURNS
Nothing.
#>
function Invoke-BackendComposeCommand {
    param(
        [string]$EnvFile,
        [string]$ComposeFile,
        [string[]]$CommandArgs
    )

    $composeArgs = @("compose", "--env-file", $EnvFile)
    foreach ($activeComposeFile in Get-ActiveComposeFiles -FallbackComposeFile $ComposeFile) {
        $composeArgs += @("-f", $activeComposeFile)
    }

    $composeArgs += $CommandArgs
    & docker @composeArgs
}

<#
.SYNOPSIS
Opens an app-specific file or folder in Explorer.

.DESCRIPTION
Reveals the requested backend artifact for the active app. Folders are opened
directly in Explorer, while files are selected so adjacent files remain easy to
discover.

.PARAMETER Path
Absolute or relative file-system path of the artifact to reveal.

.PARAMETER Description
Friendly label printed to the console before opening the artifact.

.RETURNS
Int32. Returns 0 when the artifact was opened or 1 when the path is missing or
could not be opened.
#>
function Open-BackendArtifact {
    param(
        [string]$Path,
        [string]$Description
    )

    if (-not (Test-Path $Path)) {
        Write-Host "${Description} not found: $Path" -ForegroundColor Yellow
        return 1
    }

    $resolvedPath = (Resolve-Path $Path).Path
    Write-Host "Opening ${Description}: $resolvedPath" -ForegroundColor Cyan

    try {
        if (Test-Path $resolvedPath -PathType Container) {
            Start-Process "explorer.exe" $resolvedPath
        } else {
            Start-Process "explorer.exe" "/select,`"$resolvedPath`""
        }
    } catch {
        Write-Host "Could not open $Description automatically: $_" -ForegroundColor Yellow
        return 1
    }

    return 0
}

<#
.SYNOPSIS
Displays a submenu for app-specific files and folders.

.DESCRIPTION
Shows the most relevant entry points for the active backend app, beginning with
API routes and then offering services, schemas, config, container, environment,
and dependency artifacts.

.PARAMETER ComposeFile
Active Docker Compose file path selected by quick-start.

.RETURNS
Int32. Returns 0 when the user leaves the submenu.
#>
function Show-AppArtifactMenu {
    param(
        [string]$ComposeFile
    )

    $projectRoot = (Get-Location).Path
    $appId = if ($env:ACTIVE_BACKEND_APP_ID) { $env:ACTIVE_BACKEND_APP_ID } else { "demo_app" }
    $appRoot = Join-Path $projectRoot "app\apps\$appId"
    $deploymentRoot = if ($env:ACTIVE_BACKEND_DEPLOYMENT_ROOT) { $env:ACTIVE_BACKEND_DEPLOYMENT_ROOT } else { Join-Path $projectRoot "local-deployment" }
    $composeManifestPath = if ($env:ACTIVE_BACKEND_COMPOSE_MANIFEST) { $env:ACTIVE_BACKEND_COMPOSE_MANIFEST } else { Join-Path $deploymentRoot "compose-files.txt" }
    $composeOverridePath = Join-Path $deploymentRoot "compose.override.yml"
    $routesPath = Join-Path $appRoot "routes"
    $servicesPath = Join-Path $appRoot "services"
    $schemasPath = Join-Path $appRoot "schemas"
    $configPath = Join-Path $appRoot "config"
    $dependencyRoot = Resolve-DependencyManagementProjectRoot
    $pyprojectPath = Join-Path $dependencyRoot "pyproject.toml"
    $lockfilePath = Join-Path $dependencyRoot "pdm.lock"
    $envFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } elseif ($env:ACTIVE_BACKEND_ENV_FILE) { $env:ACTIVE_BACKEND_ENV_FILE } else { ".env" }
    $envPath = if ([System.IO.Path]::IsPathRooted($envFile)) { $envFile } else { [System.IO.Path]::GetFullPath((Join-Path $projectRoot $envFile)) }

    $composePath = $deploymentRoot

    while ($true) {
        Write-Host ""
        Write-Host "============= App-Specific Files =============" -ForegroundColor Yellow
        Show-ActiveBackendContext -ComposeFile $composePath
        Write-Host "  1) API endpoints and functionality (routes)" -ForegroundColor Gray
        Write-Host "  2) Services / business logic" -ForegroundColor Gray
        Write-Host "  3) Schemas / data contracts" -ForegroundColor Gray
        Write-Host "  4) App config / metadata" -ForegroundColor Gray
        Write-Host "  5) Containers / Docker Compose deployment folder" -ForegroundColor Gray
        Write-Host "  6) Docker Compose manifest (compose-files.txt)" -ForegroundColor Gray
        Write-Host "  7) App Docker Compose override" -ForegroundColor Gray
        Write-Host "  8) Environment file" -ForegroundColor Gray
        Write-Host "  9) Dependency manifest (pyproject.toml)" -ForegroundColor Gray
        Write-Host "  10) Dependency lockfile (pdm.lock)" -ForegroundColor Gray
        Write-Host "  11) App root folder" -ForegroundColor Gray
        Write-Host "  0) Back to main menu" -ForegroundColor Gray
        Write-Host ""

        $choice = Read-Host "Your choice (0-11)"

        switch ($choice) {
            "1" {
                Write-Host "Endpoint handlers live in $routesPath. Business logic usually lives in $servicesPath." -ForegroundColor Yellow
                [void](Open-BackendArtifact -Path $routesPath -Description "API routes folder")
            }
            "2" {
                [void](Open-BackendArtifact -Path $servicesPath -Description "services folder")
            }
            "3" {
                [void](Open-BackendArtifact -Path $schemasPath -Description "schemas folder")
            }
            "4" {
                [void](Open-BackendArtifact -Path $configPath -Description "app config folder")
            }
            "5" {
                [void](Open-BackendArtifact -Path $composePath -Description "Docker Compose deployment folder")
            }
            "6" {
                [void](Open-BackendArtifact -Path $composeManifestPath -Description "Docker Compose manifest")
            }
            "7" {
                [void](Open-BackendArtifact -Path $composeOverridePath -Description "app Docker Compose override")
            }
            "8" {
                [void](Open-BackendArtifact -Path $envPath -Description "environment file")
            }
            "9" {
                [void](Open-BackendArtifact -Path $pyprojectPath -Description "dependency manifest")
            }
            "10" {
                [void](Open-BackendArtifact -Path $lockfilePath -Description "dependency lockfile")
            }
            "11" {
                [void](Open-BackendArtifact -Path $appRoot -Description "app root folder")
            }
            "0" {
                return 0
            }
            Default {
                Write-Host "Invalid selection. Please choose a value between 0 and 11." -ForegroundColor Yellow
            }
        }
    }
}

function Open-BrowserInIncognito {
    param(
        [string]$Port,
        [string]$ComposeFile
    )

    $apiUrl = "http://localhost:$Port/docs"
    $neo4jUrl = "http://localhost:7474"
    $includeNeo4j = Test-ComposeIncludesNeo4j -ComposeFile $ComposeFile

    Write-Host "Opening browser..." -ForegroundColor Cyan

    $edgeArgs = "--inprivate $apiUrl"
    $chromeArgs = "--incognito $apiUrl"

    if ($includeNeo4j) {
        $edgeArgs = "$edgeArgs $neo4jUrl"
        $chromeArgs = "$chromeArgs $neo4jUrl"
        Write-Host "Neo4j Browser will open at $neo4jUrl using the same private window." -ForegroundColor Gray
    }

    Start-Process "msedge" $edgeArgs -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) {
        Start-Process "chrome" $chromeArgs -ErrorAction SilentlyContinue
    }
}

function Get-ActiveBackendBrowserTargets {
    <#
    .SYNOPSIS
    Parses the ACTIVE_BACKEND_BROWSER_TARGETS environment variable into objects.
    #>
    $targets = @()
    if ([string]::IsNullOrWhiteSpace($env:ACTIVE_BACKEND_BROWSER_TARGETS)) {
        return $targets
    }

    foreach ($line in ($env:ACTIVE_BACKEND_BROWSER_TARGETS -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split "\|", 2
        if ($parts.Count -lt 2) { continue }
        $targets += [PSCustomObject]@{ Label = $parts[0]; Url = $parts[1] }
    }
    return $targets
}

function Start-Backend {
    param(
        [string]$Port,
        [string]$ComposeFile
    )

    $envFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } elseif ($env:ACTIVE_BACKEND_ENV_FILE) { $env:ACTIVE_BACKEND_ENV_FILE } else { ".env" }

    Write-Host "Starting backend directly..." -ForegroundColor Cyan

    # Determine if Neo4j is included
    $includeNeo4j = Test-ComposeIncludesNeo4j -ComposeFile $ComposeFile

    # Get additional browser targets (e.g., Mongo Express, pgAdmin)
    $browserTargets = Get-ActiveBackendBrowserTargets
    Write-Host "DEBUG: ACTIVE_BACKEND_BROWSER_TARGETS env var = '$($env:ACTIVE_BACKEND_BROWSER_TARGETS)'" -ForegroundColor Magenta
    Write-Host "DEBUG: Parsed browser targets count = $($browserTargets.Count)" -ForegroundColor Magenta
    if ($browserTargets.Count -gt 0) {
        foreach ($target in $browserTargets) {
            Write-Host "DEBUG:   Target: $($target.Label) -> $($target.Url)" -ForegroundColor Magenta
        }
    }

    # Open browsers automatically when services are ready
    Open-BrowsersDelayed -Port $Port -IncludeNeo4j $includeNeo4j -TimeoutSeconds 120 -AdditionalTargets $browserTargets

    Invoke-BackendComposeCommand -EnvFile $envFile -ComposeFile $ComposeFile -CommandArgs @("up", "--build", "--remove-orphans")
}

function Start-DependencyManagement {
    Write-Host "Opening Dependency Management..." -ForegroundColor Cyan

    $dependencyRoot = Resolve-DependencyManagementProjectRoot

    Show-ActiveBackendContext

    $coreMenuScript = ".\tools\core-pdm-manager\menu\menu.ps1"
    if (Test-Path $coreMenuScript) {
        & $coreMenuScript -ProjectRoot $dependencyRoot
    } else {
        Write-Host "core-pdm-manager menu not found. Falling back to root dependency wrapper." -ForegroundColor Yellow
        Write-Host "To fix: git submodule update --init --recursive" -ForegroundColor Yellow
        if (Test-Path .\manage-python-project-dependencies.ps1) {
            & .\manage-python-project-dependencies.ps1
        } else {
            Write-Host ".\manage-python-project-dependencies.ps1 not found" -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host "Dependency Management completed." -ForegroundColor Gray
}

function Start-DependencyAndBackend {
    param(
        [string]$Port,
        [string]$ComposeFile
    )

    $envFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } elseif ($env:ACTIVE_BACKEND_ENV_FILE) { $env:ACTIVE_BACKEND_ENV_FILE } else { ".env" }
    $dependencyRoot = Resolve-DependencyManagementProjectRoot
    
    Write-Host "Opening Dependency Management first..." -ForegroundColor Cyan

    Show-ActiveBackendContext -ComposeFile $ComposeFile

    $coreMenuScript = ".\tools\core-pdm-manager\menu\menu.ps1"
    if (Test-Path $coreMenuScript) {
        & $coreMenuScript -ProjectRoot $dependencyRoot -Action dependency-management
    } else {
        Write-Host "core-pdm-manager menu not found. Falling back to root dependency wrapper." -ForegroundColor Yellow
        Write-Host "To fix: git submodule update --init --recursive" -ForegroundColor Yellow
        if (Test-Path .\manage-python-project-dependencies.ps1) {
            & .\manage-python-project-dependencies.ps1
        } else {
            Write-Host ".\manage-python-project-dependencies.ps1 not found" -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host "Starting backend now..." -ForegroundColor Cyan
    
    # Determine if Neo4j is included
    $includeNeo4j = Test-ComposeIncludesNeo4j -ComposeFile $ComposeFile

    # Get additional browser targets (e.g., Mongo Express, pgAdmin)
    $browserTargets = Get-ActiveBackendBrowserTargets

    # Open browsers automatically when services are ready
    Open-BrowsersDelayed -Port $Port -IncludeNeo4j $includeNeo4j -TimeoutSeconds 120 -AdditionalTargets $browserTargets

    Invoke-BackendComposeCommand -EnvFile $envFile -ComposeFile $ComposeFile -CommandArgs @("up", "--build", "--remove-orphans")
}

function Invoke-EnvironmentDiagnostics {
    Write-Host "Running Docker/build diagnostics..." -ForegroundColor Yellow

    $dependencyRoot = Resolve-DependencyManagementProjectRoot

    $coreMenuScript = ".\tools\core-pdm-manager\menu\menu.ps1"
    if (Test-Path $coreMenuScript) {
        & $coreMenuScript -ProjectRoot $dependencyRoot -Action diagnostics
    } else {
        $diagnosticsScript = "run-docker-build-diagnostics.ps1"
        if (Test-Path $diagnosticsScript) {
            Write-Host "core-pdm-manager diagnostics unavailable. Using root diagnostics wrapper." -ForegroundColor Yellow
            Write-Host "Gathering diagnostic information..." -ForegroundColor Gray
            try {
                & .\$diagnosticsScript
            } catch {
                Write-Host "Diagnostics encountered an error: $_" -ForegroundColor Red
            }
        } else {
            Write-Host "$diagnosticsScript not found" -ForegroundColor Yellow
        }
    }
}

function Invoke-SetupWizard {
    Write-Host "Re-running the interactive setup wizard" -ForegroundColor Cyan
    Write-Host "" 
    Write-Host "To launch the wizard again, delete the .setup-complete file and restart quick-start." -ForegroundColor Gray
    Write-Host "The wizard automatically backs up your current .env before writing a new one." -ForegroundColor Gray
    Write-Host "" 

    if (-not (Test-Path .setup-complete)) {
        Write-Host ".setup-complete is already missing. The next quick-start run will start the wizard automatically." -ForegroundColor Yellow
    }

    $choice = Read-Host "Delete .setup-complete and restart quick-start.ps1 now? (y/N)"
    if ($choice -notmatch "^[Yy]$") {
        Write-Host "No changes were made. Remove .setup-complete manually and run .\quick-start.ps1 when you're ready." -ForegroundColor Yellow
        return 1
    }

    if (Test-Path .setup-complete) {
        Remove-Item .setup-complete -Force -ErrorAction SilentlyContinue
        Write-Host ".setup-complete removed." -ForegroundColor Green
    } else {
        Write-Host ".setup-complete was not found, continuing." -ForegroundColor Gray
    }

    Write-Host "" 
    Write-Host "Now re-run quick-start to start the wizard again:" -ForegroundColor Cyan
    Write-Host "  Windows: .\quick-start.ps1" -ForegroundColor Gray
    Write-Host "  Mac/Linux: ./quick-start.sh" -ForegroundColor Gray
    return 0
}

function Invoke-DockerComposeDown {
    param(
        [string]$ComposeFile
    )

    $envFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } elseif ($env:ACTIVE_BACKEND_ENV_FILE) { $env:ACTIVE_BACKEND_ENV_FILE } else { ".env" }
    
    Write-Host "Stopping and removing containers..." -ForegroundColor Yellow
    Write-Host "   Using compose file: $ComposeFile" -ForegroundColor Gray
    Write-Host ""
    Invoke-BackendComposeCommand -EnvFile $envFile -ComposeFile $ComposeFile -CommandArgs @("down", "--remove-orphans")
    Write-Host ""
    Write-Host "Containers stopped and removed" -ForegroundColor Green
}

function Start-BackendNoCache {
    param(
        [string]$Port,
        [string]$ComposeFile
    )

    $envFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } elseif ($env:ACTIVE_BACKEND_ENV_FILE) { $env:ACTIVE_BACKEND_ENV_FILE } else { ".env" }
    
    Write-Host "Starting backend directly (with --no-cache)..." -ForegroundColor Cyan
    
    # Determine if Neo4j is included
    $includeNeo4j = Test-ComposeIncludesNeo4j -ComposeFile $ComposeFile

    # Get additional browser targets (e.g., Mongo Express, pgAdmin)
    $browserTargets = Get-ActiveBackendBrowserTargets

    # Open browsers automatically when services are ready
    Open-BrowsersDelayed -Port $Port -IncludeNeo4j $includeNeo4j -TimeoutSeconds 120 -AdditionalTargets $browserTargets

    Invoke-BackendComposeCommand -EnvFile $envFile -ComposeFile $ComposeFile -CommandArgs @("build", "--no-cache")
    Invoke-BackendComposeCommand -EnvFile $envFile -ComposeFile $ComposeFile -CommandArgs @("up", "--remove-orphans")
}

<#
.SYNOPSIS
Resolves the active backend app environment file to an absolute path.

.DESCRIPTION
Quick-start exports the selected backend app's env file in
DOCKER_COMPOSE_ENV_FILE or ACTIVE_BACKEND_ENV_FILE. This helper normalizes that
state so build and version actions update the same file used by the local stack.

.RETURNS
String. Absolute path to the active backend env file, or the root .env fallback.
#>
function Resolve-ActiveBackendEnvFilePath {
    $envFile = if ($env:DOCKER_COMPOSE_ENV_FILE) { $env:DOCKER_COMPOSE_ENV_FILE } elseif ($env:ACTIVE_BACKEND_ENV_FILE) { $env:ACTIVE_BACKEND_ENV_FILE } else { ".env" }

    if ([System.IO.Path]::IsPathRooted($envFile)) {
        return $envFile
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $envFile))
}

<#
.SYNOPSIS
Resolves the active backend app pyproject.toml path.

.DESCRIPTION
Each backend app stores committed release metadata in its own `pyproject.toml`.
This mirrors the frontend wrapper's use of per-site `package.json` versions
while keeping secrets and local runtime settings out of version control.

.PARAMETER AppId
Selected backend app id.

.RETURNS
String. Absolute path to the active app pyproject.toml.
#>
function Resolve-ActiveBackendPackageFilePath {
    param(
        [string]$AppId
    )

    $safeAppId = if ($AppId) { $AppId -replace '[\\/:*?"<>|]', '_' } else { "demo_app" }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) "app\apps\$safeAppId\pyproject.toml"))
}

<#
.SYNOPSIS
Reads the committed package version for a backend app.

.DESCRIPTION
Parses the `[project]` section version from the selected app's `pyproject.toml`.
The value is used as the Docker image semver source of truth.

.PARAMETER AppId
Selected backend app id.

.PARAMETER DefaultValue
Version returned when the package file or version field is missing.

.RETURNS
String. The app package version.
#>
function Get-ActiveBackendPackageVersion {
    param(
        [string]$AppId,
        [string]$DefaultValue = "0.1.0"
    )

    $packagePath = Resolve-ActiveBackendPackageFilePath -AppId $AppId
    if (-not (Test-Path -LiteralPath $packagePath)) {
        return $DefaultValue
    }

    $inProjectSection = $false
    foreach ($line in Get-Content -LiteralPath $packagePath) {
        $trimmedLine = $line.Trim()
        if ($trimmedLine -eq "[project]") {
            $inProjectSection = $true
            continue
        }

        if ($inProjectSection -and $trimmedLine -match '^\[') {
            break
        }

        if ($inProjectSection -and $trimmedLine -match '^version\s*=\s*"([^"]+)"') {
            return $matches[1]
        }
    }

    return $DefaultValue
}

<#
.SYNOPSIS
Writes the committed package version for a backend app.

.DESCRIPTION
Updates the `[project]` section version in the selected app's `pyproject.toml`.
If the version field is missing, it is inserted immediately after `[project]`.

.PARAMETER AppId
Selected backend app id.

.PARAMETER Version
Semantic version to persist.

.RETURNS
Nothing.
#>
function Set-ActiveBackendPackageVersion {
    param(
        [string]$AppId,
        [string]$Version
    )

    $packagePath = Resolve-ActiveBackendPackageFilePath -AppId $AppId
    if (-not (Test-Path -LiteralPath $packagePath)) {
        throw "Missing active backend package file: $packagePath"
    }

    $lines = Get-Content -LiteralPath $packagePath
    $inProjectSection = $false
    $updated = $false
    $output = New-Object System.Collections.Generic.List[string]

    foreach ($line in $lines) {
        $trimmedLine = $line.Trim()

        if ($trimmedLine -eq "[project]") {
            $inProjectSection = $true
            $output.Add($line)
            continue
        }

        if ($inProjectSection -and $trimmedLine -match '^\[' -and -not $updated) {
            $output.Add("version = `"$Version`"")
            $updated = $true
            $inProjectSection = $false
        }

        if ($inProjectSection -and $trimmedLine -match '^version\s*=') {
            $output.Add("version = `"$Version`"")
            $updated = $true
            continue
        }

        $output.Add($line)
    }

    if (-not $updated) {
        $output.Add("version = `"$Version`"")
    }

    [System.IO.File]::WriteAllLines($packagePath, $output, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] Updated $packagePath to version $Version" -ForegroundColor Green
}

<#
.SYNOPSIS
Normalizes an app id into a Docker repository name segment.

.DESCRIPTION
Docker repository components are lowercase and allow alphanumeric characters
plus separators such as dot, underscore, and dash. Invalid characters are
replaced so generated app image names remain pushable.

.PARAMETER AppId
Selected backend app id.

.RETURNS
String. Repository-safe app name segment.
#>
function ConvertTo-DockerAppName {
    param(
        [string]$AppId
    )

    $normalized = if ($AppId) { $AppId.ToLowerInvariant() } else { "app" }
    $normalized = $normalized -replace '_', '-'
    $normalized = $normalized -replace '[^a-z0-9.-]', '-'
    $normalized = $normalized.Trim(".-".ToCharArray())

    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "app"
    }

    return $normalized
}

<#
.SYNOPSIS
Builds the canonical Docker Hub image name for the active backend app.

.DESCRIPTION
The API template publishes one API image per selected backend app using the
required naming convention: sokrates1989/python-api-<app-name>.

.PARAMETER AppId
Selected backend app id.

.RETURNS
String. Docker image name without a tag.
#>
function Get-ActiveBackendApiImageName {
    param(
        [string]$AppId
    )

    $appName = ConvertTo-DockerAppName -AppId $AppId
    return "sokrates1989/python-api-$appName"
}

<#
.SYNOPSIS
Prompts for the API image semantic version.

.DESCRIPTION
Offers the same version bumper shape used by the Figma website wrapper:
patch, minor, major, manual entry, or keeping the current version. Manual
versions must use x.y.z with an optional leading v.

.PARAMETER CurrentVersion
Current package version from the active app pyproject.toml.

.RETURNS
String. The selected semantic version.
#>
function Read-ApiImageVersionSelection {
    param(
        [string]$CurrentVersion
    )

    $baseVersion = if (-not [string]::IsNullOrWhiteSpace($CurrentVersion)) { $CurrentVersion } else { "0.1.0" }
    $patchVersion = Bump-SemVer -Version $baseVersion -Level "patch"
    $minorVersion = Bump-SemVer -Version $baseVersion -Level "minor"
    $majorVersion = Bump-SemVer -Version $baseVersion -Level "major"

    Write-Host ""
    Write-Host "Version options:" -ForegroundColor Yellow
    Write-Host "  [1] Patch  ($baseVersion -> $patchVersion)"
    Write-Host "  [2] Minor  ($baseVersion -> $minorVersion)"
    Write-Host "  [3] Major  ($baseVersion -> $majorVersion)"
    Write-Host "  [4] Enter manually"
    Write-Host "  [5] Keep current ($baseVersion)"
    Write-Host ""

    while ($true) {
        $versionChoice = Read-Host "Choose version option [1]"
        if ([string]::IsNullOrWhiteSpace($versionChoice)) {
            $versionChoice = "1"
        }

        switch ($versionChoice.Trim()) {
            "1" { return $patchVersion }
            "2" { return $minorVersion }
            "3" { return $majorVersion }
            "4" {
                $manualVersion = (Read-Host "Enter version tag").Trim()
                if ($manualVersion -match '^[vV]?[0-9]+\.[0-9]+\.[0-9]+$') {
                    return $manualVersion
                }
                Write-Host "Invalid SemVer value. Use x.y.z, for example 1.2.3." -ForegroundColor Red
            }
            "5" { return $baseVersion }
            Default {
                Write-Host "Invalid option. Choose 1-5." -ForegroundColor Red
            }
        }
    }
}

<#
.SYNOPSIS
Builds the active backend API Docker image.

.DESCRIPTION
Builds the root Dockerfile for linux/amd64 and passes app-specific build args
so the production image contains the selected backend app dependencies and
runtime profile.

.PARAMETER ImageName
Docker image name without tag.

.PARAMETER TagVersion
Version tag to build.

.PARAMETER AppId
Selected backend app id baked into BACKEND_APP_ID.

.PARAMETER PythonVersion
Python base image version from the active env file.

.PARAMETER BackendDataProfile
Database/backend profile passed to the Dockerfile.

.RETURNS
Boolean. True when Docker build succeeds; otherwise false.
#>
function Invoke-ApiDockerImageBuild {
    param(
        [string]$ImageName,
        [string]$TagVersion,
        [string]$AppId,
        [string]$PythonVersion,
        [string]$BackendDataProfile
    )

    Write-Host ""
    Write-Host "Building Docker image: ${ImageName}:$TagVersion" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Building Docker image: ${ImageName}:$TagVersion" -ForegroundColor Cyan
    Write-Host "  Dockerfile: Dockerfile" -ForegroundColor Gray
    Write-Host "  Context: ." -ForegroundColor Gray
    Write-Host "  Platform: linux/amd64 (for Swarm compatibility)" -ForegroundColor Gray
    Write-Host "  Backend app: $AppId" -ForegroundColor Gray
    Write-Host ""

    $buildArgs = @(
        "--build-arg", "PYTHON_VERSION=$PythonVersion",
        "--build-arg", "IMAGE_TAG=$TagVersion",
        "--build-arg", "BACKEND_APP_ID=$AppId"
    )

    if (-not [string]::IsNullOrWhiteSpace($BackendDataProfile)) {
        $buildArgs += @("--build-arg", "BACKEND_DATA_PROFILE=$BackendDataProfile")
    }

    if (docker buildx version 2>$null) {
        Write-Host "Using docker buildx for platform linux/amd64..." -ForegroundColor Cyan
        docker buildx build --platform "linux/amd64" -t "${ImageName}:$TagVersion" -f "Dockerfile" @buildArgs "." --load
    } else {
        Write-Host "docker buildx not found, falling back to docker build (host architecture)..." -ForegroundColor Yellow
        docker build -t "${ImageName}:$TagVersion" -f "Dockerfile" @buildArgs "."
    }

    return ($LASTEXITCODE -eq 0)
}

<#
.SYNOPSIS
Pushes a Docker image and offers registry login when authentication fails.

.DESCRIPTION
Attempts a Docker push, detects common authentication errors, and gives the
user a chance to run docker login before retrying the same push once.

.PARAMETER ImageRef
Full Docker image reference including tag.

.RETURNS
Boolean. True when the image is pushed; otherwise false.
#>
function Push-DockerImageWithLoginRetry {
    param(
        [string]$ImageRef
    )

    Write-Host "Pushing image: $ImageRef" -ForegroundColor Yellow
    $pushOutput = docker push $ImageRef 2>&1
    $pushExitCode = $LASTEXITCODE
    $pushOutput | ForEach-Object { Write-Host $_ }

    if ($pushExitCode -eq 0) {
        return $true
    }

    $combinedOutput = ($pushOutput | Out-String)
    if ($combinedOutput -match '(?i)(insufficient_scope|unauthorized|authentication required|no basic auth credentials|requested access)') {
        Write-Host ""
        Write-Host "Docker registry login may be required." -ForegroundColor Yellow
        $loginChoice = Read-Host "Run docker login and retry? (Y/n)"
        if ($loginChoice -notmatch '^[Nn]$') {
            docker login
            if ($LASTEXITCODE -eq 0) {
                Write-Host ""
                Write-Host "Retrying push: $ImageRef" -ForegroundColor Yellow
                docker push $ImageRef
                return ($LASTEXITCODE -eq 0)
            }
        }
    }

    return $false
}

<#
.SYNOPSIS
Builds and pushes the selected backend app API image.

.DESCRIPTION
Uses the active backend app selected in quick-start, reads and updates the
committed app package version in `pyproject.toml`, builds the API image, pushes
the versioned tag, then tags and pushes latest.

.RETURNS
Boolean. True when build and both pushes succeed; otherwise false.
#>
function Invoke-ProductionImageBuild {
    $appId = if ($env:ACTIVE_BACKEND_APP_ID) { $env:ACTIVE_BACKEND_APP_ID } else { "demo_app" }
    $envFile = Resolve-ActiveBackendEnvFilePath
    $imageName = Get-ActiveBackendApiImageName -AppId $appId
    $currentVersion = Get-ActiveBackendPackageVersion -AppId $appId -DefaultValue "0.1.0"
    $pythonVersion = Get-EnvVariable -VariableName "PYTHON_VERSION" -EnvFile $envFile -DefaultValue "3.13-slim"
    $backendDataProfile = Get-EnvVariable -VariableName "DB_TYPE" -EnvFile $envFile -DefaultValue ""

    Write-Host ""
    Write-Host "Docker Build & Push" -ForegroundColor Cyan
    Write-Host "======================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Images to build:" -ForegroundColor Yellow
    Write-Host "  API:      $imageName" -ForegroundColor Gray
    Write-Host "  (auto-detected from active backend app: $appId)" -ForegroundColor DarkGray

    $tagVersion = Read-ApiImageVersionSelection -CurrentVersion $currentVersion

    if ($tagVersion -ne $currentVersion) {
        Set-ActiveBackendPackageVersion -AppId $appId -Version $tagVersion
    } else {
        Write-Host "[OK] Keeping app package version $tagVersion" -ForegroundColor Green
    }

    $buildOk = Invoke-ApiDockerImageBuild -ImageName $imageName -TagVersion $tagVersion -AppId $appId -PythonVersion $pythonVersion -BackendDataProfile $backendDataProfile
    if (-not $buildOk) {
        Write-Host "[ERROR] Docker build failed for ${imageName}:$tagVersion" -ForegroundColor Red
        return $false
    }

    Write-Host ""
    Write-Host "[OK] Docker image built successfully: ${imageName}:$tagVersion" -ForegroundColor Green
    Write-Host ""

    if (-not (Push-DockerImageWithLoginRetry -ImageRef "${imageName}:$tagVersion")) {
        Write-Host "[ERROR] Push failed for ${imageName}:$tagVersion" -ForegroundColor Red
        return $false
    }
    Write-Host "[OK] Image pushed successfully" -ForegroundColor Green

    Write-Host "Tagging and pushing as 'latest'..." -ForegroundColor Yellow
    docker tag "${imageName}:$tagVersion" "${imageName}:latest"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Could not tag latest image." -ForegroundColor Red
        return $false
    }

    if (-not (Push-DockerImageWithLoginRetry -ImageRef "${imageName}:latest")) {
        Write-Host "[ERROR] Latest push failed for ${imageName}:latest" -ForegroundColor Red
        return $false
    }
    Write-Host "[OK] Latest tag pushed" -ForegroundColor Green

    return $true
}

function Start-CICDSetup {
    Write-Host "Setting up CI/CD Pipeline..." -ForegroundColor Cyan
    Write-Host ""
    if (Test-Path ci-cd\docker-compose.cicd-setup.yml) {
        docker compose -f ci-cd\docker-compose.cicd-setup.yml run --rm cicd-setup
    } else {
        Write-Host "ci-cd\docker-compose.cicd-setup.yml not found" -ForegroundColor Red
        Write-Host "Please ensure the ci-cd directory exists" -ForegroundColor Yellow
    }
}

function Show-MainMenu {
    param(
        [string]$Port,
        [string]$ComposeFile
    )

    Write-Host "DEBUG MENU START: ACTIVE_BACKEND_BROWSER_TARGETS = '$($env:ACTIVE_BACKEND_BROWSER_TARGETS)'" -ForegroundColor Magenta
 
    $hasCognito = [bool](Get-Command Invoke-CognitoSetup -ErrorAction SilentlyContinue)
    $hasAuthProvider = [bool](Get-Command Set-AuthProvider -ErrorAction SilentlyContinue)
    $hasKeycloakBootstrap = [bool](Get-Command Invoke-KeycloakBootstrap -ErrorAction SilentlyContinue)
    $activeAppId = if ($env:ACTIVE_BACKEND_APP_ID) { $env:ACTIVE_BACKEND_APP_ID } else { "demo_app" }
    $activeApiVersion = Get-ActiveBackendPackageVersion -AppId $activeAppId -DefaultValue "0.1.0"
 
    $menuNext = 1
    $MENU_START_BACKEND = $menuNext; $menuNext++
    $MENU_START_BACKEND_NO_CACHE = $menuNext; $menuNext++
    $MENU_START_DEP_AND_BACKEND = $menuNext; $menuNext++
 
    $MENU_MAINT_DOWN = $menuNext; $menuNext++
    $MENU_MAINT_DEP_MGMT = $menuNext; $menuNext++
    $MENU_MAINT_DIAGNOSTICS = $menuNext; $menuNext++
    $MENU_MAINT_APP_FILES = $menuNext; $menuNext++
 
    $MENU_BUILD_PROD_IMAGE = $menuNext; $menuNext++
    $MENU_BUILD_CICD_SETUP = $menuNext; $menuNext++
    $MENU_BUILD_BUMP_VERSION = $menuNext; $menuNext++
 
    $MENU_SETUP_COGNITO = $menuNext; $menuNext++
    $MENU_SETUP_AUTH = $null
    if ($hasAuthProvider) { $MENU_SETUP_AUTH = $menuNext; $menuNext++ }
    $MENU_SETUP_KEYCLOAK_BOOTSTRAP = $null
    if ($hasKeycloakBootstrap) { $MENU_SETUP_KEYCLOAK_BOOTSTRAP = $menuNext; $menuNext++ }
    $MENU_SETUP_WIZARD = $menuNext; $menuNext++
 
    $MENU_EXIT = $menuNext
 
    Write-Host "" 
    Write-Host "================ Main Menu ================" -ForegroundColor Yellow
    Write-Host "" 
 
    Write-Host "Start:" -ForegroundColor Yellow
    Write-Host "  $MENU_START_BACKEND) Start backend directly (docker compose up)" -ForegroundColor Gray
    Write-Host "  $MENU_START_BACKEND_NO_CACHE) Start backend with --no-cache (fixes caching issues)" -ForegroundColor Gray
    Write-Host "  $MENU_START_DEP_AND_BACKEND) Both - Dependency Management and then start backend" -ForegroundColor Gray
    Write-Host "" 
    Write-Host "Maintenance:" -ForegroundColor Yellow
    Write-Host "  $MENU_MAINT_DOWN) Docker Compose Down (stop and remove containers)" -ForegroundColor Gray
    Write-Host "  $MENU_MAINT_DEP_MGMT) Open Dependency Management only" -ForegroundColor Gray
    Write-Host "  $MENU_MAINT_DIAGNOSTICS) Run Docker/Build Diagnostics" -ForegroundColor Gray
    Write-Host "  $MENU_MAINT_APP_FILES) Open app-specific files and folders" -ForegroundColor Gray
    Write-Host "" 
    Write-Host "Build / CI-CD:" -ForegroundColor Yellow
    Write-Host "  $MENU_BUILD_PROD_IMAGE) Build & Push API Docker Image (v$activeApiVersion)" -ForegroundColor Gray
    Write-Host "  $MENU_BUILD_CICD_SETUP) Setup CI/CD Pipeline" -ForegroundColor Gray
    Write-Host "  $MENU_BUILD_BUMP_VERSION) Bump release version for docker image" -ForegroundColor Gray
    Write-Host "" 
    Write-Host "Setup:" -ForegroundColor Yellow
    Write-Host "  $MENU_SETUP_COGNITO) Configure AWS Cognito" -ForegroundColor Gray
    if ($hasAuthProvider) {
        Write-Host "  $MENU_SETUP_AUTH) Configure Authentication Provider (Cognito/Keycloak/Dual)" -ForegroundColor Gray
    }
    if ($hasKeycloakBootstrap) {
        Write-Host "  $MENU_SETUP_KEYCLOAK_BOOTSTRAP) Run Keycloak realm bootstrap (Docker)" -ForegroundColor Gray
    }
    Write-Host "  $MENU_SETUP_WIZARD) Re-run setup wizard" -ForegroundColor Gray
    Write-Host "" 
    Write-Host "  $MENU_EXIT) Exit" -ForegroundColor Gray
 
    Write-Host ""
    $choice = Read-Host "Your choice (1-$MENU_EXIT)"
 
     $summary = $null
     $exitCode = 0
 
     switch ($choice) {
        "$MENU_START_BACKEND" {
             Start-Backend -Port $Port -ComposeFile $ComposeFile
             $summary = "Backend start triggered (docker compose up)"
         }
        "$MENU_START_BACKEND_NO_CACHE" {
             Start-BackendNoCache -Port $Port -ComposeFile $ComposeFile
             $summary = "Backend start with --no-cache triggered"
         }
        "$MENU_MAINT_DOWN" {
             Invoke-DockerComposeDown -ComposeFile $ComposeFile
             $summary = "Docker Compose Down executed"
         }
        "$MENU_MAINT_DEP_MGMT" {
             Start-DependencyManagement
             Write-Host "To start the backend, re-run quick-start.ps1 and choose a start option." -ForegroundColor Yellow
             $summary = "Dependency Management executed"
         }
        "$MENU_START_DEP_AND_BACKEND" {
             Start-DependencyAndBackend -Port $Port -ComposeFile $ComposeFile
             $summary = "Dependency Management and backend start executed"
         }
        "$MENU_MAINT_DIAGNOSTICS" {
             Invoke-EnvironmentDiagnostics
             $summary = "Docker/Build diagnostics launched"
         }
        "$MENU_MAINT_APP_FILES" {
             Show-AppArtifactMenu -ComposeFile $ComposeFile
             $summary = "App-specific files menu opened"
         }
        "$MENU_SETUP_COGNITO" {
             if ($hasCognito) {
                 Invoke-CognitoSetup
                 $summary = "AWS Cognito setup executed"
             } else {
                 Write-Host "AWS Cognito module not loaded." -ForegroundColor Yellow
                 Write-Host "Ensure setup/modules/cognito_setup.ps1 is imported before selecting this option." -ForegroundColor Yellow
                 $summary = "AWS Cognito setup could not run"
                 $exitCode = 1
             }
         }
        "$MENU_SETUP_AUTH" {
            if ($hasAuthProvider) {
                Set-AuthProvider
                if (Get-Command Show-AuthStatus -ErrorAction SilentlyContinue) {
                    Show-AuthStatus
                }
                $summary = "Authentication provider setup executed"
            } else {
                Write-Host "Auth provider module not loaded." -ForegroundColor Yellow
                Write-Host "Ensure setup/modules/auth_provider.ps1 is available." -ForegroundColor Yellow
                $summary = "Auth provider setup could not run"
                $exitCode = 1
            }
        }
        "$MENU_SETUP_KEYCLOAK_BOOTSTRAP" {
            if ($hasKeycloakBootstrap) {
                if (Invoke-KeycloakBootstrap) {
                    $summary = "Keycloak realm bootstrap executed"
                } else {
                    $summary = "Keycloak realm bootstrap failed"
                    $exitCode = 1
                }
            } else {
                Write-Host "Keycloak bootstrap module not loaded." -ForegroundColor Yellow
                Write-Host "Ensure setup/modules/bootstrap_utils.ps1 is available." -ForegroundColor Yellow
                $summary = "Keycloak realm bootstrap could not run"
                $exitCode = 1
            }
        }
        "$MENU_BUILD_PROD_IMAGE" {
             $buildPushOk = Invoke-ProductionImageBuild
             if ($buildPushOk) {
                 $summary = "API Docker image build/push completed"
             } else {
                 $summary = "API Docker image build/push failed"
                 $exitCode = 1
             }
         }
        "$MENU_BUILD_CICD_SETUP" {
             Start-CICDSetup
             $summary = "CI/CD setup started"
         }
        "$MENU_SETUP_WIZARD" {
             $result = Invoke-SetupWizard
             if ($result -eq 0) {
                 $summary = "Setup wizard re-run completed"
             } else {
                 $summary = "Setup wizard re-run failed or aborted"
                 $exitCode = 1
             }
         }
        "$MENU_BUILD_BUMP_VERSION" {
             $versionAppId = if ($env:ACTIVE_BACKEND_APP_ID) { $env:ACTIVE_BACKEND_APP_ID } else { "demo_app" }
             $currentAppVersion = Get-ActiveBackendPackageVersion -AppId $versionAppId -DefaultValue "0.1.0"
             $newAppVersion = Read-ApiImageVersionSelection -CurrentVersion $currentAppVersion
             Set-ActiveBackendPackageVersion -AppId $versionAppId -Version $newAppVersion
             $summary = "Active app package version updated"
         }
        "$MENU_EXIT" {
             Write-Host "Exiting script." -ForegroundColor Cyan
             exit 0
         }
         Default {
             Write-Host "Invalid selection. Please re-run the script." -ForegroundColor Yellow
             exit 1
         }
     }

    Write-Host ""
    if ($summary) {
        Write-Host ("{0}" -f $summary) -ForegroundColor Green
    }
    Write-Host 'Quick-start finished. Run the script again for more actions.' -ForegroundColor Cyan
    Write-Host ""
    exit $exitCode
}
