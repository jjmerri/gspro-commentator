@echo off
rem Check the OCR regions still line up (after a GSPro update or resolution change).
rem Run from a logged-in desktop session, not over SSH: screen capture needs an interactive desktop.
cd /d "%~dp0"
if not exist logs mkdir logs
(
  .venv\Scripts\python.exe -m commentator calibrate
  .venv\Scripts\python.exe -m commentator ocr-test
) > logs\screen-check.txt 2>&1
echo Wrote logs\screen-check.txt (regions drawn on logs\calibrate.png)
