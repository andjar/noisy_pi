#!/bin/bash
#
# Noisy Pi Installation Script
# Ambient noise monitoring for Raspberry Pi
#
# Usage:
#   curl -s https://raw.githubusercontent.com/YOUR_USERNAME/noisy-pi/main/install.sh | bash
#
# Or clone and run:
#   git clone https://github.com/YOUR_USERNAME/noisy-pi.git
#   cd noisy-pi && ./install.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/noisy-pi"
DATA_DIR="/var/lib/noisy-pi"
LOG_DIR="/var/log/noisy-pi"
WEB_PORT=8080
REPO_URL="https://github.com/YOUR_USERNAME/noisy-pi.git"

# Logging
log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ERROR:${NC} $1" >&2
    exit 1
}

header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should NOT be run as root. Run as your normal user (e.g., 'pi')."
    fi
}

# Check system requirements
check_requirements() {
    header "Checking System Requirements"
    
    # Check OS
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        log "Detected OS: $PRETTY_NAME"
        
        if [[ "$ID" != "debian" && "$ID" != "raspbian" ]]; then
            warn "This script is designed for Debian/Raspbian. Proceed with caution."
        fi
    else
        warn "Could not detect OS version."
    fi
    
    # Check architecture
    ARCH=$(uname -m)
    log "Architecture: $ARCH"
    
    # Check for Raspberry Pi
    if [[ -f /proc/device-tree/model ]]; then
        PI_MODEL=$(cat /proc/device-tree/model)
        log "Hardware: $PI_MODEL"
    fi
    
    # Check disk space (need at least 500MB free)
    FREE_SPACE=$(df -m / | awk 'NR==2 {print $4}')
    if [[ $FREE_SPACE -lt 500 ]]; then
        error "Insufficient disk space. Need at least 500MB free, have ${FREE_SPACE}MB."
    fi
    log "Free disk space: ${FREE_SPACE}MB"
    
    # Check for PulseAudio
    if command -v pulseaudio &> /dev/null; then
        log "PulseAudio: Found"
        if pulseaudio --check 2>/dev/null; then
            log "PulseAudio: Running"
        else
            warn "PulseAudio is installed but not running. Will attempt to start it."
        fi
    else
        warn "PulseAudio not found. Audio capture may not work."
    fi
    
    # Check for Python 3
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version)
        log "Python: $PYTHON_VERSION"
    else
        error "Python 3 is required but not found."
    fi
    
    # Check for PHP
    if command -v php &> /dev/null; then
        PHP_VERSION=$(php --version | head -n1)
        log "PHP: $PHP_VERSION"
    else
        warn "PHP not found. Will install."
    fi
    
    # Check if port 8080 is available
    if ss -tuln | grep -q ":${WEB_PORT} "; then
        warn "Port ${WEB_PORT} is already in use. You may need to change the web port."
    else
        log "Port ${WEB_PORT}: Available"
    fi
    
    log "Requirements check passed!"
}

# Install system dependencies
install_dependencies() {
    header "Installing Dependencies"
    
    log "Updating package lists..."
    sudo apt-get update -qq
    
    log "Installing required packages..."
    sudo apt-get install -y -qq \
        python3-pip \
        python3-numpy \
        python3-scipy \
        php-cli \
        php-sqlite3 \
        sqlite3 \
        libportaudio2 \
        portaudio19-dev \
        git
    
    log "Installing Python packages..."
    pip3 install --user --quiet sounddevice soundfile
    
    log "Dependencies installed!"
}

# Download or copy source files
setup_files() {
    header "Setting Up Files"
    
    # Check if we're running from a cloned repo
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    if [[ -f "${SCRIPT_DIR}/capture/capture_daemon.py" ]]; then
        log "Installing from local directory..."
        SOURCE_DIR="$SCRIPT_DIR"
    else
        log "Cloning repository..."
        TEMP_DIR=$(mktemp -d)
        git clone --depth 1 "$REPO_URL" "$TEMP_DIR"
        SOURCE_DIR="$TEMP_DIR"
    fi
    
    # Create directories
    log "Creating directories..."
    sudo mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$LOG_DIR"
    
    # Copy files
    log "Copying files to $INSTALL_DIR..."
    sudo cp -r "${SOURCE_DIR}/capture" "$INSTALL_DIR/"
    sudo cp -r "${SOURCE_DIR}/web" "$INSTALL_DIR/"
    sudo cp -r "${SOURCE_DIR}/systemd" "$INSTALL_DIR/"
    
    # Set ownership
    sudo chown -R $USER:$USER "$INSTALL_DIR"
    sudo chown -R $USER:$USER "$DATA_DIR"
    sudo chown -R $USER:$USER "$LOG_DIR"
    
    # Make capture daemon executable
    chmod +x "$INSTALL_DIR/capture/capture_daemon.py"
    
    # Clean up temp directory if used
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
    
    log "Files installed!"
}

