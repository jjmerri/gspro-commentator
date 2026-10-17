@echo off
rem Launch the booth minimized. Double-click for a league night; close the "Golf Booth" window to stop.
cd /d "%~dp0"
start "Golf Booth" /min cmd /k .venv\Scripts\python.exe -m commentator run
