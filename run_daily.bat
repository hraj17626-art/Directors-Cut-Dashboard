@echo off
REM Double-click this file after you put the new data in the "incoming" folder.
cd /d %~dp0
python build.py
if errorlevel 1 (echo Build failed. & pause & exit /b 1)
git add docs
git commit -m "Data update %date% %time%"
git push
echo.
echo Done. The website updates in about 1 minute.
pause
