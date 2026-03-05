$ErrorActionPreference = "SilentlyContinue"

function Stop-ListeningPort {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        try {
            Stop-Process -Id $conn.OwningProcess -Force
        } catch {}
    }
}

Write-Host "Stopping local infra services..." -ForegroundColor Cyan

Stop-ListeningPort -Port 6379
Stop-ListeningPort -Port 7233
Stop-ListeningPort -Port 8233
Stop-ListeningPort -Port 9000
Stop-ListeningPort -Port 9001

Get-Process -Name "redis-server","minio","temporal" -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Stopped Redis/MinIO/Temporal local infra processes (if running)." -ForegroundColor Green
