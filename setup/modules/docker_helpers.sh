#!/bin/bash
#
# docker_helpers.sh
#
# Module for Docker-related helper functions

check_docker_installation() {
    echo "🔍 Überprüfe Docker-Installation..."
    
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker ist nicht installiert!"
        echo "📥 Bitte installiere Docker von: https://www.docker.com/get-started"
        return 1
    fi

    if ! docker info &> /dev/null; then
        echo "❌ Docker-Daemon läuft nicht!"
        echo "🔄 Bitte starte Docker Desktop oder den Docker-Service"
        return 1
    fi

    if ! docker compose version &> /dev/null; then
        echo "❌ Docker Compose ist nicht verfügbar!"
        echo "📥 Bitte installiere eine aktuelle Docker-Version mit Compose-Plugin"
        return 1
    fi

    echo "✅ Docker ist installiert und läuft"
    return 0
}

read_env_variable() {
    local var_name="$1"
    local env_file="${2:-.env}"
    local default_value="${3:-}"
    
    local value
    value=$(grep "^${var_name}=" "$env_file" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '\r' | tr -d '"' | sed "s/^[[:space:]]*//;s/[[:space:]]*$//")
    
    if [ -z "$value" ]; then
        echo "$default_value"
    else
        echo "$value"
    fi
}

update_env_variable() {
    local var_name="$1"
    local value="$2"
    local env_file="${3:-.env}"

    if [ ! -f "$env_file" ]; then
        printf '%s=%s\n' "$var_name" "$value" > "$env_file"
        return 0
    fi

    local temp_file
    temp_file="$(mktemp)" || return 1

    if grep -qE "^${var_name}=" "$env_file" 2>/dev/null; then
        sed "s|^${var_name}=.*|${var_name}=${value}|" "$env_file" > "$temp_file"
    else
        cat "$env_file" > "$temp_file"
        printf '\n%s=%s\n' "$var_name" "$value" >> "$temp_file"
    fi

    mv "$temp_file" "$env_file"
}

determine_compose_file() {
    local db_type="$1"
    local db_mode="$2"
    local normalized_db_type
    local normalized_db_mode
    normalized_db_type=$(printf '%s' "$db_type" | tr '[:upper:]' '[:lower:]')
    normalized_db_mode=$(printf '%s' "$db_mode" | tr '[:upper:]' '[:lower:]')
    
    if [ "$normalized_db_mode" = "external" ]; then
        echo "local-deployment/docker-compose.yml"
    elif [ "$normalized_db_type" = "neo4j" ]; then
        echo "local-deployment/docker-compose.neo4j.yml"
    elif [ "$normalized_db_type" = "postgresql" ] || [ "$normalized_db_type" = "postgres" ] || [ "$normalized_db_type" = "mysql" ]; then
        echo "local-deployment/docker-compose.postgres.yml"
    elif [ "$normalized_db_type" = "mongodb" ] || [ "$normalized_db_type" = "mongo" ]; then
        echo "local-deployment/docker-compose.mongodb.named-volume.yml"
    else
        echo "local-deployment/docker-compose.yml"
    fi
}
