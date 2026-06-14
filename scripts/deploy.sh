#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/traveldiary"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
SERVICE_NAME="traveldiary.service"

echo "[deploy] moving to $APP_DIR"
cd "$APP_DIR"

echo "[deploy] pulling latest code"
git pull --ff-only origin main

echo "[deploy] installing backend dependencies"
source "$BACKEND_DIR/.venv/bin/activate"
pip install -r "$BACKEND_DIR/requirements.txt"

echo "[deploy] building frontend"
cd "$FRONTEND_DIR"
npm install
npm run build

echo "[deploy] restarting backend service"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
