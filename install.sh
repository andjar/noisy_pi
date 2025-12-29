#!/bin/bash
# Noisy Pi Installation Script
# Installs ambient noise monitoring alongside BirdNET-Pi

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
REPO_URL="https://github.com/andjar/noisy_pi"
INSTALL_DIR="/opt/noisy-pi"
DATA_DIR="/var/lib/noisy-pi"
LOG_DIR="/var/log/noisy-pi"
CONFIG_DIR="$INSTALL_DIR/config"
USER="${SUDO_USER:-$USER}"

# Check if running as root or with sudo
check_sudo() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run with sudo"
        exit 1
    fi
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    local missing=()
    
    # Required commands
    for cmd in ffmpeg php sqlite3 python3 git curl; do
        if ! command -v $cmd &>/dev/null; then
            missing+=($cmd)
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_info "Installing missing dependencies: ${missing[*]}"
        apt-get update
        apt-get install -y "${missing[@]}"
    fi
    
    log_info "All dependencies satisfied"
}

# Test Icecast stream
test_icecast() {
    log_info "Testing BirdNET-Pi Icecast stream..."
    
    # Try multiple possible URLs for the Icecast stream
    local urls=(
        "http://127.0.0.1/stream"
        "http://localhost/stream"
        "http://127.0.0.1:8000/stream"
        "http://localhost:8000/stream"
    )
    
    for url in "${urls[@]}"; do
        # Check if we get HTTP 200 and some data (stream never ends, so we limit bytes)
        local response
        response=$(curl -s --connect-timeout 3 --max-time 2 -w "%{http_code}" "$url" 2>/dev/null | tail -c 3)
        if [[ "$response" == "200" ]]; then
            log_info "Icecast stream found at: $url"
            ICECAST_URL="$url"
            return 0
        fi
    done
    
    # Fallback: test with ffmpeg which handles streams better
    if timeout 5 ffmpeg -hide_banner -i http://127.0.0.1/stream -t 1 -f null - 2>&1 | grep -q "Audio"; then
        log_info "Icecast stream found at: http://127.0.0.1/stream"
        ICECAST_URL="http://127.0.0.1/stream"
        return 0
    fi
    
    log_warn "Icecast stream not found"
    log_warn "Make sure BirdNET-Pi is running and Icecast is enabled"
    return 1
}

# Test audio capture
test_audio() {
    log_info "Testing audio capture from Icecast..."
    
    local url="${ICECAST_URL:-http://127.0.0.1/stream}"
    local output
    
    if output=$(timeout 10 ffmpeg -hide_banner -i "$url" -t 2 -af volumedetect -f null - 2>&1); then
        if echo "$output" | grep -q "mean_volume"; then
            local mean_db=$(echo "$output" | grep "mean_volume" | sed 's/.*mean_volume: \([-0-9.]*\).*/\1/')
            log_info "Audio capture working! Mean volume: ${mean_db} dB"
            return 0
        fi
    fi
    
    log_warn "Could not capture audio from Icecast stream"
    return 1
}

# Create directories
setup_directories() {
    log_info "Creating directories..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$DATA_DIR"
    mkdir -p "$DATA_DIR/snippets"
    mkdir -p "$LOG_DIR"
    mkdir -p "$CONFIG_DIR"
    
    # Set ownership
    chown -R "$USER:$USER" "$DATA_DIR"
    chown -R "$USER:$USER" "$LOG_DIR"
}

# Download/copy files
setup_files() {
    log_info "Setting up files..."
    
    # If running from cloned repo
    if [[ -f "$(dirname "$0")/capture/capture_daemon.py" ]]; then
        log_info "Installing from local directory..."
        cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
    else
        log_info "Cloning from GitHub..."
        if [[ -d "$INSTALL_DIR/.git" ]]; then
            cd "$INSTALL_DIR"
            git pull
        else
            rm -rf "$INSTALL_DIR"
            git clone "$REPO_URL" "$INSTALL_DIR"
        fi
    fi
    
    # Ensure config exists
    if [[ ! -f "$CONFIG_DIR/noisy.json" ]]; then
        cp "$INSTALL_DIR/config/noisy.json" "$CONFIG_DIR/noisy.json"
    fi
    
    # Set ownership
    chown -R "$USER:$USER" "$INSTALL_DIR"
    chown -R "$USER:$USER" "$CONFIG_DIR"
    
    # Make scripts executable
    chmod +x "$INSTALL_DIR/capture/capture_daemon.py"
}

