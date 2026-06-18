# bootstrap_utils.ps1
#
# Purpose:
# - Bootstrap utilities for the Keycloak realm used by python-api-template.
# - Builds and runs the Docker-based bootstrap image.
#
# Usage:
#   Import or dot-source this file and call Invoke-KeycloakBootstrap.

$script:BootstrapScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:BootstrapSetupDir = Split-Path -Parent $script:BootstrapScriptDir
$script:BootstrapProjectRoot = Split-Path -Parent $script:BootstrapSetupDir
$script:BootstrapEnvFile = Join-Path $script:BootstrapProjectRoot ".env"
$script:BootstrapDir = Join-Path $script:BootstrapProjectRoot "keycloak\bootstrap"
$script:BootstrapImage = "python-api-template-keycloak-bootstrap"

function Get-BootstrapEnvValue {
    <#
    .SYNOPSIS
        Resolves a Keycloak bootstrap value from .env or the current shell.

    .PARAMETER Key
        Environment variable name to read.

    .PARAMETER DefaultValue
        Fallback value when the variable is not set.

    .OUTPUTS
        System.String. The resolved value.
    #>
    param(
        [string]$Key,
        [string]$DefaultValue = ""
    )

    $value = ""
    if (Get-Command Get-EnvVariable -ErrorAction SilentlyContinue) {
        $value = Get-EnvVariable -VariableName $Key -EnvFile $script:BootstrapEnvFile -DefaultValue ""
    }

    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Key)
    }

    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = $DefaultValue
    }

    return $value
}

function Test-HostNetworkSupport {
    <#
    .SYNOPSIS
        Determines whether Docker host networking is supported.

    .OUTPUTS
        System.Boolean. True when host networking can be used.
    #>
    $supportsHostNetwork = $false
    try {
        $runtimeInfo = [System.Runtime.InteropServices.RuntimeInformation]
        $supportsHostNetwork = $runtimeInfo::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Linux)
    } catch {
        $supportsHostNetwork = $false
    }

    return $supportsHostNetwork
}

function Get-KeycloakBootstrapUrl {
    <#
    .SYNOPSIS
        Resolves the Keycloak URL used for bootstrapping.

    .OUTPUTS
        System.String. The Keycloak URL.
    #>
    $url = Get-BootstrapEnvValue -Key "KEYCLOAK_BOOTSTRAP_URL" -DefaultValue ""
    if ([string]::IsNullOrWhiteSpace($url)) {
        $url = Get-BootstrapEnvValue -Key "KEYCLOAK_SERVER_URL" -DefaultValue ""
    }
    if ([string]::IsNullOrWhiteSpace($url)) {
        $url = Get-BootstrapEnvValue -Key "KEYCLOAK_INTERNAL_URL" -DefaultValue ""
    }

    if ([string]::IsNullOrWhiteSpace($url)) {
        $url = "http://localhost:9090"
    }

    return $url
}

function Convert-KeycloakUrlForContainer {
    <#
    .SYNOPSIS
        Normalizes Keycloak URLs for Docker containers.

    .PARAMETER Url
        Original Keycloak URL.

    .PARAMETER UseHostNetwork
        Indicates whether host networking is enabled.

    .OUTPUTS
        System.String. The container-safe Keycloak URL.
    #>
    param(
        [string]$Url,
        [bool]$UseHostNetwork
    )

    if ($UseHostNetwork) {
        return $Url
    }

    $normalized = $Url -replace "localhost", "host.docker.internal"
    $normalized = $normalized -replace "127\.0\.0\.1", "host.docker.internal"
    return $normalized
}

function Test-KeycloakConnection {
    <#
    .SYNOPSIS
        Verifies that Keycloak is reachable.

    .PARAMETER KeycloakUrl
        Base Keycloak URL to check.

    .OUTPUTS
        System.Boolean. True when Keycloak responds.
    #>
    param(
        [string]$KeycloakUrl
    )

    Write-Host "Checking Keycloak at $KeycloakUrl..." -ForegroundColor Yellow

    try {
        $response = Invoke-WebRequest -Uri "$KeycloakUrl/" -TimeoutSec 10 -UseBasicParsing
        if ($response.StatusCode -ge 200) {
            Write-Host "Keycloak is reachable" -ForegroundColor Green
            return $true
        }
    } catch {
        $errorResponse = $_.Exception.Response
        if ($null -ne $errorResponse) {
            $statusCode = [int]$errorResponse.StatusCode
            if ($statusCode -eq 405) {
                Write-Host "Keycloak is reachable" -ForegroundColor Green
                return $true
            }
        }
    }

    Write-Host "Keycloak is not reachable at $KeycloakUrl" -ForegroundColor Red
    Write-Host "Please start Keycloak first." -ForegroundColor Yellow
    return $false
}

