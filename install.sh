#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo "ERREUR: lance ce script en root." >&2; exit 1; fi
if [[ ! -d /opt/unetlab ]]; then echo "ERREUR: /opt/unetlab introuvable. Ce script doit être lancé sur le serveur EVE-NG." >&2; exit 1; fi
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR=/opt/eve-image-forge
STATE_DIR=/var/lib/eve-image-forge
CONF_DIR=/etc/eve-image-forge
mkdir -p "$APP_DIR" "$STATE_DIR/uploads" "$STATE_DIR/work" "$STATE_DIR/backups" "$CONF_DIR"
rm -rf "$APP_DIR/app"
cp -a "$SRC_DIR/app" "$APP_DIR/app"
cp -a "$SRC_DIR/VERSION" "$APP_DIR/VERSION"
if [[ ! -s "$CONF_DIR/token" ]]; then
  if command -v openssl >/dev/null; then openssl rand -hex 24 > "$CONF_DIR/token"; else python3 - <<'PY' > "$CONF_DIR/token"
import secrets; print(secrets.token_hex(24))
PY
  fi
fi
chmod 600 "$CONF_DIR/token"
cat > /etc/systemd/system/eve-image-forge.service <<'EOF'
[Unit]
Description=EVE Image Forge
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/eve-image-forge/app
ExecStart=/usr/bin/python3 /opt/eve-image-forge/app/server.py --host 0.0.0.0 --port 8088
Restart=on-failure
RestartSec=3
NoNewPrivileges=false
PrivateTmp=true
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now eve-image-forge
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "============================================================"
echo " EVE Image Forge installé"
echo " URL   : http://${IP:-ADRESSE_EVE}:8088"
echo " Jeton : $(cat "$CONF_DIR/token")"
echo "============================================================"
echo "Le jeton est aussi conservé dans $CONF_DIR/token"
