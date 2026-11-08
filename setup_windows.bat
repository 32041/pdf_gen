@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
python check_environment.py
if errorlevel 1 exit /b 1
echo Setup complete. Run: python generate.py --type paper --count 20 --output outputs_more
pause
