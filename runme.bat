@echo off

az account show >nul 2>&1
if %errorlevel% neq 0 (
    echo Not logged in to Azure. Running 'az login'...
    az login
    if %errorlevel% neq 0 (
        echo Azure login failed. Aborting.
        exit /b 1
    )
) else (
    echo Already logged in to Azure.
)

if exist ".venv\Scripts\python.exe" (
    echo Virtual environment already exists -- skipping creation.
) else (
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment. Is Python installed?
        exit /b 1
    )
)
call .venv\Scripts\activate

pip install requests
if %errorlevel% neq 0 (
    echo pip install failed.
    exit /b 1
)

python ami-lab-deploy.py
exit /b %errorlevel%
