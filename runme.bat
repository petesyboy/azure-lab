@echo off

for /f %%i in ('powershell -NoProfile -Command "(Get-Date).Ticks"') do set START_TICKS=%%i

where az >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Azure CLI 'az' is not installed or not in PATH.
    echo Please install Azure CLI: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows
    exit /b 1
)

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

rem --- Intercept 'check-fabric' argument ---
if "%~1"=="check-fabric" (
    echo Running fabric health checks...
    if exist .venv\Scripts\activate.bat (
        call .venv\Scripts\activate.bat
    )
    python check_fabric.py
    exit /b %errorlevel%
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
set DEPLOY_EXIT_CODE=%errorlevel%

for /f %%i in ('powershell -NoProfile -Command "(Get-Date).Ticks"') do set END_TICKS=%%i
if %DEPLOY_EXIT_CODE% equ 0 (
    set STATUS_MSG=succeeded
) else (
    set STATUS_MSG=failed
)
powershell -NoProfile -Command "$ts = [timespan]::FromTicks(%END_TICKS% - %START_TICKS%); Write-Host ('Deployment %STATUS_MSG% after {0:hh\:mm\:ss}' -f $ts)"

exit /b %DEPLOY_EXIT_CODE%
