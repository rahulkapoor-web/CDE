# Deploying Migration Bridge

## Your Infrastructure

| Role | Server |
|------|--------|
| **App Server** | `rm2lvmbridge.mah.roche.com` (RHEL) |
| **DB Server** | `rm2lvpgs17s1.mah.roche.com` (PostgreSQL) |
| **DB Name** | `rahulkapoor` |
| **DB User** | `rahulkapoor` |
| **DB Port** | `5432` |

## Before You Start

1. You need SSH or terminal access to `rm2lvmbridge.mah.roche.com`
2. You need sudo/root privileges on that server
3. Have your PostgreSQL password ready

**How to get access:** If you don't have SSH access yet, raise a ServiceNow request for "SSH access to rm2lvmbridge.mah.roche.com" or ask your server admin to grant your Roche ID access.

## Deployment — 3 Steps

### Step 1 — Copy deploy files to the app server

From any machine that has access to both this repo and the server:

```bash
scp -r deploy/ your-roche-id@rm2lvmbridge.mah.roche.com:/tmp/deploy/
```

Or if you're already on the server, clone the repo directly:

```bash
git clone -b feature/migration-bridge https://github.com/rahulkapoor-web/CDE.git /tmp/cde
cp -r /tmp/cde/deploy /tmp/deploy
```

### Step 2 — SSH into the server and run scripts

```bash
ssh your-roche-id@rm2lvmbridge.mah.roche.com
```

Then run these 3 commands in order:

```bash
# 1. Install Python, Redis, Nginx (no PostgreSQL — it's on the separate DB server)
sudo bash /tmp/deploy/01-server-setup.sh

# 2. Clone app, build frontend, run DB migrations (will ask for your DB password)
sudo -u migbridge bash /tmp/deploy/02-deploy-app.sh

# 3. Start all services, configure Nginx, enable auto-start on reboot
sudo bash /tmp/deploy/03-install-services.sh
```

### Step 3 — Open in browser

Go to: **http://rm2lvmbridge.mah.roche.com**

That's it. The app is running and will auto-restart on server reboot.

## Managing the Application

| What you want to do | Command |
|---------------------|---------|
| Check if API is running | `systemctl status migration-bridge-api` |
| Check if worker is running | `systemctl status migration-bridge-worker` |
| Restart API | `sudo systemctl restart migration-bridge-api` |
| Restart worker | `sudo systemctl restart migration-bridge-worker` |
| View live API logs | `journalctl -u migration-bridge-api -f` |
| View live worker logs | `journalctl -u migration-bridge-worker -f` |
| View Nginx logs | `tail -f /var/log/nginx/migration-bridge-access.log` |

## Updating After Code Changes

```bash
ssh your-roche-id@rm2lvmbridge.mah.roche.com

# Pull latest code
cd /opt/migration-bridge/repo
sudo -u migbridge git pull origin feature/migration-bridge

# Backend update
source /opt/migration-bridge/venv/bin/activate
cd backend && pip install -r requirements.txt
PYTHONPATH=/opt/migration-bridge/repo/backend alembic upgrade head
sudo systemctl restart migration-bridge-api
sudo systemctl restart migration-bridge-worker

# Frontend update
cd /opt/migration-bridge/repo/frontend
npm ci && npm run build
cp -r dist/* /opt/migration-bridge/frontend-dist/
```

## File Locations on the Server

| What | Path |
|------|------|
| Application code | `/opt/migration-bridge/repo/` |
| Python virtualenv | `/opt/migration-bridge/venv/` |
| Environment config (.env) | `/opt/migration-bridge/.env` |
| Built frontend files | `/opt/migration-bridge/frontend-dist/` |
| API logs | `/var/log/migration-bridge/api-*.log` |
| Worker logs | `/var/log/migration-bridge/worker.log` |
| Nginx config | `/etc/nginx/conf.d/migration-bridge.conf` |

## Troubleshooting

**Can't connect to database:**
```bash
# Test from app server
psql "postgresql://rahulkapoor@rm2lvpgs17s1.mah.roche.com:5432/rahulkapoor" -c "SELECT 1;"
```
If this fails, check with global.datastores@roche.com (your DB service team).

**App not loading in browser:**
```bash
systemctl status nginx
systemctl status migration-bridge-api
# Check if port 80 is open in firewall
firewall-cmd --list-all
```

**Services not starting after reboot:**
```bash
systemctl enable migration-bridge-api
systemctl enable migration-bridge-worker
systemctl enable redis
systemctl enable nginx
```
