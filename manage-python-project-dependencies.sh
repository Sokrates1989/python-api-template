#!/bin/bash
#
# manage-python-project-dependencies.sh
#
# This script automates the setup and interactive use of a Dockerized Python dependency management environment.
# Usage: ./manage-python-project-dependencies.sh
#
# - Builds the dev Docker image (if needed)
# - Runs the setup script to generate poetry.lock and pdm.lock
# - Drops the user into an interactive shell with Poetry and PDM ready to use
# - All changes persist in your project directory

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_color() {
    color=$1
    message=$2
    echo -e "${color}${message}${NC}"
}

print_color $BLUE "🐳 Python Dependency Management with Docker"

# Change to the python-dependency-management directory
cd python-dependency-management

# Check if config.env exists, if not create it from example
if [ ! -f "config.env" ]; then
    if [ -f "config.env.example" ]; then
        print_color $YELLOW "📝 config.env not found. Creating from config.env.example..."
        cp config.env.example config.env
        print_color $GREEN "✅ Created config.env from example template"
    else
        print_color $RED "❌ Neither config.env nor config.env.example found!"
        exit 1
    fi
else
    print_color $GREEN "✅ config.env found"
fi

# Show current configuration
print_color $BLUE "📋 Current configuration:"
echo ""
while IFS= read -r line; do
    # Skip empty lines and comments
    if [[ ! -z "$line" && ! "$line" =~ ^[[:space:]]*# ]]; then
        print_color $YELLOW "  $line"
    fi
done < config.env
echo ""

# Ask user if they want to proceed or modify config
print_color $BLUE "Do you want to proceed with this configuration?"
print_color $YELLOW "  [y] Yes, proceed with current config"
print_color $YELLOW "  [n] No, let me modify config.env first"
echo ""
read -p "Enter your choice (y/n): " choice

case $choice in
    [Yy]|[Yy][Ee][Ss]|"")
        print_color $GREEN "✅ Proceeding with current configuration..."
        ;;
    [Nn]|[Nn][Oo])
        print_color $YELLOW "📝 Please edit python-dependency-management/config.env and run this script again."
        print_color $YELLOW "💡 You can use: nano python-dependency-management/config.env"
        exit 0
        ;;
    *)
        print_color $RED "❌ Invalid choice. Please run the script again and choose y or n."
        exit 1
        ;;
esac

print_color $YELLOW "[python-dependency-management] Building dev environment Docker image..."

# Build the Docker image
docker-compose build

print_color $YELLOW "[python-dependency-management] Running setup script to generate lock files..."

# Run the setup script in a container
docker-compose run --rm dev ./python-dependency-management/dev-setup.sh

print_color $GREEN "[python-dependency-management] Setup complete!"
print_color $BLUE "🚀 Dropping you into an interactive shell with Poetry and PDM ready to use..."

print_color $BLUE "💡 Common PDM Commands & Use Cases:"
print_color $YELLOW ""
print_color $YELLOW "📦 Basic Package Management:"
print_color $YELLOW "  pdm add requests                    # Add a package"
print_color $YELLOW "  pdm add \"requests>=2.28.0\"         # Add with version constraint"
print_color $YELLOW "  pdm add pytest --dev               # Add development dependency"
print_color $YELLOW "  pdm remove requests                 # Remove a package"
print_color $YELLOW "  pdm install                         # Install all dependencies"
print_color $YELLOW "  pdm list                            # List installed packages"
print_color $YELLOW ""
print_color $YELLOW "🔄 Dependency Management:"
print_color $YELLOW "  pdm update                          # Update all dependencies"
print_color $YELLOW "  pdm update requests                 # Update specific package"
print_color $YELLOW "  pdm lock                            # Update lock file"
print_color $YELLOW "  pdm lock --check                    # Check if lock file is up-to-date"
print_color $YELLOW "  pdm sync                            # Sync environment with lock file"
print_color $YELLOW ""
print_color $YELLOW "🔧 Troubleshooting & Conflicts:"
print_color $YELLOW "  pdm lock --update-reuse             # Update lock with conflict resolution"
print_color $YELLOW "  pdm install --no-lock               # Install without updating lock file"
print_color $YELLOW "  pdm cache clear                     # Clear package cache"
print_color $YELLOW "  pdm info                            # Show project information"
print_color $YELLOW "  pdm info requests                   # Show package details"
print_color $YELLOW ""
print_color $YELLOW "🐍 Python Version Management:"
print_color $YELLOW "  pdm python list                     # List available Python versions"
print_color $YELLOW "  pdm python install 3.12             # Install specific Python version"
print_color $YELLOW "  pdm use 3.12                        # Switch to Python 3.12"
print_color $YELLOW ""
print_color $YELLOW "🚀 Running Scripts:"
print_color $YELLOW "  pdm run python script.py            # Run script with project dependencies"
print_color $YELLOW "  pdm run pytest                      # Run tests"
print_color $YELLOW "  pdm run --list                      # List available scripts"
print_color $YELLOW ""
print_color $YELLOW "🔍 Debugging Dependency Issues:"
print_color $YELLOW "  pdm show --graph                    # Show dependency tree"
print_color $YELLOW "  pdm show --reverse requests         # Show what depends on requests"
print_color $YELLOW "  pdm export -f requirements          # Export to requirements.txt format"
print_color $YELLOW "  pdm import requirements.txt         # Import from requirements.txt"
print_color $YELLOW ""
print_color $YELLOW "⚡ Quick Fixes for Common Issues:"
print_color $YELLOW "  # Dependency conflict resolution:"
print_color $YELLOW "  pdm lock --update-reuse --resolution=highest"
print_color $YELLOW ""
print_color $YELLOW "  # Force reinstall all packages:"
print_color $YELLOW "  pdm sync --reinstall"
print_color $YELLOW ""
print_color $YELLOW "  # Install from fresh lock file:"
print_color $YELLOW "  rm pdm.lock && pdm lock && pdm install"
print_color $YELLOW ""
print_color $YELLOW "Type 'exit' to leave the container when done."
print_color $YELLOW ""

# Start interactive shell in a clean container
docker-compose run --rm dev 