function Get-KeycloakBootstrapConfig {
    <#
    .SYNOPSIS
        Builds the Keycloak bootstrap configuration map.

    .PARAMETER KeycloakUrl
        Base Keycloak URL used for container execution.

    .OUTPUTS
        System.Collections.Hashtable. The bootstrap configuration values.
    #>
    param(
        [string]$KeycloakUrl
    )

    $config = @{
        KeycloakUrl = $KeycloakUrl
        AdminUser = Get-BootstrapEnvValue -Key "KEYCLOAK_ADMIN" -DefaultValue "admin"
        AdminPassword = Get-BootstrapEnvValue -Key "KEYCLOAK_ADMIN_PASSWORD" -DefaultValue "admin"
        Realm = Get-BootstrapEnvValue -Key "KEYCLOAK_REALM" -DefaultValue "python-api-template"
        FrontendClientId = Get-BootstrapEnvValue -Key "KEYCLOAK_FRONTEND_CLIENT_ID" -DefaultValue "python-api-template-frontend"
        BackendClientId = Get-BootstrapEnvValue -Key "KEYCLOAK_BACKEND_CLIENT_ID" -DefaultValue ""
        BackendFallbackClientId = Get-BootstrapEnvValue -Key "KEYCLOAK_CLIENT_ID" -DefaultValue "python-api-template-backend"
        FrontendRootUrl = Get-BootstrapEnvValue -Key "KEYCLOAK_FRONTEND_ROOT_URL" -DefaultValue "http://localhost:3000"
        ApiRootUrl = Get-BootstrapEnvValue -Key "KEYCLOAK_API_ROOT_URL" -DefaultValue "http://localhost:8000"
        Roles = Get-BootstrapEnvValue -Key "KEYCLOAK_ROLES" -DefaultValue ""
        Users = Get-BootstrapEnvValue -Key "KEYCLOAK_USERS" -DefaultValue ""
        ServiceAccountRole = Get-BootstrapEnvValue -Key "KEYCLOAK_SERVICE_ACCOUNT_ROLE" -DefaultValue ""
    }

    if ([string]::IsNullOrWhiteSpace($config.BackendClientId)) {
        $config.BackendClientId = $config.BackendFallbackClientId
    }

    return $config
}

function New-KeycloakBootstrapRunArguments {
    <#
    .SYNOPSIS
        Creates docker run arguments for the bootstrap container.

    .PARAMETER Config
        Hashtable of bootstrap configuration values.

    .PARAMETER UseHostNetwork
        Indicates whether host networking is enabled.

    .OUTPUTS
        System.String[]. The docker run argument list.
    #>
    param(
        [hashtable]$Config,
        [bool]$UseHostNetwork
    )

    $runArgs = @("--rm")

    if ($UseHostNetwork) {
        $runArgs += "--network"
        $runArgs += "host"
    }

    $runArgs += "-e"; $runArgs += "KEYCLOAK_URL=$($Config.KeycloakUrl)"
    $runArgs += "-e"; $runArgs += "KEYCLOAK_ADMIN=$($Config.AdminUser)"
    $runArgs += "-e"; $runArgs += "KEYCLOAK_ADMIN_PASSWORD=$($Config.AdminPassword)"
    $runArgs += "-e"; $runArgs += "KEYCLOAK_REALM=$($Config.Realm)"
    $runArgs += "-e"; $runArgs += "KEYCLOAK_FRONTEND_CLIENT_ID=$($Config.FrontendClientId)"
    $runArgs += "-e"; $runArgs += "KEYCLOAK_BACKEND_CLIENT_ID=$($Config.BackendClientId)"
    $runArgs += "-e"; $runArgs += "KEYCLOAK_FRONTEND_ROOT_URL=$($Config.FrontendRootUrl)"
    $runArgs += "-e"; $runArgs += "KEYCLOAK_API_ROOT_URL=$($Config.ApiRootUrl)"

    if (-not [string]::IsNullOrWhiteSpace($Config.Roles)) {
        $runArgs += "-e"; $runArgs += "KEYCLOAK_ROLES=$($Config.Roles)"
    }

    if (-not [string]::IsNullOrWhiteSpace($Config.Users)) {
        $runArgs += "-e"; $runArgs += "KEYCLOAK_USERS=$($Config.Users)"
    }

    if (-not [string]::IsNullOrWhiteSpace($Config.ServiceAccountRole)) {
        $runArgs += "-e"; $runArgs += "KEYCLOAK_SERVICE_ACCOUNT_ROLE=$($Config.ServiceAccountRole)"
    }

    return $runArgs
}

function Invoke-KeycloakBootstrap {
    <#
    .SYNOPSIS
        Builds and runs the Docker-based Keycloak bootstrap flow.

    .OUTPUTS
        System.Boolean. True when the bootstrap completes successfully.
    #>
    Write-Host "" 
    Write-Host "Keycloak realm bootstrap" -ForegroundColor Cyan
    Write-Host "------------------------" -ForegroundColor Cyan

    if (Get-Command Test-DockerInstallation -ErrorAction SilentlyContinue) {
        if (-not (Test-DockerInstallation)) {
            return $false
        }
    }

    $keycloakUrl = Get-KeycloakBootstrapUrl
    if (-not (Test-KeycloakConnection -KeycloakUrl $keycloakUrl)) {
        return $false
    }

    if (-not (Test-Path $script:BootstrapDir)) {
        Write-Host "Bootstrap directory not found at $script:BootstrapDir" -ForegroundColor Red
        return $false
    }

    Write-Host "" 
    Write-Host "Building bootstrap image..." -ForegroundColor Yellow
    & docker build -t $script:BootstrapImage $script:BootstrapDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docker build failed" -ForegroundColor Red
        return $false
    }

    $useHostNetwork = Test-HostNetworkSupport
    $containerUrl = Convert-KeycloakUrlForContainer -Url $keycloakUrl -UseHostNetwork $useHostNetwork
    $config = Get-KeycloakBootstrapConfig -KeycloakUrl $containerUrl
    $runArgs = New-KeycloakBootstrapRunArguments -Config $config -UseHostNetwork $useHostNetwork

    Write-Host "" 
    Write-Host "Running bootstrap container..." -ForegroundColor Yellow
    & docker run @runArgs $script:BootstrapImage
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Bootstrap failed" -ForegroundColor Red
        return $false
    }

    Write-Host "" 
    Write-Host "Keycloak realm bootstrap complete" -ForegroundColor Green
    return $true
}
