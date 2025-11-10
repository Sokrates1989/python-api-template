#!/usr/bin/env pwsh
# Quick fix script to update .env for Neo4j

Write-Host "🔧 Fixing .env for Neo4j..." -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path .env)) {
    Write-Host "❌ .env file not found!" -ForegroundColor Red
    exit 1
}

# Backup current .env
$backupFile = ".env.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Copy-Item .env $backupFile
Write-Host "📋 Backed up .env to $backupFile" -ForegroundColor Gray
Write-Host ""

# Update Neo4j settings
$content = Get-Content .env
$content = $content -replace '^DB_USER=.*', 'DB_USER=neo4j'
$content = $content -replace '^DB_PASSWORD=.*', 'DB_PASSWORD=neo4jpassword'
$content = $content -replace '^DB_PORT=.*', 'DB_PORT=7687'

# Ensure NEO4J_HTTP_PORT exists
if (-not ($content -match '^NEO4J_HTTP_PORT=')) {
    $content += "`nNEO4J_HTTP_PORT=7474"
}

$content | Set-Content .env

Write-Host "✅ Updated .env with Neo4j credentials:" -ForegroundColor Green
Write-Host "   DB_USER=neo4j" -ForegroundColor Gray
Write-Host "   DB_PASSWORD=neo4jpassword" -ForegroundColor Gray
Write-Host "   DB_PORT=7687" -ForegroundColor Gray
Write-Host "   NEO4J_HTTP_PORT=7474" -ForegroundColor Gray
Write-Host ""
Write-Host "🎉 You can now run: docker compose -f docker\docker-compose.neo4j.yml up" -ForegroundColor Cyan
