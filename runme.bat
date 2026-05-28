@echo off

az account show >nul 2>&1
if %errorlevel% neq 0 (
    echo Not logged in to Azure. Running 'az login'...
    az login
) else (
    echo Already logged in to Azure.
)

python -m venv .venv
call .venv\Scripts\activate
pip install requests
python ami-lab-deploy.py
