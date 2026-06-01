#Requires -Version 5.1
<#
.SYNOPSIS
    Azure Lab 6.1x - Gigamon V Series Deployment Wrapper v1.0 (PowerShell)
.DESCRIPTION
    PowerShell equivalent of runme.bat / runme.sh.
    Checks Azure CLI login state, creates a Python venv, installs
    dependencies, and launches the main deployment script.
#>

$ErrorActionPreference = 'Stop'

$startTime = Get-Date

# -- Azure CLI login check ----------------------------------------------------
Write-Host "Checking Azure CLI login status..."
$azStatus = az account show 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in to Azure. Running 'az login'..."
    az login
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Azure login failed. Aborting."
        exit 1
    }
}
else {
    Write-Host "Already logged in to Azure."
}

# -- Python virtual environment -----------------------------------------------
$venvPython = ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "Virtual environment already exists -- skipping creation."
}
else {
    Write-Host "Creating Python virtual environment..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment. Is Python installed?"
        exit 1
    }
}

# Ensure we have permission to run the activation script in this process
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force -ErrorAction SilentlyContinue

# Activate -- PowerShell uses a different activate script to cmd/bash
. ".\.venv\Scripts\Activate.ps1"

# -- Install dependencies -----------------------------------------------------
Write-Host "Installing Python dependencies..."
pip install requests
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed."
    exit 1
}

# -- Launch deployment --------------------------------------------------------
Write-Host "Launching deployment..."
python ami-lab-deploy.py
$deployExitCode = $LASTEXITCODE

$endTime = Get-Date
$elapsedTime = $endTime - $startTime
Write-Host ("Deployment elapsed time: {0:hh\:mm\:ss}" -f $elapsedTime)

exit $deployExitCode
