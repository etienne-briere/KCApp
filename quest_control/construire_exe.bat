@echo off
REM Reconstruit QuestControl.exe a partir de quest_gui.py.
REM A relancer a chaque modification de quest.py ou quest_gui.py.
REM L'exe doit rester dans quest_control\, a cote de config.json.

cd /d "%~dp0"

python -m PyInstaller --onefile --noconsole --name QuestControl ^
  --distpath dist_exe --workpath build_exe --specpath build_exe ^
  quest_gui.py

if errorlevel 1 (
    echo.
    echo Echec de la construction.
    pause
    exit /b 1
)

move /Y dist_exe\QuestControl.exe QuestControl.exe
rmdir /S /Q dist_exe
rmdir /S /Q build_exe

echo.
echo QuestControl.exe reconstruit.
pause
