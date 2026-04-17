# Windows Support - Full PDM Dependency Management

This project now has **full Windows support** for PDM dependency management through Docker - **no bash, WSL, or Git Bash required!**

## ✅ What Works on Windows

All functionality that previously required bash now works natively in PowerShell:

- ✅ **PDM Dependency Management** - Full interactive shell with PDM, Poetry, and uv
- ✅ **Python Version Testing** - Verify your Docker and Python configuration
- ✅ **Quick Start Script** - Complete onboarding and setup
- ✅ **Docker-based Development** - Consistent environment across all platforms

## 🚀 Quick Start (Windows)

### Prerequisites
- **Docker Desktop** installed and running
- **PowerShell** (comes with Windows)

### First Time Setup

```powershell
# Run the quick-start script
.\quick-start.ps1
```

The script will:
1. Check Docker installation
2. Create `.env` from template
3. Test Python version configuration
4. Run dependency management setup
5. Start the backend

## 📦 Managing Dependencies on Windows

### Interactive Dependency Management

```powershell
# Open interactive PDM shell
.\manage-python-project-dependencies.ps1
```

Inside the Docker container, you can use all PDM commands:

```bash
# Add packages
pdm add requests
pdm add fastapi uvicorn

# Add development dependencies
pdm add pytest --dev
pdm add black --dev

# Remove packages
pdm remove old-package

# Update dependencies
pdm update

# List installed packages
pdm list

# Exit when done
exit
```

### After Managing Dependencies

```powershell
# Start the backend with updated dependencies
docker compose up --build
```

## 🧪 Testing Python Version

```powershell
# Test your Python version configuration
.\test-python-version.ps1
```

This verifies:
- Docker is installed and running
- `.env` file has correct `PYTHON_VERSION`
- Main Dockerfile builds successfully
- Dependency management Dockerfile builds successfully
- All docker-compose files work correctly

## 📋 Available Scripts

### PowerShell Scripts (Windows Native)

| Script | Purpose |
|--------|---------|
| `.\quick-start.ps1` | Complete onboarding and setup |
| `.\manage-python-project-dependencies.ps1` | Interactive PDM dependency management |
| `.\test-python-version.ps1` | Test Python version configuration |

### Bash Scripts (Optional - for WSL/Git Bash users)

| Script | Purpose |
|--------|---------|
| `./quick-start.sh` | Bash version of quick-start |
| `./manage-python-project-dependencies.sh` | Bash version of dependency management |
| `./test-python-version.sh` | Bash version of version test |

**Note:** You can use either PowerShell or bash scripts - they provide identical functionality!

## 🔧 Common Workflows

### 1. First Time Setup
```powershell
.\quick-start.ps1
# Choose option 3 on subsequent runs for dependency management + backend start
```

### 2. Add a New Package
```powershell
# Open dependency management
.\manage-python-project-dependencies.ps1

# Inside the container:
pdm add new-package
exit

# Rebuild and start backend
docker compose up --build
```

### 3. Update All Dependencies
```powershell
.\manage-python-project-dependencies.ps1

# Inside the container:
pdm update
exit

docker compose up --build
```

### 4. Troubleshoot Configuration
```powershell
# Test your setup
.\test-python-version.ps1

# Check .env file
Get-Content .env

# Verify Docker
docker --version
docker info
```

## 🐳 How It Works

All dependency management runs **inside Docker containers**, so you don't need:
- ❌ Local Python installation
- ❌ Local pip, PDM, or Poetry
- ❌ Bash, WSL, or Git Bash
- ❌ pipx or other Python tools

You only need:
- ✅ Docker Desktop
- ✅ PowerShell (built into Windows)

The PowerShell scripts use Docker commands to:
1. Build a Python 3.13 container with PDM, Poetry, and uv
2. Mount your project directory into the container
3. Run dependency management commands inside the container
4. Persist all changes to your local files

## 💡 Tips for Windows Users

### PowerShell Execution Policy

If you get an execution policy error, run PowerShell as Administrator and execute:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Docker Desktop Settings

Ensure Docker Desktop is configured to:
- Start on Windows startup (optional, but convenient)
- Use WSL 2 backend (recommended for better performance)
- Share the drive where your project is located

### File Paths

The scripts use Windows-style paths (`.\script.ps1`) automatically. No need to convert paths manually.

### Line Endings

If you edit files in the container and see issues, ensure your Git is configured for proper line endings:

```powershell
git config --global core.autocrlf true
```

## 🆚 PowerShell vs Bash Scripts

Both script versions provide **identical functionality**:

| Feature | PowerShell | Bash |
|---------|-----------|------|
| Dependency Management | ✅ | ✅ |
| Python Version Testing | ✅ | ✅ |
| Quick Start | ✅ | ✅ |
| Docker Integration | ✅ | ✅ |
| Interactive PDM Shell | ✅ | ✅ |
| Initial Setup Mode | ✅ | ✅ |

**Choose based on your preference:**
- Use PowerShell scripts for native Windows experience
- Use bash scripts if you have WSL/Git Bash and prefer bash syntax

## 🚨 Troubleshooting

### "Docker is not running"
```powershell
# Start Docker Desktop from the Start menu
# Or check if Docker service is running:
Get-Service docker
```

### "Execution policy" error
```powershell
# Run as Administrator:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "Cannot find path" error
```powershell
# Ensure you're in the project root directory:
cd d:\Development\Code\python\python-api-template
.\quick-start.ps1
```

### Container build fails
```powershell
# Check your .env file:
Get-Content .env

# Verify PYTHON_VERSION is set:
# PYTHON_VERSION=3.13

# Test configuration:
.\test-python-version.ps1
```

### PDM commands not found in container
```powershell
# Rebuild the dependency management container:
$env:PDM_MANAGER_PROJECT_ROOT = (Get-Location).Path
docker compose -f tools/core-pdm-manager/docker/docker-compose.pdm-manager.yml build --no-cache

# Try again:
.\manage-python-project-dependencies.ps1
```

## 📚 Additional Resources

- **Main README:** `README.md`
- **Dependency Management Details:** `tools/core-pdm-manager/docs/HOST_INTEGRATION_GUIDE.md`
- **Database Configuration:** `docs/DATABASE.md`
- **Architecture Overview:** `docs/ARCHITECTURE.md`

## 🎉 Summary

Windows users now have **first-class support** for PDM dependency management:
- No bash required
- Native PowerShell scripts
- Full Docker integration
- Identical functionality to Linux/Mac
- Easy onboarding and maintenance

**Enjoy modern Python development on Windows!** 🐍🪟
