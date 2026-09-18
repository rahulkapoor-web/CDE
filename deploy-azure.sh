#!/bin/bash
# Deploy Migration Bridge to Azure Container Apps
# Prerequisites: Azure CLI installed and logged in (az login)
set -e

# ── Configuration ──────────────────────────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-migration-bridge-rg}"
LOCATION="${LOCATION:-westeurope}"
ACR_NAME="${ACR_NAME:-migrationbridgeacr}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-migration-bridge-env}"
APP_NAME="${APP_NAME:-migration-bridge}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 24)}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
CREDENTIAL_KEY="${CREDENTIAL_ENCRYPTION_KEY:-$(openssl rand -base64 32)}"

echo "=== Migration Bridge — Azure Deployment ==="
echo "Resource Group: $RESOURCE_GROUP"
echo "Location:       $LOCATION"
echo "ACR:            $ACR_NAME"
echo ""

# ── Step 1: Resource Group ─────────────────────────────────────
echo "[1/7] Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

# ── Step 2: Azure Container Registry ──────────────────────────
echo "[2/7] Creating container registry..."
az acr create --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" --sku Basic --admin-enabled true -o none

ACR_SERVER="$ACR_NAME.azurecr.io"
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

# ── Step 3: Build and push images ─────────────────────────────
echo "[3/7] Building and pushing backend image..."
az acr build --registry "$ACR_NAME" \
    --image migration-bridge-backend:latest \
    --file backend/Dockerfile ./backend

echo "[3/7] Building and pushing frontend image..."
az acr build --registry "$ACR_NAME" \
    --image migration-bridge-frontend:latest \
    --file frontend/Dockerfile ./frontend

# ── Step 4: Azure Database for PostgreSQL ─────────────────────
echo "[4/7] Creating PostgreSQL Flexible Server..."
az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" \
    --name "${APP_NAME}-db" \
    --location "$LOCATION" \
    --admin-user postgres \
    --admin-password "$POSTGRES_PASSWORD" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --storage-size 32 \
    --version 16 \
    --yes -o none 2>/dev/null || echo "  (DB may already exist)"

# Allow Azure services to connect
az postgres flexible-server firewall-rule create \
    --resource-group "$RESOURCE_GROUP" \
    --name "${APP_NAME}-db" \
    --rule-name AllowAzure \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0 -o none 2>/dev/null || true

# Create the database
az postgres flexible-server db create \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "${APP_NAME}-db" \
    --database-name migration_bridge -o none 2>/dev/null || true

PG_HOST="${APP_NAME}-db.postgres.database.azure.com"

# ── Step 5: Container Apps Environment ────────────────────────
echo "[5/7] Creating Container Apps environment..."
az containerapp env create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ENVIRONMENT_NAME" \
    --location "$LOCATION" -o none 2>/dev/null || echo "  (Environment may already exist)"

# ── Step 6: Deploy backend ────────────────────────────────────
echo "[6/7] Deploying backend container app..."
az containerapp create \
    --resource-group "$RESOURCE_GROUP" \
    --name "${APP_NAME}-backend" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$ACR_SERVER/migration-bridge-backend:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 8000 \
    --ingress internal \
    --min-replicas 1 \
    --max-replicas 3 \
    --cpu 1.0 \
    --memory 2.0Gi \
    --env-vars \
        "DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@${PG_HOST}:5432/migration_bridge" \
        "DATABASE_URL_SYNC=postgresql+psycopg2://postgres:${POSTGRES_PASSWORD}@${PG_HOST}:5432/migration_bridge" \
        "REDIS_URL=redis://localhost:6379/0" \
        "SECRET_KEY=${SECRET_KEY}" \
        "CREDENTIAL_ENCRYPTION_KEY=${CREDENTIAL_KEY}" \
        "WORKERS=2" \
    -o none

BACKEND_FQDN=$(az containerapp show \
    --resource-group "$RESOURCE_GROUP" \
    --name "${APP_NAME}-backend" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

# ── Step 7: Deploy frontend ──────────────────────────────────
echo "[7/7] Deploying frontend container app..."

# Create a custom nginx config that points to the backend FQDN
cat > /tmp/nginx-azure.conf <<NGINX
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass https://${BACKEND_FQDN};
        proxy_set_header Host ${BACKEND_FQDN};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
NGINX

az containerapp create \
    --resource-group "$RESOURCE_GROUP" \
    --name "${APP_NAME}-frontend" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$ACR_SERVER/migration-bridge-frontend:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 80 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 3 \
    --cpu 0.5 \
    --memory 1.0Gi \
    -o none

FRONTEND_URL=$(az containerapp show \
    --resource-group "$RESOURCE_GROUP" \
    --name "${APP_NAME}-frontend" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "App URL:         https://$FRONTEND_URL"
echo "Backend (int):   https://$BACKEND_FQDN"
echo "PostgreSQL:      $PG_HOST"
echo ""
echo "Credentials (save these):"
echo "  POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
echo "  SECRET_KEY=$SECRET_KEY"
echo "  CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_KEY"
echo ""
echo "NOTE: The frontend nginx config needs to be updated with the"
echo "backend FQDN. Update frontend/nginx.conf proxy_pass to:"
echo "  https://$BACKEND_FQDN"
echo "Then rebuild and redeploy the frontend image."
