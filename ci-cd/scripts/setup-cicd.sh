#!/bin/bash
#
# setup-cicd.sh
#
# Interactive CI/CD Pipeline Setup Script
# Guides users through setting up CI/CD for GitHub or GitLab with deployment to Linux/Swarm or Azure

set -e

echo "🚀 CI/CD Pipeline Setup Wizard"
echo "================================"
echo ""
echo "This wizard will guide you through setting up a complete CI/CD pipeline"
echo "for your Python API project."
echo ""

# Check if running in Docker
if [ ! -f /.dockerenv ] && [ ! -f /run/.containerenv ]; then
    echo "⚠️  This script should be run via docker-compose"
    echo "Please use: docker compose -f ci-cd/docker-compose.cicd-setup.yml run --rm cicd-setup"
    exit 1
fi

# Load environment variables from .env
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please create .env from config/.env.template first"
    echo "You can run: cp config/.env.template .env"
    exit 1
fi

# Source .env file (filter out comments and empty lines)
set -a
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ ! "$line" =~ = ]] && continue
    
    key=$(echo "$line" | cut -d= -f1 | xargs)
    value=$(echo "$line" | cut -d= -f2- | sed 's/#.*//' | xargs)
    
    [[ -z "$key" || "$key" =~ [[:space:]] ]] && continue
    
    export "$key=$value"
done < .env
set +a

# ============================================================================
# STEP 1: Choose CI/CD Platform
# ============================================================================
echo "📋 STEP 1: Choose Your CI/CD Platform"
echo "======================================="
echo ""
echo "Which CI/CD platform would you like to use?"
echo "1) GitHub Actions"
echo "2) GitLab CI/CD"
echo ""
read -p "Your choice (1-2): " cicd_platform

case $cicd_platform in
    1)
        PLATFORM="github"
        PLATFORM_NAME="GitHub Actions"
        ;;
    2)
        PLATFORM="gitlab"
        PLATFORM_NAME="GitLab CI/CD"
        ;;
    *)
        echo "❌ Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "✅ Selected: $PLATFORM_NAME"
echo ""

# ============================================================================
# STEP 2: Choose Deployment Target
# ============================================================================
echo "📋 STEP 2: Choose Your Deployment Target"
echo "=========================================="
echo ""
echo "Where would you like to deploy your application?"
echo "1) Linux Server / Docker Swarm Cluster"
echo "2) Azure Container Instances"
echo "3) Azure App Service"
echo "4) Build Only (no automatic deployment)"
echo ""
read -p "Your choice (1-4): " deploy_target

case $deploy_target in
    1)
        DEPLOYMENT="linux-swarm"
        DEPLOYMENT_NAME="Linux Server / Docker Swarm"
        ;;
    2)
        DEPLOYMENT="azure-aci"
        DEPLOYMENT_NAME="Azure Container Instances"
        ;;
    3)
        DEPLOYMENT="azure-appservice"
        DEPLOYMENT_NAME="Azure App Service"
        ;;
    4)
        DEPLOYMENT="build-only"
        DEPLOYMENT_NAME="Build Only (No Deployment)"
        ;;
    *)
        echo "❌ Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "✅ Selected: $DEPLOYMENT_NAME"
echo ""

# ============================================================================
# STEP 3: Configure CI Environment
# ============================================================================
echo "📋 STEP 3: Configure CI/CD Environment"
echo "========================================"
echo ""

# Check if .ci.env already exists
if [ -f .ci.env ]; then
    echo "⚠️  .ci.env already exists"
    read -p "Do you want to reconfigure it? (y/N): " reconfigure
    if [[ ! "$reconfigure" =~ ^[Yy]$ ]]; then
        echo "Using existing .ci.env configuration"
        SKIP_CI_ENV=true
    fi
fi

