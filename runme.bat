@echo off
az login
python -m venv .venv
call .venv\Scripts\activate
pip install requests
python ami-lab-deploy.py
