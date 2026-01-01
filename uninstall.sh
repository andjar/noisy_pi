#!/bin/bash
# Noisy Pi Uninstallation Script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo ""
echo "=========================================="
echo "       Noisy Pi Uninstaller"
echo "=========================================="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}This script must be run with sudo${NC}"
    exit 1
fi

# Stop services
log_info "Stopping services..."
systemctl stop noisy-capture 2>/dev/null || true
systemctl stop noisy-web 2>/dev/null || true

# Disable services
log_info "Disabling services..."
systemctl disable noisy-capture 2>/dev/null || true
systemctl disable noisy-web 2>/dev/null || true

# Remove service files
log_info "Removing service files..."
rm -f /etc/systemd/system/noisy-capture.service
rm -f /etc/systemd/system/noisy-web.service
systemctl daemon-reload

# Ask about data
echo ""
read -p "Remove data directory (/var/lib/noisy-pi)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "Removing data directory..."
    rm -rf /var/lib/noisy-pi
fi

# Remove logs
log_info "Removing log directory..."
rm -rf /var/log/noisy-pi

# Remove installation directory
log_info "Removing installation directory..."
rm -rf /opt/noisy-pi

echo ""
echo -e "${GREEN}Noisy Pi has been uninstalled.${NC}"
echo ""



