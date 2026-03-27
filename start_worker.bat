@echo off
setlocal
cd /d %~dp0
call .venv\Scripts\activate
python main.py
