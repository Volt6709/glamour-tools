@echo off
echo Setting up Glamour Tools...
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
echo.
echo Setup complete! Run start.bat to launch.
pause
