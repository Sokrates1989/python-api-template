#!/bin/bash
#
# version_manager.sh
#
# Module for managing Docker image versions and semantic versioning

bump_semver() {
    local version="$1"
    local level="$2"

    if [ -z "$version" ]; then
        version="0.0.0"
    fi

    local prefix=""
    if [[ "$version" =~ ^[vV] ]]; then
        prefix="${version:0:1}"
        version="${version:1}"
    fi

    local IFS='.'
    read -r major minor patch <<< "$version"
    major=${major:-0}
    minor=${minor:-0}
    patch=${patch:-0}

    if ! [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ && "$patch" =~ ^[0-9]+$ ]]; then
        echo ""
        return
    fi

    case "$level" in
        patch) patch=$((patch + 1)) ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        major) major=$((major + 1)); minor=0; patch=0 ;;
        *) echo ""; return ;;
    esac

    echo "${prefix}${major}.${minor}.${patch}"
}

update_image_version_in_file() {
    local file="$1"
    local new_version="$2"

    if [ ! -f "$file" ]; then
        echo "⚠️  $file nicht gefunden – übersprungen."
        return
    fi

    local tmp_file
    tmp_file=$(mktemp) || {
        echo "❌ Konnte temporäre Datei nicht erstellen."
        return
    }

    local replaced=0
    while IFS= read -r line || [ -n "$line" ]; do
        if [ $replaced -eq 0 ] && [[ $line == IMAGE_VERSION=* ]]; then
            echo "IMAGE_VERSION=$new_version" >> "$tmp_file"
            replaced=1
        else
            echo "$line" >> "$tmp_file"
        fi
    done < "$file"

    if [ $replaced -eq 0 ]; then
        echo "IMAGE_VERSION=$new_version" >> "$tmp_file"
    fi

    mv "$tmp_file" "$file"
    echo "✅  $file -> IMAGE_VERSION=$new_version"
}

update_image_version() {
    local env_file=".env"
    local ci_env_file=".ci.env"

    local current_env_version
    current_env_version=$(grep '^IMAGE_VERSION=' "$env_file" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d ' "')

    local current_ci_version
    current_ci_version=$(grep '^IMAGE_VERSION=' "$ci_env_file" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d ' "')

    local base_version="$current_env_version"
    if [ -z "$base_version" ]; then
        base_version="$current_ci_version"
    fi
    if [ -z "$base_version" ]; then
        base_version="0.1.0"
    fi

    local display_env=${current_env_version:-"<nicht gesetzt>"}
    local display_ci=${current_ci_version:-"<nicht gesetzt>"}

    echo ""
    echo "📸 Aktuelle IMAGE_VERSION Werte:"
    echo "  • .env    : $display_env"
    echo "  • .ci.env : $display_ci"
    echo ""
    echo "Wie möchtest du die Version aktualisieren?"
    echo "  1) Manuell eingeben"
    echo "  2) Bugfix/Patch (+0.0.1)"
    echo "  3) Feature/Minor (+0.1.0)"
    echo "  4) Breaking/Major (+1.0.0)"
    read -r -p "Deine Wahl (1-4): " version_choice

    local new_version=""
    case "$version_choice" in
        1)
            read -r -p "Neue IMAGE_VERSION: " new_version
            new_version=${new_version//[[:space:]]/}
            ;;
        2)
            new_version=$(bump_semver "$base_version" "patch")
            ;;
        3)
            new_version=$(bump_semver "$base_version" "minor")
            ;;
        4)
            new_version=$(bump_semver "$base_version" "major")
            ;;
        *)
            echo "❌ Ungültige Auswahl. Breche Aktualisierung ab."
            return
            ;;
    esac

    if [ -z "$new_version" ]; then
        echo "❌ Konnte neue Version nicht bestimmen. Bitte erneut versuchen."
        return
    fi

    echo ""
    update_image_version_in_file "$env_file" "$new_version"
    update_image_version_in_file "$ci_env_file" "$new_version"
    echo ""
    echo "🎯 IMAGE_VERSION wurde auf $new_version gesetzt."
}
