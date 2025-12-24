#!/bin/bash
#
# browser_helpers.sh
#
# Module for browser-related helper functions in quick-start script.
# Provides URL polling and automatic browser opening when services are ready.

# wait_for_url
# Polls a URL until it returns a 2xx or 3xx HTTP status code.
# Uses curl with a short connect timeout to avoid hanging on unresponsive services.
#
# Args:
#   url: The URL to check
#   timeout_seconds: Maximum time to wait (default: 120)
#   (polls every 2 seconds)
#
# Returns:
#   0 if URL became available, 1 if timeout reached
wait_for_url() {
    local url="$1"
    local timeout="${2:-120}"
    local start_time
    start_time=$(date +%s)
    
    while true; do
        local current_time
        current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ "$elapsed" -ge "$timeout" ]; then
            return 1
        fi
        
        # Try to get HTTP status code, timeout after 2 seconds per attempt
        local status
        status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 "$url" 2>/dev/null || echo "000")
        
        # Check if status is 2xx or 3xx (successful)
        if [[ "$status" =~ ^[23][0-9][0-9]$ ]]; then
            return 0
        fi
        
        sleep 2
    done
}

# open_url
# Opens a URL in the default browser, preferring incognito/private mode.
#
# Args:
#   url: The URL to open
#
# Returns:
#   void
open_url() {
    local url="$1"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        open -na "Google Chrome" --args --incognito "$url" 2>/dev/null || \
        open -a "Safari" "$url" 2>/dev/null || \
        open "$url" 2>/dev/null
    elif command -v microsoft-edge &> /dev/null; then
        microsoft-edge --inprivate "$url" >/dev/null 2>&1 &
    elif command -v google-chrome &> /dev/null; then
        google-chrome --incognito "$url" >/dev/null 2>&1 &
    elif command -v chromium-browser &> /dev/null; then
        chromium-browser --incognito "$url" >/dev/null 2>&1 &
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$url" 2>/dev/null &
    else
        echo "Could not detect browser command. Please open manually: $url"
    fi
}

# open_browsers_delayed
# Displays service URLs and opens browsers automatically when services become available.
# Runs the polling and browser opening in the background so docker compose can proceed.
#
# Args:
#   port: The port the API is running on
#   include_neo4j: "true" or "false" - whether to also open Neo4j browser
#   timeout: Maximum seconds to wait for services (default: 120)
#
# Returns:
#   void
open_browsers_delayed() {
    local port="$1"
    local include_neo4j="$2"
    local timeout="${3:-120}"
    
    local api_url="http://localhost:$port/docs"
    local neo4j_url="http://localhost:7474"
    
    echo ""
    echo "========================================"
    echo "  Services will be accessible at:"
    echo "  • API Docs: $api_url"
    if [ "$include_neo4j" = "true" ]; then
        echo "  • Neo4j Browser: $neo4j_url"
    fi
    echo "========================================"
    echo ""
    echo "🌐 Browser will open automatically when services are ready..."
    echo ""
    
    # Wait for services and open browsers in background
    (
        # Wait for API to be available
        if wait_for_url "$api_url" "$timeout"; then
            open_url "$api_url"
        else
            echo "⚠️  Timeout waiting for API at $api_url"
        fi
        
        # Wait for Neo4j if requested
        if [ "$include_neo4j" = "true" ]; then
            if wait_for_url "$neo4j_url" "$timeout"; then
                open_url "$neo4j_url"
            else
                echo "⚠️  Timeout waiting for Neo4j at $neo4j_url"
            fi
        fi
    ) &
}