# Find available port
find_available_port() {
    local port=8080
    while [[ $port -le 8085 ]]; do
        if ! ss -tlnp | grep -q ":$port "; then
            echo $port
            return 0
        fi
        ((port++))
    done
    echo 8080
}

# Setup systemd services
setup_services() {
    log_info "Setting up systemd services..."
    
    # Find available port for web server
    local web_port=$(find_available_port)
    log_info "Using port $web_port for web dashboard"
    
    # Update service files with correct user
    sed -i "s/User=ubuntu/User=$USER/" "$INSTALL_DIR/systemd/noisy-capture.service"
    sed -i "s/Group=ubuntu/Group=$USER/" "$INSTALL_DIR/systemd/noisy-capture.service"
    sed -i "s/User=ubuntu/User=$USER/" "$INSTALL_DIR/systemd/noisy-web.service"
    sed -i "s/Group=ubuntu/Group=$USER/" "$INSTALL_DIR/systemd/noisy-web.service"
    
    # Update web port
    sed -i "s/0.0.0.0:8080/0.0.0.0:$web_port/" "$INSTALL_DIR/systemd/noisy-web.service"
    
    # Update config with port and detected Icecast URL
    local icecast="${ICECAST_URL:-http://127.0.0.1/stream}"
    if command -v jq &>/dev/null; then
        jq ".web_port = $web_port | .icecast_url = \"$icecast\"" "$CONFIG_DIR/noisy.json" > "$CONFIG_DIR/noisy.json.tmp"
        mv "$CONFIG_DIR/noisy.json.tmp" "$CONFIG_DIR/noisy.json"
    else
        sed -i "s/\"web_port\": [0-9]*/\"web_port\": $web_port/" "$CONFIG_DIR/noisy.json"
        sed -i "s|\"icecast_url\": \"[^\"]*\"|\"icecast_url\": \"$icecast\"|" "$CONFIG_DIR/noisy.json"
    fi
    
    # Copy service files
    cp "$INSTALL_DIR/systemd/noisy-capture.service" /etc/systemd/system/
    cp "$INSTALL_DIR/systemd/noisy-web.service" /etc/systemd/system/
    
    # Reload and enable
    systemctl daemon-reload
    systemctl enable noisy-capture
    systemctl enable noisy-web
    
    log_info "Services configured on port $web_port"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    systemctl start noisy-capture
    sleep 2
    systemctl start noisy-web
    
    # Check status
    if systemctl is-active --quiet noisy-capture; then
        log_info "Capture daemon started successfully"
    else
        log_error "Capture daemon failed to start"
        journalctl -u noisy-capture -n 20 --no-pager
    fi
    
    if systemctl is-active --quiet noisy-web; then
        log_info "Web dashboard started successfully"
    else
        log_error "Web dashboard failed to start"
        journalctl -u noisy-web -n 20 --no-pager
    fi
}

# Print summary
print_summary() {
    local web_port=$(grep -oP '"web_port":\s*\K[0-9]+' "$CONFIG_DIR/noisy.json" 2>/dev/null || echo "8080")
    local hostname=$(hostname)
    
    echo ""
    echo "=========================================="
    echo -e "${GREEN}Noisy Pi Installation Complete!${NC}"
    echo "=========================================="
    echo ""
    echo "Dashboard: http://${hostname}.local:${web_port}"
    echo "           http://$(hostname -I | awk '{print $1}'):${web_port}"
    echo ""
    echo "Commands:"
    echo "  sudo systemctl status noisy-capture  # Check capture daemon"
    echo "  sudo systemctl status noisy-web      # Check web server"
    echo "  tail -f $LOG_DIR/capture.log         # Watch logs"
    echo "  sqlite3 $DATA_DIR/noisy.db           # Query database"
    echo ""
    echo "Config file: $CONFIG_DIR/noisy.json"
    echo ""
}

# Main
main() {
    echo ""
    echo "=========================================="
    echo "       Noisy Pi Installer"
    echo "=========================================="
    echo ""
    
    check_sudo
    check_dependencies
    
    if ! test_icecast; then
        log_error "BirdNET-Pi Icecast stream is required"
        log_error "Please ensure BirdNET-Pi is running with Icecast enabled"
        exit 1
    fi
    
    test_audio || true  # Continue even if this fails
    
    setup_directories
    setup_files
    setup_services
    start_services
    print_summary
}

main "$@"