if [ "$SKIP_CI_ENV" != "true" ]; then
    # Copy template
    cp ci-cd/.ci.env.template .ci.env
    
    # Configure IMAGE_NAME
    echo "🐳 Docker Image Configuration"
    echo "------------------------------"
    echo ""
    echo "Current IMAGE_NAME from .env: $IMAGE_NAME"
    echo ""
    echo "This should be your Docker registry image name."
    echo "Examples:"
    echo "  - Docker Hub: username/api-name"
    echo "  - GitHub Container Registry: ghcr.io/username/api-name"
    echo "  - GitLab Container Registry: registry.gitlab.com/username/project/api-name"
    echo ""
    read -p "Enter Docker image name [$IMAGE_NAME]: " new_image_name
    
    if [ -n "$new_image_name" ]; then
        IMAGE_NAME="$new_image_name"
    fi
    
    # Update .ci.env
    sed -i "s|^IMAGE_NAME=.*|IMAGE_NAME=$IMAGE_NAME|" .ci.env
    
    # Configure IMAGE_VERSION
    echo ""
    echo "Current IMAGE_VERSION from .env: $IMAGE_VERSION"
    read -p "Enter initial image version [$IMAGE_VERSION]: " new_version
    
    if [ -n "$new_version" ]; then
        IMAGE_VERSION="$new_version"
    fi
    
    sed -i "s/^IMAGE_VERSION=.*/IMAGE_VERSION=$IMAGE_VERSION/" .ci.env
    
    # Configure PYTHON_VERSION
    echo ""
    echo "Current PYTHON_VERSION from .env: $PYTHON_VERSION"
    read -p "Enter Python version [$PYTHON_VERSION]: " new_python_version
    
    if [ -n "$new_python_version" ]; then
        PYTHON_VERSION="$new_python_version"
    fi
    
    sed -i "s/^PYTHON_VERSION=.*/PYTHON_VERSION=$PYTHON_VERSION/" .ci.env
    
    echo ""
    echo "✅ .ci.env configured successfully"
fi

echo ""

# ============================================================================
# STEP 4: Configure Deployment Settings
# ============================================================================
if [ "$DEPLOYMENT" != "build-only" ]; then
    echo "📋 STEP 4: Configure Deployment Settings"
    echo "=========================================="
    echo ""
    
    case $DEPLOYMENT in
        linux-swarm)
            echo "🖥️  Linux Server / Docker Swarm Configuration"
            echo "----------------------------------------------"
            echo ""
            read -p "Enter deployment server hostname or IP: " deploy_server
            read -p "Enter deployment server SSH user: " deploy_user
            read -p "Enter deployment path on server [/opt/api]: " deploy_path
            deploy_path=${deploy_path:-/opt/api}
            
            # Add to .ci.env
            echo "" >> .ci.env
            echo "# Deployment Configuration" >> .ci.env
            echo "DEPLOY_SERVER=$deploy_server" >> .ci.env
            echo "DEPLOY_USER=$deploy_user" >> .ci.env
            echo "DEPLOY_PATH=$deploy_path" >> .ci.env
            ;;
        azure-aci)
            echo "☁️  Azure Container Instances Configuration"
            echo "-------------------------------------------"
            echo ""
            read -p "Enter Azure Resource Group name: " azure_rg
            read -p "Enter Azure Container Instance name: " azure_aci_name
            read -p "Enter Azure location [westeurope]: " azure_location
            azure_location=${azure_location:-westeurope}
            
            # Add to .ci.env
            echo "" >> .ci.env
            echo "# Azure Deployment Configuration" >> .ci.env
            echo "AZURE_RESOURCE_GROUP=$azure_rg" >> .ci.env
            echo "AZURE_CONTAINER_NAME=$azure_aci_name" >> .ci.env
            echo "AZURE_LOCATION=$azure_location" >> .ci.env
            ;;
        azure-appservice)
            echo "☁️  Azure App Service Configuration"
            echo "------------------------------------"
            echo ""
            read -p "Enter Azure Resource Group name: " azure_rg
            read -p "Enter Azure App Service name: " azure_app_name
            read -p "Enter Azure location [westeurope]: " azure_location
            azure_location=${azure_location:-westeurope}
            
            # Add to .ci.env
            echo "" >> .ci.env
            echo "# Azure Deployment Configuration" >> .ci.env
            echo "AZURE_RESOURCE_GROUP=$azure_rg" >> .ci.env
            echo "AZURE_APP_NAME=$azure_app_name" >> .ci.env
            echo "AZURE_LOCATION=$azure_location" >> .ci.env
            ;;
    esac
    
    echo ""
    echo "✅ Deployment settings configured"
    echo ""
