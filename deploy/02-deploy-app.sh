#!/bin/bash
# Deploy Migration Bridge application
# Run as migbridge user: sudo -u migbridge bash 02-deploy-app.sh
set -euo pipefail

APP_DIR="/opt/migration-bridge"
REPO_URL="https://github.com/rahulkapoor-web/CDE.git"
BRANCH="feature/migration-bridge"

# ── Database details ──
DB_HOST="rm2lvpgs17s1.mah.roche.com"
DB_PORT="5432"
DB_NAME="rahulkapoor"
DB_USER="rahulkapoor"

echo "=== Migration Bridge — Application Deployment ==="
echo "App Server: rm2lvmbridge.mah.roche.com"
echo "DB Server:  $DB_HOST"
echo ""

# ── 1. Clone / update repo ──
echo "=== 1/5 Cloning repository ==="
if [ -d "$APP_DIR/repo" ]; then
    cd "$APP_DIR/repo"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
    echo "Repository updated."
else
    git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR/repo"
    echo "Repository cloned."
fi

# ── 2. Backend setup ──
echo ""
echo "=== 2/5 Setting up backend ==="
cd "$APP_DIR/repo/backend"

python3.12 -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# ── 3. Environment file ──
echo ""
echo "=== 3/5 Creating environment config ==="
if [ ! -f "$APP_DIR/.env" ]; then
    SECRET_KEY=$(python3.12 -c "import secrets; print(secrets.token_urlsafe(48))")
    ENCRYPTION_KEY=$(python3.12 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    # Prompt for DB password
    echo ""
    echo "Enter PostgreSQL password for user '$DB_USER':"
    read -s DB_PASSWORD
    echo ""

    cat > "$APP_DIR/.env" << EOF
# Migration Bridge — Production Configuration
# App Server:  rm2lvmbridge.mah.roche.com
# DB Server:   ${DB_HOST}

# Database (external PostgreSQL)
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
DATABASE_URL_SYNC=postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}

# Redis (local)
REDIS_URL=redis://localhost:6379/0

# Security keys (auto-generated)
SECRET_KEY=${SECRET_KEY}
CREDENTIAL_ENCRYPTION_KEY=${ENCRYPTION_KEY}

# Workers
WORKERS=4
EOF
    chmod 600 "$APP_DIR/.env"
    echo "Environment file created at $APP_DIR/.env (permissions: 600)"
else
    echo "Environment file already exists, skipping."
fi

# ── 4. Run database migrations ──
echo ""
echo "=== 4/5 Running database migrations ==="
cd "$APP_DIR/repo/backend"
source "$APP_DIR/venv/bin/activate"
set -a && source "$APP_DIR/.env" && set +a
PYTHONPATH="$APP_DIR/repo/backend" alembic upgrade head
echo "Migrations complete."

# ── 5. Build frontend ──
echo ""
echo "=== 5/5 Building frontend ==="
cd "$APP_DIR/repo/frontend"

if ! command -v node &>/dev/null; then
    echo "Installing Node.js 20..."
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo dnf install -y nodejs
fi

npm ci
npm run build

# Copy built frontend to serve directory
mkdir -p "$APP_DIR/frontend-dist"
cp -r dist/* "$APP_DIR/frontend-dist/"
echo "Frontend built."

echo ""
echo "============================================"
echo "  Application deployed!"
echo "  Next: install systemd services and nginx"
echo "  Run: sudo bash 03-install-services.sh"
echo "============================================"
