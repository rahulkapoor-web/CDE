#!/bin/bash
# Install systemd services and Nginx config
# Run as root: sudo bash 03-install-services.sh
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Migration Bridge — Service Installation ==="
echo ""

# ── 1. Create log directory ──
echo "=== 1/4 Creating log directory ==="
mkdir -p /var/log/migration-bridge
chown migbridge:migbridge /var/log/migration-bridge

# ── 2. Install systemd services ──
echo "=== 2/4 Installing systemd services ==="
cp "$DEPLOY_DIR/migration-bridge-api.service" /etc/systemd/system/
cp "$DEPLOY_DIR/migration-bridge-worker.service" /etc/systemd/system/
systemctl daemon-reload

systemctl enable migration-bridge-api
systemctl enable migration-bridge-worker

systemctl start migration-bridge-api
systemctl start migration-bridge-worker

echo "Backend API:  $(systemctl is-active migration-bridge-api)"
echo "Celery Worker: $(systemctl is-active migration-bridge-worker)"

# ── 3. Install Nginx config ──
echo ""
echo "=== 3/4 Configuring Nginx ==="
cp "$DEPLOY_DIR/nginx-migration-bridge.conf" /etc/nginx/conf.d/migration-bridge.conf

# Remove default site if it exists
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

nginx -t
systemctl restart nginx
echo "Nginx: $(systemctl is-active nginx)"

# ── 4. Verify ──
echo ""
echo "=== 4/4 Verifying deployment ==="
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ || echo "000")
API_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/docs || echo "000")

echo "Frontend (http://localhost/): $HTTP_CODE"
echo "Backend  (http://localhost/docs): $API_CODE"

echo ""
echo "============================================"
echo "  Deployment complete!"
echo ""
echo "  Access the application at:"
echo "  http://rm2lvmbridge.mah.roche.com"
echo ""
echo "  Manage services:"
echo "  systemctl status migration-bridge-api"
echo "  systemctl status migration-bridge-worker"
echo "  journalctl -u migration-bridge-api -f"
echo "============================================"
