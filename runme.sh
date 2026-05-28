#!/bin/bash
set -e

az account show > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Not logged in to Azure. Running 'az login'..."
    az login
else
    echo "Already logged in to Azure."
fi

if [ ! -f ".venv/bin/python3" ]; then
    python3 -m venv .venv
else
    echo "Virtual environment already exists -- skipping creation."
fi
source .venv/bin/activate
python3 ami-lab-deploy.py