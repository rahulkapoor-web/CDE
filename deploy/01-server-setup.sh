#!/bin/bash
# Server setup script for rm2lvmbridge.mah.roche.com (RHEL/CentOS)
# PostgreSQL is on a separate server — NOT installed here
# Run as root: sudo bash 01-server-setup.sh
set -euo pipefail

echo "=== Migration Bridge — Server Setup ==="
echo "App Server:  rm2lvmbridge.mah.roche.com"
echo "DB Server:   rm2lvpgs17s1.mah.roche.com (external)"
echo ""

# ── 1. System packages ──
echo "=== 1/4 Installing system packages ==="
dnf update -y
dnf install -y epel-release
dnf install -y git curl wget gcc make openssl-devel bzip2-devel \
    libffi-devel zlib-devel readline-devel sqlite-devel \
    postgresql-devel  # client libs only, for psycopg2

# ── 2. Python 3.12 ──
echo ""
echo "=== 2/4 Installing Python 3.12 ==="
if command -v python3.12 &>/dev/null; then
    echo "Python 3.12 already installed"
else
    dnf install -y python3.12 python3.12-devel python3.12-pip
fi
python3.12 --version

# ── 3. Redis ──
echo ""
echo "=== 3/4 Installing Redis ==="
if command -v redis-server &>/dev/null; then
    echo "Redis already installed"
else
    dnf install -y redis
fi
systemctl enable redis
systemctl start redis
redis-cli ping

# ── 4. Nginx ──
echo ""
echo "=== 4/4 Installing Nginx ==="
if command -v nginx &>/dev/null; then
    echo "Nginx already installed"
else
    dnf install -y nginx
fi
systemctl enable nginx

# ── Create app user ──
echo ""
echo "=== Creating application user ==="
id -u migbridge &>/dev/null || useradd -r -m -s /bin/bash migbridge
echo "User 'migbridge' ready."

# ── Create directories ──
mkdir -p /opt/migration-bridge
chown migbridge:migbridge /opt/migration-bridge

# ── Firewall ──
echo ""
echo "=== Configuring firewall ==="
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --reload
fi

# ── Verify DB connectivity ──
echo ""
echo "=== Verifying database connectivity ==="
if command -v psql &>/dev/null; then
    echo "Testing connection to rm2lvpgs17s1.mah.roche.com..."
    psql "postgresql://rahulkapoor@rm2lvpgs17s1.mah.roche.com:5432/rahulkapoor" -c "SELECT 1;" 2>/dev/null \
        && echo "DB connection: OK" \
        || echo "DB connection: FAILED (you may need to enter password or check network)"
else
    echo "psql not found — install postgresql client to test: dnf install -y postgresql"
fi

echo ""
echo "============================================"
echo "  Server setup complete!"
echo "  Next: run 02-deploy-app.sh as migbridge"
echo "============================================"
