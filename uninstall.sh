#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Lancer en root"; exit 1; }
systemctl disable --now eve-image-forge 2>/dev/null || true
rm -f /etc/systemd/system/eve-image-forge.service
systemctl daemon-reload
rm -rf /opt/eve-image-forge
printf 'Application supprimée. Les uploads/backups restent dans /var/lib/eve-image-forge et le jeton dans /etc/eve-image-forge.\n'
