#!/bin/bash

# --- CONFIGURATION ---
# IMPORTANT: Update these values with your Jetson details
JETSON_USER="georgegabor"
JETSON_IP="192.168.1.223"
REMOTE_PATH="~/safeguard_vision_alpha"
# ---------------------

echo "🚀 Starting deployment to Jetson Orin Nano ($JETSON_IP)..."

# Use rsync to sync files, excluding large/unnecessary directories
rsync -avz --progress \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '.gemini' \
    --exclude 'safeguard.db' \
    --exclude 'deploy_to_jetson.sh' \
    --exclude 'jetson_cmd.sh' \
    ./ $JETSON_USER@$JETSON_IP:$REMOTE_PATH

if [ $? -eq 0 ]; then
    echo "✅ Deployment successful!"
    echo "Next: Run ./jetson_cmd.sh setup to install dependencies on the Jetson."
else
    echo "❌ Deployment failed. Please check your IP and SSH connection."
fi
