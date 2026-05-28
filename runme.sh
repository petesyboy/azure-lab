#!/bin/bash
set -e

az login
python3 -m venv .venv
source .venv/bin/activate
python3 ami-lab-deploy.py