#!/bin/bash

# Test script to verify Python version configuration

# Change to project root (script is in python-dependency-management/scripts/)
cd "$(dirname "$0")/../.."

# Function to provide diagnostic information
provide_diagnostics() {
    echo ""
    echo "🔧 Diagnostic Information:"
    echo "=========================="
    
    # Check Docker
    if command -v docker &> /dev/null; then
        echo "✅ Docker is installed"
        if docker info &> /dev/null; then
            echo "✅ Docker is running"
        else
            echo "❌ Docker is not running"
        fi
    else
        echo "❌ Docker is not installed"
    fi
    
    # Check .env file
    if [ -f .env ]; then
        echo "✅ .env file exists"
        if grep -q "PYTHON_VERSION" .env; then
            echo "✅ PYTHON_VERSION is defined in .env"
            echo "   Current value: $(grep PYTHON_VERSION .env)"
        else
            echo "❌ PYTHON_VERSION not found in .env"
        fi
    else
        echo "❌ .env file does not exist"
    fi
    
    # Check required files
    if [ -f Dockerfile ]; then
        echo "✅ Main Dockerfile exists"
    else
        echo "❌ Main Dockerfile missing"
    fi
    
    if [ -f python-dependency-management/Dockerfile ]; then
        echo "✅ Dependency management Dockerfile exists"
    else
        echo "❌ Dependency management Dockerfile missing"
    fi
    
    if [ -f docker/docker-compose.yml ]; then
        echo "✅ Main docker-compose.yml exists"
    else
        echo "❌ Main docker/docker-compose.yml missing"
    fi
    
    if [ -f docker/docker-compose-python-dependency-management.yml ]; then
        echo "✅ Dependency management docker-compose.yml exists"
    else
        echo "❌ Dependency management docker/docker-compose-python-dependency-management.yml missing"
    fi
}

echo "🔍 Testing Python version configuration..."
echo "=========================================="

# Load environment variables
if [ -f .env ]; then
    source .env
    echo "✅ Loaded .env file"
    echo "  PYTHON_VERSION: $PYTHON_VERSION"
else
    echo "❌ .env file not found"
    echo "   Please ensure .env file exists in the project root"
    provide_diagnostics
    exit 1
fi

# Test main Dockerfile
echo ""
echo "🐳 Testing main Dockerfile..."
if docker build --build-arg PYTHON_VERSION=$PYTHON_VERSION -t test-main . > /dev/null 2>&1; then
    echo "✅ Main Dockerfile builds successfully with Python $PYTHON_VERSION"
else
    echo "❌ Main Dockerfile build failed"
    echo "   Error: Docker build failed for main application"
    echo "   Possible causes:"
    echo "   - Docker not running"
    echo "   - Invalid PYTHON_VERSION in .env file"
    echo "   - Network connectivity issues"
    echo "   - Insufficient disk space"
    provide_diagnostics
    return 1
fi

# Test python-dependency-management Dockerfile
echo ""
echo "🐳 Testing python-dependency-management Dockerfile..."
cd python-dependency-management
if docker build --build-arg PYTHON_VERSION=$PYTHON_VERSION -t test-dev . > /dev/null 2>&1; then
    echo "✅ Dependency management Dockerfile builds successfully with Python $PYTHON_VERSION"
else
    echo "❌ Dependency management Dockerfile build failed"
    echo "   Error: Docker build failed for dependency management"
    echo "   Possible causes:"
    echo "   - Docker not running"
    echo "   - Invalid PYTHON_VERSION in .env file"
    echo "   - Network connectivity issues"
    echo "   - Insufficient disk space"
    cd ..
    provide_diagnostics
    return 1
fi
cd ..

# Test docker-compose builds
echo ""
echo "🐳 Testing docker-compose builds..."
if docker-compose -f docker/docker-compose.yml build --no-cache > /dev/null 2>&1; then
    echo "✅ Main docker-compose builds successfully"
else
    echo "❌ Main docker/docker-compose.yml build failed"
    echo "   Error: Docker compose build failed for main application"
    echo "   Possible causes:"
    echo "   - Docker not running"
    echo "   - Invalid environment variables in .env file"
    echo "   - Network connectivity issues"
    echo "   - Insufficient disk space"
    provide_diagnostics
    return 1
fi

if docker-compose -f docker/docker-compose-python-dependency-management.yml build --no-cache > /dev/null 2>&1; then
    echo "✅ Dependency management docker-compose builds successfully"
else
    echo "❌ Dependency management docker/docker-compose-python-dependency-management.yml build failed"
    echo "   Error: Docker compose build failed for dependency management"
    echo "   Possible causes:"
    echo "   - Docker not running"
    echo "   - Invalid environment variables in .env file"
    echo "   - Network connectivity issues"
    echo "   - Insufficient disk space"
    provide_diagnostics
    return 1
fi

echo ""
echo "🎉 Python version configuration test completed!"
echo "==============================================" 