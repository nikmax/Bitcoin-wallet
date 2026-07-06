#!/bin/bash

cd /wallet
pip3 install --no-cache-dir -r requirements.txt

python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
