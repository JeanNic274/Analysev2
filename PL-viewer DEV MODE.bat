@echo off

REM Edit base path to work:

set DIRECTORY="C:...\Analysev2"


cd /d %DIRECTORY%

:restart
"AnalyseV2\Scripts\python.exe" "main.py"
goto restart