fi

# ============================================================================
# STEP 5: Copy Pipeline Configuration Files
# ============================================================================
echo "📋 STEP 5: Copy Pipeline Configuration Files"
echo "=============================================="
echo ""

case $PLATFORM in
    github)
        # Create .github/workflows directory if it doesn't exist
        mkdir -p .github/workflows
        
        # Copy appropriate workflow file
        if [ "$DEPLOYMENT" = "linux-swarm" ]; then
            cp ci-cd/templates/github/build-deploy-linux.yml .github/workflows/ci-cd.yml
        elif [ "$DEPLOYMENT" = "azure-aci" ]; then
            cp ci-cd/templates/github/build-deploy-azure-aci.yml .github/workflows/ci-cd.yml
        elif [ "$DEPLOYMENT" = "azure-appservice" ]; then
            cp ci-cd/templates/github/build-deploy-azure-app.yml .github/workflows/ci-cd.yml
        else
            cp ci-cd/templates/github/build-and-push.yml.example .github/workflows/ci-cd.yml
        fi
        
        echo "✅ Created .github/workflows/ci-cd.yml"
        ;;
    gitlab)
        # Copy appropriate GitLab CI file
        if [ "$DEPLOYMENT" = "linux-swarm" ]; then
            cp ci-cd/templates/gitlab/.gitlab-ci-linux.yml .gitlab-ci.yml
        elif [ "$DEPLOYMENT" = "azure-aci" ]; then
            cp ci-cd/templates/gitlab/.gitlab-ci-azure-aci.yml .gitlab-ci.yml
        elif [ "$DEPLOYMENT" = "azure-appservice" ]; then
            cp ci-cd/templates/gitlab/.gitlab-ci-azure-app.yml .gitlab-ci.yml
        else
            cp ci-cd/templates/gitlab/.gitlab-ci.yml.example .gitlab-ci.yml
        fi
        
        echo "✅ Created .gitlab-ci.yml"
        ;;
esac

# Copy deployment files if needed
if [ "$DEPLOYMENT" = "linux-swarm" ]; then
    cp ci-cd/templates/deployment/docker-compose.prod.yml docker-compose.prod.yml
    echo "✅ Created docker-compose.prod.yml"
fi

echo ""

# ============================================================================
# STEP 6: Display Required Secrets/Variables
# ============================================================================
echo "📋 STEP 6: Required Secrets and Variables"
echo "==========================================="
echo ""

echo "You need to configure the following secrets/variables in your $PLATFORM_NAME:"
echo ""

# Common secrets
echo "🔐 Required Secrets:"
echo "-------------------"
echo ""
echo "1. DOCKER_USERNAME"
echo "   Current local value: (Docker Hub username)"
echo "   Description: Your Docker registry username"
echo "   ⚠️  Action: Set this in $PLATFORM_NAME secrets"
echo ""
echo "2. DOCKER_PASSWORD"
echo "   Current local value: (hidden for security)"
echo "   Description: Your Docker registry password or access token"
echo "   ⚠️  Action: Set this in $PLATFORM_NAME secrets"
echo "   💡 Tip: Use an access token instead of your password"
echo ""

# Platform-specific instructions
case $PLATFORM in
    github)
        echo "📍 Where to add secrets in GitHub:"
        echo "   1. Go to your repository on GitHub"
        echo "   2. Click 'Settings' → 'Secrets and variables' → 'Actions'"
        echo "   3. Click 'New repository secret'"
        echo "   4. Add each secret listed above"
        echo ""
        ;;
    gitlab)
        echo "📍 Where to add variables in GitLab:"
        echo "   1. Go to your project on GitLab"
        echo "   2. Click 'Settings' → 'CI/CD'"
        echo "   3. Expand 'Variables' section"
        echo "   4. Click 'Add variable'"
        echo "   5. Add each variable listed above"
        echo "   6. Make sure to check 'Mask variable' for sensitive values"
        echo ""
        ;;
