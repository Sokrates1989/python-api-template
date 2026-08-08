#!/bin/bash
#
# version_manager.sh
#
# Module for managing Docker image versions and semantic versioning. The
# canonical selector is shared by build, publish, and maintenance workflows so
# every API menu uses the same numeric and named actions.

# Bump one semantic version without editing source files.
#
# Args:
#   $1: Current version, optionally prefixed with v or V.
#   $2: patch, minor, or major.
#
# Returns:
#   Writes the bumped version to stdout, or an empty line for invalid input.

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

# Read one line from the operator without contaminating captured stdout.
#
# Args:
#   $1: Prompt text.
#   $2: Name of the caller variable that receives the response.
#
# Returns:
#   0 after reading from the controlling terminal or standard input.
#
# Environment:
#   SEMVER_MENU_USE_STDIN=1 forces redirected input for automated tests.
read_semver_menu_value() {
    local prompt="$1"
    local target_name="$2"
    local response=""

    if [ "${SEMVER_MENU_USE_STDIN:-}" = "1" ]; then
        read -r -p "$prompt" response
    elif [[ -r /dev/tty ]]; then
        read -r -p "$prompt" response < /dev/tty
    else
        read -r -p "$prompt" response
    fi
    printf -v "$target_name" '%s' "$response"
}

# Select a semantic version through the repository-wide canonical menu.
#
# Args:
#   $1: Current semantic version.
#   $2: Human-readable subject, such as "API image" or "Release".
#   $3: true to permit a v/V prefix for an exact value; false otherwise.
#   $4: Optional text appended inside the keep-current parentheses.
#
# Returns:
#   Writes only the selected version to stdout. Menus and errors use stderr.
#
# Errors:
#   Re-prompts after invalid menu aliases or malformed exact versions.
select_semver_version() {
    local current_version="${1:-0.1.0}"
    local subject="${2:-Version}"
    local allow_prefix="${3:-false}"
    local keep_note="${4:-}"
    local patch_version=""
    local minor_version=""
    local major_version=""
    local choice=""
    local exact_version=""
    local exact_pattern='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'

    if [ "$allow_prefix" = "true" ]; then
        exact_pattern='^[vV]?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
    fi
    patch_version="$(bump_semver "$current_version" patch)"
    minor_version="$(bump_semver "$current_version" minor)"
    major_version="$(bump_semver "$current_version" major)"
    if [ -z "$patch_version" ] || [ -z "$minor_version" ] || [ -z "$major_version" ]; then
        echo "Invalid current SemVer value: ${current_version}" >&2
        return 1
    fi

    while true; do
        echo "" >&2
        echo "${subject} version options:" >&2
        echo "  1/k) Keep current (${current_version}${keep_note})" >&2
        echo "  2/p) Patch (${current_version} -> ${patch_version})" >&2
        echo "  3/f) Feature / Minor (${current_version} -> ${minor_version})" >&2
        echo "  4/m) Major (${current_version} -> ${major_version})" >&2
        echo "  5/e) Enter an exact semantic version" >&2
        echo "" >&2
        read_semver_menu_value "Choose ${subject} version [1/k]: " choice
        choice="${choice,,}"
        case "${choice:-1}" in
            1|k|keep|current) printf '%s\n' "$current_version"; return 0 ;;
            2|p|patch) printf '%s\n' "$patch_version"; return 0 ;;
            3|f|feature|minor) printf '%s\n' "$minor_version"; return 0 ;;
            4|m|major) printf '%s\n' "$major_version"; return 0 ;;
            5|e|exact|manual)
                read_semver_menu_value "Enter exact semantic version: " exact_version
                ;;
            *) exact_version="$choice" ;;
        esac
        if [[ "$exact_version" =~ $exact_pattern ]]; then
            printf '%s\n' "$exact_version"
            return 0
        fi
        echo "Invalid selection. Use 1-5, k/p/f/m/e, or an exact x.y.z version." >&2
        exact_version=""
    done
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

get_remote_image_state() {
    local image_ref="$1"

    if [ -z "$image_ref" ]; then
        echo "unknown|"
        return
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo "skipped|Docker CLI nicht verfügbar"
        return
    fi

    local output
    if output=$(docker manifest inspect "$image_ref" 2>&1); then
        echo "present|"
        return
    fi

    if echo "$output" | grep -Eqi 'not found|no such manifest'; then
        echo "missing|"
    elif echo "$output" | grep -Eqi 'denied|unauthorized'; then
        echo "unauthorized|Anmeldung erforderlich"
    else
        local detail
        detail=$(echo "$output" | head -n1)
        echo "error|$detail"
    fi
}

get_local_image_state() {
    local image_ref="$1"

    if [ -z "$image_ref" ]; then
        echo "unknown|"
        return
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo "skipped|Docker CLI nicht verfügbar"
        return
    fi

    if docker image inspect "$image_ref" >/dev/null 2>&1; then
        echo "present|"
    else
        echo "missing|"
    fi
}

