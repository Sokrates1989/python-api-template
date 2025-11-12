#!/bin/bash
# Branch selector module
# Handles branch selection for CI/CD triggers

# Select branches for CI/CD
# Returns: space-separated list of branch names
select_cicd_branches() {
    section_header "Branch Selection for CI/CD"
    
    echo "Fetching remote branches..." >&2
    local branches=($(get_remote_branches))
    
    if [ ${#branches[@]} -eq 0 ]; then
        warning_message "No remote branches found"
        echo "" >&2
        echo "Using default: main" >&2
        echo "main"
        return 0
    fi
    
    echo "Available branches:" >&2
    for i in "${!branches[@]}"; do
        echo "  $((i+1))) ${branches[$i]}" >&2
    done
    echo "" >&2
    
    # If only one branch, use it automatically
    if [ ${#branches[@]} -eq 1 ]; then
        info_message "Only one branch found: ${branches[0]}"
        echo "Using ${branches[0]} for CI/CD triggers" >&2
        echo "${branches[0]}"
        return 0
    fi
    
    echo "Select which branches should trigger CI/CD pipeline:" >&2
    echo "(Common choices: main, master, develop, production)" >&2
    echo "" >&2
    
    local indices=$(prompt_multi_selection "Select branches" "${branches[@]}")
    
    # Convert indices to branch names
    local selected_branches=()
    for idx in $indices; do
        selected_branches+=("${branches[$idx]}")
    done
    
    echo "" >&2
    success_message "Selected branches: ${selected_branches[*]}"
    
    # Return as space-separated string
    echo "${selected_branches[@]}"
}

# Format branches for GitHub Actions YAML
# Usage: format_branches_github "main develop production"
format_branches_github() {
    local branches="$1"
    local formatted=""
    
    for branch in $branches; do
        if [ -z "$formatted" ]; then
            formatted="$branch"
        else
            formatted="$formatted, $branch"
        fi
    done
    
    echo "[ $formatted ]"
}

# Format branches for GitLab CI YAML
# Usage: format_branches_gitlab "main develop production"
format_branches_gitlab() {
    local branches="$1"
    local formatted=""
    
    for branch in $branches; do
        formatted="$formatted\n    - $branch"
    done
    
    echo -e "$formatted"
}

# Validate branch name
# Usage: validate_branch_name "main"
validate_branch_name() {
    local branch="$1"
    
    # Check if branch exists in remote
    if git ls-remote --heads origin "$branch" | grep -q "$branch"; then
        return 0
    else
        return 1
    fi
}
