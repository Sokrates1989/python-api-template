# DEPRECATED: Old CI/CD Setup Script

⚠️ **This directory contains the deprecated monolithic setup script.**

## Migration Notice

The CI/CD setup has been refactored into a modular architecture for better maintainability.

### Old Location (Deprecated)
```
ci-cd/scripts/setup-cicd.sh  ❌ DEPRECATED
```

### New Location (Current)
```
ci-cd/setup/
├── setup-cicd-wizard.sh      ✅ Main orchestrator
└── modules/                   ✅ Modular components
    ├── git-detector.sh
    ├── branch-selector.sh
    ├── platform-config.sh
    ├── deployment-config.sh
    ├── secret-manager.sh
    ├── template-builder.sh
    └── user-prompts.sh
```

## Why the Change?

The old `setup-cicd.sh` script had grown to **436 lines** and was becoming unmaintainable:

- ❌ Single file with multiple responsibilities
- ❌ Difficult to test individual features
- ❌ Hard to extend with new functionality
- ❌ No code reuse between functions

The new modular structure provides:

- ✅ **Single Responsibility**: Each module handles one concern
- ✅ **Maintainability**: Small, focused files (100-200 lines each)
- ✅ **Reusability**: Functions can be sourced independently
- ✅ **Testability**: Modules can be tested in isolation
- ✅ **Extensibility**: Easy to add new features

## How to Use the New Setup

The usage remains the same:

```bash
# Via quick-start menu (option 6)
./quick-start.sh

# Or directly
docker compose -f ci-cd/docker-compose.cicd-setup.yml run --rm cicd-setup
```

The new wizard provides:

1. **Automatic git detection** - Builds repository URLs automatically
2. **Branch selection** - Choose which branches trigger CI/CD
3. **Step-by-step secrets** - Guided secret creation with security warnings
4. **Simplified .ci.env** - Only contains IMAGE_VERSION (as intended)
5. **Better UX** - Clear sections, confirmation steps, progress indicators

## For Developers

If you need to modify the CI/CD setup:

1. **Don't edit** `ci-cd/scripts/setup-cicd.sh` (deprecated)
2. **Do edit** the appropriate module in `ci-cd/setup/modules/`
3. See `ci-cd/setup/modules/README.md` for module documentation

## Timeline

- **Deprecated**: November 2025
- **Removal**: Will be removed in a future version
- **Support**: Use the new modular setup going forward

## Questions?

See the documentation:
- `ci-cd/setup/README.md` - Architecture overview
- `ci-cd/setup/modules/README.md` - Module documentation
