#!/bin/bash
az login
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python3 ami-lab-deploy.py