# Initialize database
init_database() {
    header "Initializing Database"
    
    cd "$INSTALL_DIR/capture"
    
    # Set environment for Python
    export NOISY_PI_DIR="$INSTALL_DIR"
    export NOISY_PI_DATA="$DATA_DIR"
    export NOISY_PI_LOG="$LOG_DIR"
    
    log "Creating database schema..."
    python3 db.py --init
    
    log "Database initialized at ${DATA_DIR}/noisy.db"
}

# Test audio capture
test_audio() {
    header "Testing Audio Capture"
    
    cd "$INSTALL_DIR/capture"
    
    log "Available audio devices:"
    python3 capture_daemon.py --list-devices || true
    
    log ""
    log "If you see your microphone listed above, audio capture should work."
    log "If not, check your PulseAudio configuration."
}

# Install systemd services
install_services() {
    header "Installing Services"
    
    # Update user in service files
    CURRENT_USER=$(whoami)
    CURRENT_UID=$(id -u)
    
    log "Configuring services for user: $CURRENT_USER (UID: $CURRENT_UID)"
    
    # Create service files with correct user
    sudo sed "s/User=pi/User=$CURRENT_USER/g; s/Group=pi/Group=$CURRENT_USER/g; s|/run/user/1000|/run/user/$CURRENT_UID|g" \
        "$INSTALL_DIR/systemd/noisy-capture.service" > /tmp/noisy-capture.service
    sudo sed "s/User=pi/User=$CURRENT_USER/g; s/Group=pi/Group=$CURRENT_USER/g" \
        "$INSTALL_DIR/systemd/noisy-web.service" > /tmp/noisy-web.service
    
    # Install service files
    sudo mv /tmp/noisy-capture.service /etc/systemd/system/
    sudo mv /tmp/noisy-web.service /etc/systemd/system/
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable services
    log "Enabling services..."
    sudo systemctl enable noisy-capture noisy-web
    
    # Start services
    log "Starting services..."
    sudo systemctl start noisy-capture noisy-web
    
    # Check status
    sleep 2
    if systemctl is-active --quiet noisy-capture; then
        log "Capture daemon: Running"
    else
        warn "Capture daemon: Not running. Check logs with: journalctl -u noisy-capture"
    fi
    
    if systemctl is-active --quiet noisy-web; then
        log "Web dashboard: Running"
    else
        warn "Web dashboard: Not running. Check logs with: journalctl -u noisy-web"
    fi
    
    log "Services installed!"
}

# Create uninstall script
create_uninstall() {
    cat > "$INSTALL_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
# Noisy Pi Uninstall Script

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $1"; }

log "Stopping services..."
sudo systemctl stop noisy-capture noisy-web 2>/dev/null || true
sudo systemctl disable noisy-capture noisy-web 2>/dev/null || true

log "Removing service files..."
sudo rm -f /etc/systemd/system/noisy-capture.service
sudo rm -f /etc/systemd/system/noisy-web.service
sudo systemctl daemon-reload

log "Removing installation directory..."
sudo rm -rf /opt/noisy-pi

read -p "Remove database and logs? This will delete all collected data! [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Removing data and logs..."
    sudo rm -rf /var/lib/noisy-pi /var/log/noisy-pi
else
    warn "Data preserved at /var/lib/noisy-pi"
fi

log "Uninstallation complete!"
EOF
    chmod +x "$INSTALL_DIR/uninstall.sh"
}

# Print completion message
print_complete() {
    header "Installation Complete!"
    
    # Get hostname/IP
    HOSTNAME=$(hostname)
    IP_ADDR=$(hostname -I | awk '{print $1}')
    
    echo -e "${GREEN}Noisy Pi is now running!${NC}"
    echo ""
    echo "Access the dashboard at:"
    echo -e "  ${BLUE}http://${HOSTNAME}.local:${WEB_PORT}${NC}"
    echo -e "  ${BLUE}http://${IP_ADDR}:${WEB_PORT}${NC}"
    echo ""
    echo "Useful commands:"
    echo "  View capture logs:    journalctl -u noisy-capture -f"
    echo "  View web logs:        journalctl -u noisy-web -f"
    echo "  Restart capture:      sudo systemctl restart noisy-capture"
    echo "  Restart web:          sudo systemctl restart noisy-web"
    echo "  Stop all:             sudo systemctl stop noisy-capture noisy-web"
    echo "  Uninstall:            $INSTALL_DIR/uninstall.sh"
    echo ""
    echo "Data is stored at: $DATA_DIR"
    echo "Logs are stored at: $LOG_DIR"
    echo ""
    echo -e "${GREEN}Thank you for using Noisy Pi!${NC}"
}

# Main installation
main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                                           ║${NC}"
    echo -e "${BLUE}║     📊 Noisy Pi Installation Script       ║${NC}"
    echo -e "${BLUE}║     Ambient Noise Monitoring for Pi       ║${NC}"
    echo -e "${BLUE}║                                           ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════╝${NC}"
    echo ""
    
    check_root
    check_requirements
    install_dependencies
    setup_files
    init_database
    test_audio
    install_services
    create_uninstall
    print_complete
}

# Run main
main "$@"

