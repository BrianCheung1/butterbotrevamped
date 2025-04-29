:: Move to the Scripts directory inside env
@echo off
cd /d "%~dp0env\Scripts"

:: Activate the environment
call activate

:: Go up two directories (out of Scripts\ and env\)
cd ../..

:: Run your main bot file
py main.py

pause