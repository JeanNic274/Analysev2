@echo off

REM Edit base path to work:

set DIRECTORY="D:\JHoule\Code\AnalyseV2"


cd /d %DIRECTORY%

:restart
".venv-Houle\Scripts\python.exe" "main.py"
goto restart