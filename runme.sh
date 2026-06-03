#!/bin/bash

# --- Intercept 'check-fabric' argument ---
if [ "$1" == "check-fabric" ]; then
    echo "Running fabric health checks..."
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
    python3 check_fabric.py
    exit $?
fi

START_TIME=$(date +%s)

echo "Checking Azure CLI login status..."
if ! az account show > /dev/null 2>&1; then
    echo "Not logged in to Azure. Running 'az login'..."
    if ! az login; then
        echo "Azure login failed. Aborting."
        exit 1
    fi
else
    echo "Already logged in to Azure."
fi

if [ ! -f ".venv/bin/python3" ]; then
    echo "Creating Python virtual environment..."
    if ! python3 -m venv .venv; then
        echo "Failed to create virtual environment. Is Python installed?"
        exit 1
    fi
else
    echo "Virtual environment already exists -- skipping creation."
fi

source .venv/bin/activate

echo "Installing Python dependencies..."
if ! pip install requests; then
    echo "pip install failed."
    exit 1
fi

echo "Launching deployment..."
python3 ami-lab-deploy.py
DEPLOY_EXIT_CODE=$?

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
FORMATTED_TIME=$(printf '%02d:%02d:%02d' $((ELAPSED/3600)) $((ELAPSED%3600/60)) $((ELAPSED%60)))
echo "Deployment elapsed time: ${FORMATTED_TIME}"

exit $DEPLOY_EXIT_CODE