esac

# Deployment-specific secrets
if [ "$DEPLOYMENT" = "linux-swarm" ]; then
    echo "3. SSH_PRIVATE_KEY"
    echo "   Description: SSH private key for deployment server access"
    echo "   Current server: $deploy_server"
    echo "   ⚠️  Action: Generate SSH key pair and add private key to secrets"
    echo "   💡 Tip: Run 'ssh-keygen -t ed25519 -C \"ci-cd-deploy\"' to generate"
    echo ""
    echo "4. SSH_KNOWN_HOSTS (Optional but recommended)"
    echo "   Description: Known hosts entry for your server"
    echo "   💡 Tip: Run 'ssh-keyscan $deploy_server' to get the value"
    echo ""
elif [ "$DEPLOYMENT" = "azure-aci" ] || [ "$DEPLOYMENT" = "azure-appservice" ]; then
    echo "3. AZURE_CREDENTIALS"
    echo "   Description: Azure service principal credentials (JSON format)"
    echo "   ⚠️  Action: Create service principal and add credentials to secrets"
    echo "   💡 Tip: Run 'az ad sp create-for-rbac --name \"cicd-deploy\" --role contributor --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group} --sdk-auth'"
    echo ""
fi

echo ""
echo "📋 Environment Variables from .env (for reference):"
echo "----------------------------------------------------"
echo ""
echo "These values are currently used locally. Review if they should be"
echo "used in CI/CD or if different values are needed:"
echo ""
echo "  IMAGE_NAME=$IMAGE_NAME"
echo "  IMAGE_VERSION=$IMAGE_VERSION"
echo "  PYTHON_VERSION=$PYTHON_VERSION"
echo "  PORT=$PORT"
echo "  DATABASE_URL=$DATABASE_URL (⚠️  Use different DB in production!)"
echo "  REDIS_URL=$REDIS_URL (⚠️  Use different Redis in production!)"
echo "  DEBUG=$DEBUG (⚠️  Should be 'false' in production!)"
echo "  ADMIN_API_KEY=$ADMIN_API_KEY (⚠️  Generate new key for production!)"
echo ""
echo "⚠️  IMPORTANT: Never use development credentials in production!"
echo ""

# ============================================================================
# STEP 7: Next Steps
# ============================================================================
echo "📋 STEP 7: Next Steps"
echo "====================="
echo ""
echo "✅ CI/CD pipeline configuration is complete!"
echo ""
echo "🚀 To activate your pipeline:"
echo ""
echo "1. Add the required secrets/variables to $PLATFORM_NAME (see above)"
echo ""

if [ "$DEPLOYMENT" = "linux-swarm" ]; then
    echo "2. Set up your deployment server:"
    echo "   - Install Docker and Docker Compose on $deploy_server"
    echo "   - Add the CI/CD public SSH key to ~/.ssh/authorized_keys"
    echo "   - Create deployment directory: mkdir -p $deploy_path"
    echo "   - Copy docker-compose.prod.yml to $deploy_path"
    echo ""
fi

echo "3. Commit and push your changes:"
echo "   git add .ci.env .github/ .gitlab-ci.yml docker-compose.prod.yml"
echo "   git commit -m \"Add CI/CD pipeline configuration\""
echo "   git push origin main"
echo ""
echo "4. Your pipeline will automatically run on push to main/master branch"
echo ""
echo "5. Monitor the pipeline:"
if [ "$PLATFORM" = "github" ]; then
    echo "   - Go to 'Actions' tab in your GitHub repository"
elif [ "$PLATFORM" = "gitlab" ]; then
    echo "   - Go to 'CI/CD' → 'Pipelines' in your GitLab project"
fi
echo ""

echo "📚 Additional Resources:"
echo "------------------------"
echo "  - CI/CD documentation: ci-cd/README.md"
echo "  - Troubleshooting guide: ci-cd/TROUBLESHOOTING.md"
echo "  - Example configurations: ci-cd/templates/"
echo ""

echo "🎉 Setup complete! Your CI/CD pipeline is ready to use."
echo ""
