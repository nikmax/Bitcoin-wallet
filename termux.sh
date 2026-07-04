#!/bin/bash
pkg update
pkg install python clang rust make openssl libffi
python -m pip install --upgrade pip setuptools wheel

pip install --no-cache-dir -r requirements.termux

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

