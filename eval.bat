@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run run.bat once first. & pause & exit /b 1)
call ".venv\Scripts\activate.bat"
if not exist "data\warehouse.db" python data\generate_data.py
echo === Safety tests ===
python tests\test_safety.py
echo.
echo === Evaluation (26 questions) ===
python eval\run_eval.py
pause
