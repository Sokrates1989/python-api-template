# version_manager.ps1
# PowerShell module for managing Docker image versions and semantic versioning

function Bump-SemVer {
    param(
        [string]$Version,
        [ValidateSet('patch','minor','major')]
        [string]$Level
    )

    if ([string]::IsNullOrWhiteSpace($Version)) {
        $Version = '0.0.0'
    }

    $prefix = ''
    if ($Version.StartsWith('v') -or $Version.StartsWith('V')) {
        $prefix = $Version.Substring(0,1)
        $Version = $Version.Substring(1)
    }

    $parts = $Version.Split('.')
    if ($parts.Count -lt 3) {
        $parts = @($parts + @('0','0','0'))[0..2]
    }

    try {
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        $patch = [int]$parts[2]
    } catch {
        return $null
    }

    switch ($Level) {
        'patch' { $patch += 1 }
        'minor' { $minor += 1; $patch = 0 }
        'major' { $major += 1; $minor = 0; $patch = 0 }
    }

    return "$prefix$major.$minor.$patch"
}

function Update-ImageVersionInFile {
    param(
        [string]$Path,
        [string]$NewVersion
    )

    if (-not (Test-Path $Path)) {
        Write-Host "[WARN] $Path not found - skipping." -ForegroundColor Yellow
        return
    }

    $lines = Get-Content $Path
    $replaced = $false
    $updatedLines = foreach ($line in $lines) {
        if (-not $replaced -and $line -match '^IMAGE_VERSION=') {
            $replaced = $true
            "IMAGE_VERSION=$NewVersion"
        } else {
            $line
        }
    }

    if (-not $replaced) {
        $updatedLines += "IMAGE_VERSION=$NewVersion"
    }

    Set-Content -Path $Path -Value $updatedLines
    Write-Host "[OK] $Path -> IMAGE_VERSION=$NewVersion" -ForegroundColor Green
}

function Update-ImageVersion {
    $envFile = '.env'
    $ciEnvFile = '.ci.env'

    $currentEnvVersion = $null
    if (Test-Path $envFile) {
        $currentEnvVersion = (Get-Content $envFile | Where-Object { $_ -match '^IMAGE_VERSION=' } | Select-Object -First 1)
        if ($currentEnvVersion) {
            $currentEnvVersion = ($currentEnvVersion -split '=',2)[1].Trim().Trim('"')
        }
    }

    $currentCiVersion = $null
    if (Test-Path $ciEnvFile) {
        $currentCiVersion = (Get-Content $ciEnvFile | Where-Object { $_ -match '^IMAGE_VERSION=' } | Select-Object -First 1)
        if ($currentCiVersion) {
            $currentCiVersion = ($currentCiVersion -split '=',2)[1].Trim().Trim('"')
        }
    }

    $baseVersion = if (-not [string]::IsNullOrWhiteSpace($currentEnvVersion)) { $currentEnvVersion }
                  elseif (-not [string]::IsNullOrWhiteSpace($currentCiVersion)) { $currentCiVersion }
                  else { '0.1.0' }

    $displayEnv = if ($currentEnvVersion) { $currentEnvVersion } else { '<not set>' }
    $displayCi = if ($currentCiVersion) { $currentCiVersion } else { '<not set>' }

    Write-Host "" 
    Write-Host "Current IMAGE_VERSION values:" -ForegroundColor Cyan
    Write-Host "  - .env    : $displayEnv" -ForegroundColor Gray
    Write-Host "  - .ci.env : $displayCi" -ForegroundColor Gray
    Write-Host ""
    Write-Host "How would you like to update the version?" -ForegroundColor Yellow
    Write-Host "  1) Enter manually" -ForegroundColor Gray
    Write-Host "  2) Bugfix/Patch (+0.0.1)" -ForegroundColor Gray
    Write-Host "  3) Feature/Minor (+0.1.0)" -ForegroundColor Gray
    Write-Host "  4) Breaking/Major (+1.0.0)" -ForegroundColor Gray
    $choice = Read-Host "Your choice (1-4)"

    switch ($choice) {
        '1' {
            $newVersion = (Read-Host "New IMAGE_VERSION").Trim()
        }
        '2' {
            $newVersion = Bump-SemVer -Version $baseVersion -Level 'patch'
        }
        '3' {
            $newVersion = Bump-SemVer -Version $baseVersion -Level 'minor'
        }
        '4' {
            $newVersion = Bump-SemVer -Version $baseVersion -Level 'major'
        }
        Default {
            Write-Host "Invalid selection. Aborting update." -ForegroundColor Red
            return
        }
    }

    if ([string]::IsNullOrWhiteSpace($newVersion)) {
        Write-Host "Could not determine new version. Please try again." -ForegroundColor Red
        return
    }

    Write-Host ""
    Update-ImageVersionInFile -Path $envFile -NewVersion $newVersion
    Update-ImageVersionInFile -Path $ciEnvFile -NewVersion $newVersion
    Write-Host ""
    Write-Host "IMAGE_VERSION updated to $newVersion" -ForegroundColor Green
}
