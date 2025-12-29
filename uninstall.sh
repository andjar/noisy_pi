#!/bin/bash
#
# Noisy Pi Uninstall Script
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $1"; }

echo ""
echo -e "${RED}╔═══════════════════════════════════════════╗${NC}"
echo -e "${RED}║     Noisy Pi Uninstall Script             ║${NC}"
echo -e "${RED}╚═══════════════════════════════════════════╝${NC}"
echo ""

read -p "Are you sure you want to uninstall Noisy Pi? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

log "Stopping services..."
sudo systemctl stop noisy-capture noisy-web 2>/dev/null || true
sudo systemctl disable noisy-capture noisy-web 2>/dev/null || true

log "Removing service files..."
sudo rm -f /etc/systemd/system/noisy-capture.service
sudo rm -f /etc/systemd/system/noisy-web.service
sudo systemctl daemon-reload

log "Removing installation directory..."
sudo rm -rf /opt/noisy-pi

read -p "Remove database and logs? This will delete ALL collected data! [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Removing data and logs..."
    sudo rm -rf /var/lib/noisy-pi /var/log/noisy-pi
    log "All data removed."
else
    warn "Data preserved at /var/lib/noisy-pi"
    warn "Logs preserved at /var/log/noisy-pi"
fi

log "Uninstallation complete!"
echo ""
echo "Thank you for using Noisy Pi!"