describe_state_label() {
    local prefix="$1"
    local state="$2"
    local detail="$3"

    case "$state" in
        present)
            echo "$prefix: verfügbar"
            ;;
        missing)
            echo "$prefix: fehlt"
            ;;
        unauthorized)
            echo "$prefix: Zugriff verweigert"
            ;;
        error)
            if [ -n "$detail" ]; then
                echo "$prefix: Fehler - $detail"
            else
                echo "$prefix: Fehler"
            fi
            ;;
        skipped)
            if [ -n "$detail" ]; then
                echo "$prefix: nicht geprüft ($detail)"
            else
                echo "$prefix: nicht geprüft"
            fi
            ;;
        unknown)
            echo "$prefix: unbekannt"
            ;;
        *)
            echo "$prefix: unbekannt"
            ;;
    esac
}

build_version_annotation() {
    local image_name="$1"
    local version="$2"

    if [ -z "$image_name" ]; then
        echo " (Remote: nicht geprüft - IMAGE_NAME fehlt)"
        return
    fi

    if [ -z "$version" ]; then
        echo " (Remote: nicht geprüft - Version fehlt)"
        return
    fi

    local image_ref="${image_name}:${version}"

    local remote_state
    local remote_detail
    IFS='|' read -r remote_state remote_detail <<< "$(get_remote_image_state "$image_ref")"
    local annotation=" ($(describe_state_label "Remote" "$remote_state" "$remote_detail")"

    local local_state
    local local_detail
    IFS='|' read -r local_state local_detail <<< "$(get_local_image_state "$image_ref")"

    if [ "$local_state" != "$remote_state" ]; then
        annotation="$annotation, $(describe_state_label "Lokal" "$local_state" "$local_detail")"
    fi

    annotation="$annotation)"
    echo "$annotation"
}

remote_image_status() {
    local image_ref="$1"
    local context="$2"

    if [ -z "$image_ref" ]; then
        return
    fi

    local state detail
    IFS='|' read -r state detail <<< "$(get_remote_image_state "$image_ref")"

    case "$state" in
        present)
            echo "✅ $context: $image_ref ist auf der Registry vorhanden."
            ;;
        missing)
            echo "ℹ️ $context: $image_ref wurde auf der Registry nicht gefunden."
            ;;
        unauthorized)
            echo "⚠️  $context: Zugriff verweigert für $image_ref. Bitte bei der Registry anmelden."
            ;;
        skipped)
            if [ -n "$detail" ]; then
                echo "⚠️  $context: Remote-Check übersprungen ($detail)."
            else
                echo "⚠️  $context: Remote-Check übersprungen."
            fi
            ;;
        error)
            if [ -n "$detail" ]; then
                echo "⚠️  $context: Fehler beim Prüfen von $image_ref: $detail"
            else
                echo "⚠️  $context: Fehler beim Prüfen von $image_ref."
            fi
            ;;
        *)
            echo "⚠️  $context: Unbekannter Zustand für $image_ref."
            ;;
    esac
}

# Update deployment environment files with one selected image version.
#
# Args:
#   $1: Public environment file; defaults to .env.
#   $2: Optional CI environment file; defaults to .ci.env.
#   $3: Optional image repository override.
#
# Returns:
#   0 after writing the selected version, or non-zero when selection fails.
update_image_version() {
    local env_file="${1:-.env}"
    local ci_env_file="${2:-.ci.env}"
    local image_name_override="${3:-}"

    local current_env_version
    current_env_version=$(grep '^IMAGE_VERSION=' "$env_file" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d ' "')

    local current_ci_version=""
    if [ -n "$ci_env_file" ]; then
        current_ci_version=$(grep '^IMAGE_VERSION=' "$ci_env_file" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d ' "')
    fi

    local base_version="$current_env_version"
    if [ -z "$base_version" ]; then
        base_version="$current_ci_version"
    fi
    if [ -z "$base_version" ]; then
        base_version="0.1.0"
    fi

    local image_name="$image_name_override"
    if [ -z "$image_name" ]; then
        image_name=$(grep '^IMAGE_NAME=' "$env_file" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d ' "')
    fi

    local display_env=${current_env_version:-"<nicht gesetzt>"}
    local display_ci=${current_ci_version:-"<nicht gesetzt>"}

    echo ""
    local env_annotation
    env_annotation=$(build_version_annotation "$image_name" "$current_env_version")

    local ci_annotation
    ci_annotation=$(build_version_annotation "$image_name" "$current_ci_version")

    echo "📸 Aktuelle IMAGE_VERSION Werte:"
    echo "  • .env    : $display_env$env_annotation"
    echo "  • .ci.env : $display_ci$ci_annotation"
    echo ""

    if [ -n "$image_name" ] && [ -n "$base_version" ]; then
        remote_image_status "${image_name}:${base_version}" "Aktuelle Version auf Registry"
        echo ""
    elif [ -z "$image_name" ]; then
        echo "⚠️  IMAGE_NAME ist nicht gesetzt – Remote-Check übersprungen."
        echo ""
    fi

    local new_version=""
    new_version="$(select_semver_version "$base_version" "Docker image" true)" || return 1

    if [ -z "$new_version" ]; then
        echo "❌ Konnte neue Version nicht bestimmen. Bitte erneut versuchen."
        return
    fi

    if [ -n "$image_name" ]; then
        echo ""
        remote_image_status "${image_name}:${new_version}" "Gewählte Version auf Registry"
    fi

    echo ""
    update_image_version_in_file "$env_file" "$new_version"
    if [ -n "$ci_env_file" ]; then
        update_image_version_in_file "$ci_env_file" "$new_version"
    fi
    echo ""
    echo "🎯 IMAGE_VERSION wurde auf $new_version gesetzt."
}
