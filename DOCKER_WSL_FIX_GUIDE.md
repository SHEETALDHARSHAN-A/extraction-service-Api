# Docker WSL Critical Fix Guide

## Problem
Docker Desktop cannot unmount the WSL VHDX file. This is a known Windows/WSL issue.

## Solution Steps

### Step 1: Complete WSL Reset
Open PowerShell as Administrator and run these commands:

```powershell
# Stop Docker Desktop
Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue

# Wait a moment
Start-Sleep -Seconds 5

# Shutdown all WSL instances
wsl --shutdown

# Wait for WSL to fully stop
Start-Sleep -Seconds 10

# Unregister Docker WSL distributions
wsl --unregister docker-desktop
wsl --unregister docker-desktop-data

# Wait
Start-Sleep -Seconds 5
```

### Step 2: Restart Computer
This is important! Restart your computer to fully release the VHDX file locks.

```powershell
Restart-Computer
```

### Step 3: After Restart
1. Start Docker Desktop manually
2. Wait for it to fully initialize (2-3 minutes)
3. Check if Docker is working:
   ```powershell
   docker ps
   ```

### Step 4: Start Services
Once Docker is working, start your services:

```powershell
docker-compose -f docker/docker-compose.yml up -d
```

---

## Alternative: Quick Fix (Try This First)

If you don't want to restart, try this:

### Option A: Reset Docker Desktop Settings
1. Right-click Docker Desktop icon in system tray
2. Click "Troubleshoot"
3. Click "Reset to factory defaults"
4. Wait for Docker to restart
5. Try starting services again

### Option B: Manual WSL Fix
Open PowerShell as Administrator:

```powershell
# Kill all WSL processes
Get-Process -Name "wsl*" | Stop-Process -Force

# Kill Docker processes
Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "com.docker.*" -ErrorAction SilentlyContinue | Stop-Process -Force

# Shutdown WSL
wsl --shutdown

# Wait
Start-Sleep -Seconds 10

# Start Docker Desktop
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# Wait for Docker to start
Start-Sleep -Seconds 60

# Test
docker ps
```

---

## If Nothing Works

### Nuclear Option: Complete Docker Reinstall

1. **Uninstall Docker Desktop**
   - Go to Settings > Apps > Docker Desktop
   - Click Uninstall
   - Restart computer

2. **Clean WSL**
   ```powershell
   wsl --unregister docker-desktop
   wsl --unregister docker-desktop-data
   ```

3. **Delete Docker data** (optional - will lose all images/containers)
   - Delete: `C:\Users\<YourUsername>\AppData\Local\Docker`
   - Delete: `C:\Users\<YourUsername>\AppData\Roaming\Docker`

4. **Reinstall Docker Desktop**
   - Download from: https://www.docker.com/products/docker-desktop
   - Install and restart computer

5. **Rebuild services**
   ```powershell
   docker-compose -f docker/docker-compose.yml build
   docker-compose -f docker/docker-compose.yml up -d
   ```

---

## Recommended: Try This Now

**Easiest fix - Restart your computer:**

1. Save all your work
2. Restart Windows
3. After restart, open Docker Desktop and wait for it to start
4. Run: `docker-compose -f docker/docker-compose.yml up -d`

This usually fixes WSL VHDX lock issues.
