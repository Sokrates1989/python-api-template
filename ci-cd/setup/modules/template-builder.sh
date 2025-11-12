#!/bin/bash
# Template builder module
# Builds CI/CD configuration files from templates

# Build .ci.env file (only IMAGE_VERSION)
# Usage: build_ci_env "0.1.4" "/path/to/project"
build_ci_env() {
    local image_version="$1"
    local project_root="$2"
    
    echo "⚙️  Building .ci.env..." >&2
    
    cat > "$project_root/.ci.env" << EOF
IMAGE_VERSION=$image_version
EOF
    
    success_message ".ci.env created with IMAGE_VERSION=$image_version"
}

# Build GitHub Actions workflow
# Usage: build_github_workflow "linux-swarm" "main develop" "/path/to/project" "deploy_config"
build_github_workflow() {
    local deployment_target="$1"
    local branches="$2"
    local project_root="$3"
    local deploy_config="$4"
    
    section_header "STEP 4: Building CI/CD Configuration Files"
    
    echo "⚙️  Creating GitHub Actions workflow..." >&2
    
    # Create .github/workflows directory
    mkdir -p "$project_root/.github/workflows"
    
    # Format branches for YAML
    local branches_yaml=$(format_branches_github "$branches")
    
    # Create workflow file
    cat > "$project_root/.github/workflows/ci-cd.yml" << 'EOF'
name: 🚀 CI/CD Pipeline

on:
  push:
    branches: ##BRANCHES##

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    env:
      IMAGE_NAME: ${{ vars.IMAGE_NAME }}

    steps:
      - name: ⬇️ Checkout Code
        uses: actions/checkout@v4

      - name: 🧪 Load CI Environment Variables
        run: |
          while IFS='=' read -r key value
          do
            echo "$key=$value" >> $GITHUB_ENV
          done < .ci.env
      
      - name: 🔍 Debug ENV values
        run: |
          echo "IMAGE_NAME=$IMAGE_NAME"
          echo "IMAGE_VERSION=$IMAGE_VERSION"
          
      - name: 🐳 Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: 🔐 Docker Login
        run: echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin

      - name: 🚀 Build & Push Image
        run: |
          docker buildx build --load \
            --build-arg IMAGE_TAG=$IMAGE_VERSION \
            -t $IMAGE_NAME:$IMAGE_VERSION \
            .
          docker push $IMAGE_NAME:$IMAGE_VERSION

      - name: ✅ Build Summary
        run: |
          echo "### 🎉 Docker Image Built Successfully!" >> $GITHUB_STEP_SUMMARY
          echo "**Image:** \`$IMAGE_NAME:$IMAGE_VERSION\`" >> $GITHUB_STEP_SUMMARY
EOF

    # Add deployment job if not build-only
    if [ "$deployment_target" != "build-only" ]; then
        cat >> "$project_root/.github/workflows/ci-cd.yml" << 'EOF'

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    env:
      IMAGE_NAME: ${{ vars.IMAGE_NAME }}
      STACK_FILE: ${{ vars.STACK_FILE }}
      STACK_NAME: ${{ vars.STACK_NAME }}
      DEPLOY_PATH: ${{ vars.DEPLOY_PATH }}

    steps:
      - name: ⬇️ Checkout Code
        uses: actions/checkout@v4

      - name: 🧪 Load CI Environment Variables
        run: |
          while IFS='=' read -r key value
          do
            echo "$key=$value" >> $GITHUB_ENV
          done < .ci.env

      - name: 🔍 Debug ENV values
        run: |
          echo "IMAGE_VERSION=$IMAGE_VERSION"
          echo "STACK_FILE=$STACK_FILE"
          echo "STACK_NAME=$STACK_NAME"
          echo "DEPLOY_PATH=$DEPLOY_PATH"

      - name: 🔐 Setup SSH Agent
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.SSH_PRIVATE_KEY }}

      - name: 🚀 Deploy to Server
        env:
          SSH_USER: ${{ secrets.SSH_USER }}
          SSH_HOST: ${{ secrets.SSH_HOST }}
          SSH_PORT: ${{ secrets.SSH_PORT }}
          IMAGE_VERSION: ${{ env.IMAGE_VERSION }}
        run: |
          ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" << EOF
            set -e

            cd "$DEPLOY_PATH"

            echo "📝 Updating .env with image version..."
            sed -i 's/^IMAGE_VERSION=.*/IMAGE_VERSION='"$IMAGE_VERSION"'/' .env

            echo "🚢 Deploying stack..."
            docker stack deploy -c <(docker-compose -f "$STACK_FILE" config) "$STACK_NAME"

            echo "⏳ Waiting for stack to stabilize..."
            sleep 30

            echo "🔍 Service status:"
            docker stack services "$STACK_NAME"
          EOF

      - name: ✅ Deployment Summary
        run: |
          echo "### 🎉 Deployment Successful!" >> $GITHUB_STEP_SUMMARY
          echo "**Server:** \`${{ secrets.SSH_HOST }}\`" >> $GITHUB_STEP_SUMMARY
          echo "**Stack:** \`$STACK_NAME\`" >> $GITHUB_STEP_SUMMARY
          echo "**Image:** \`$IMAGE_NAME:$IMAGE_VERSION\`" >> $GITHUB_STEP_SUMMARY
EOF
    fi
    
    # Replace placeholders
    sed -i "s|##BRANCHES##|$branches_yaml|g" "$project_root/.github/workflows/ci-cd.yml"
    
    success_message "GitHub Actions workflow created: .github/workflows/ci-cd.yml"
}

# Build GitLab CI configuration
# Usage: build_gitlab_ci "linux-swarm" "main develop" "sokrates1989/api" "/path/to/project" "deploy_config"
build_gitlab_ci() {
    local deployment_target="$1"
    local branches="$2"
    local image_name="$3"
    local project_root="$4"
    local deploy_config="$5"
    
    section_header "STEP 4: Building CI/CD Configuration Files"
    
    echo "⚙️  Creating GitLab CI configuration..." >&2
    
    # Format branches for GitLab
    local branches_yaml=$(format_branches_gitlab "$branches")
    
    # Create .gitlab-ci.yml
    cat > "$project_root/.gitlab-ci.yml" << EOF
# GitLab CI/CD Pipeline
# Placeholder for GitLab implementation
# TODO: Implement GitLab CI/CD template

stages:
  - build
  - deploy

variables:
  IMAGE_NAME: $image_name

build:
  stage: build
  only:$branches_yaml
  script:
    - echo "Build stage - TODO"

deploy:
  stage: deploy
  only:$branches_yaml
  script:
    - echo "Deploy stage - TODO"
EOF
    
    success_message "GitLab CI configuration created: .gitlab-ci.yml"
    warning_message "GitLab CI template needs full implementation"
}

# Update .env file IMAGE_VERSION
# Usage: update_env_image_version "/path/to/.env" "0.1.5"
update_env_image_version() {
    local env_file="$1"
    local new_version="$2"
    
    if [ -f "$env_file" ]; then
        if grep -q "^IMAGE_VERSION=" "$env_file"; then
            sed -i "s/^IMAGE_VERSION=.*/IMAGE_VERSION=$new_version/" "$env_file"
        else
            echo "IMAGE_VERSION=$new_version" >> "$env_file"
        fi
    fi
}
