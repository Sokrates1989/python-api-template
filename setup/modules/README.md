# Quick-Start Modules

This directory contains the Bash modules used by `quick-start.sh`. On Windows,
`quick-start.ps1` is only a WSL handoff and executes the same Bash menu; it does
not own a second runtime implementation.

## Module Structure

The modular approach separates concerns and makes the quick-start scripts more maintainable and testable.

### Available Modules

#### 1. `docker_helpers.sh`
**Purpose:** Docker installation and configuration checks

**Functions:**
- `check_docker_installation()` - Verifies Docker, Docker daemon, and Docker Compose are installed and running
- `read_env_variable()` - Reads environment variables from .env files
- `determine_compose_file()` - Determines which Docker Compose file to use based on database type and mode

#### 2. `version_manager.sh`
**Purpose:** Semantic versioning and image version management

**Functions:**
- `bump_semver()` - Computes a patch, feature/minor, or major increment
- `select_semver_version()` - Owns the baseline-aware `1/k`, `2/p`, `3/f`, `4/m`, `5/e` selector and optional coordinated patch target
- `update_image_version_in_file()` - Updates IMAGE_VERSION in a specific file
- `update_image_version()` - Uses the shared selector for .env and .ci.env maintenance

#### 3. `menu_handlers.sh`
**Purpose:** Menu action handlers for the quick-start script

**Functions:**
- `handle_backend_start()` - Starts the backend with Docker Compose
- `handle_dependency_management()` - Opens dependency management menu
- `handle_dependency_and_backend()` - Runs dependency management then starts backend
- `handle_python_version_test()` - Tests Python version configuration
- `handle_keycloak_bootstrap()` - Runs the Keycloak realm bootstrap (bash only)
- `handle_build_production_image()` - Publishes either a stable or production-connected test API image
- `run_api_release_stack_plan()` - Resolves the shared baseline and selected API's next required version
- `handle_cicd_setup()` - Sets up CI/CD pipeline

#### 4. `bootstrap_utils.sh`
**Purpose:** Docker-based Keycloak realm bootstrap utilities

**Functions:**
- `run_keycloak_bootstrap()` - Builds and runs the bootstrap container to create realms, clients, roles, and users

## Usage in Quick-Start Scripts

### Bash (quick-start.sh)
```bash
# Source modules at the beginning of the script
source "${SETUP_DIR}/modules/docker_helpers.sh"
source "${SETUP_DIR}/modules/version_manager.sh"
source "${SETUP_DIR}/modules/menu_handlers.sh"

# Use module functions
if ! check_docker_installation; then
    exit 1
fi
```

### Windows (`quick-start.ps1`)

The PowerShell entry point validates WSL and forwards arguments to
`quick-start.sh`. Historical `.ps1` modules are retained only for compatibility
and must not receive new menu behavior.

## Benefits of Modular Approach

1. **Maintainability** - Each module focuses on a single responsibility
2. **Reusability** - Functions can be reused across different scripts
3. **Testability** - Individual modules can be tested in isolation
4. **Readability** - Main scripts are cleaner and easier to understand
5. **Scalability** - New features can be added as new modules without cluttering main scripts

## Adding New Modules

To add a new module:

1. Create one documented `.sh` module in this directory.
2. Source it from the authoritative Bash module graph.
3. Add a focused Bash test for reusable behavior.
4. Document the module functions in this README.

## Module Naming Convention

- Use lowercase with underscores for bash files: `module_name.sh`
- Keep new runtime modules in Bash so Windows and Linux share one behavior.
- Use descriptive function names that clearly indicate their purpose
- Keep numeric and named menu contracts stable across every caller.
