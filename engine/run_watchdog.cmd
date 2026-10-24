@echo off
rem LLM Wiki watchdog - daily automated run.
rem Manual run: writes the watchdog report to last-run.txt; on an alert it also copies the
rem report to LAST-ALERT.txt. The daily run is the Hermes cron job "Watch Dog" (ntfy + the panel's
rem Health tab); the Windows Task Scheduler task and its popup were retired.
rem
rem TAŞINABİLİR: hiçbir yol koda gömülü değil. Betikler kendi klasöründe aranır (%~dp0), Python
rem sırayla Hermes venv'i, `py -3` ve PATH'teki `python` ile bulunur. Klasörü başka bir PC'ye
rem kopyalamak yeterlidir: kullanıcı adı, sürücü ya da venv yolu değişse de çalışır.
rem
setlocal
set "BASE=%~dp0"
set "PY="

if defined HERMES_HOME if exist "%HERMES_HOME%\hermes-agent\venv\Scripts\python.exe" set "PY=%HERMES_HOME%\hermes-agent\venv\Scripts\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not defined PY if exist "%APPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" set "PY=%APPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo !! python bulunamadi - Hermes venv'i ya da PATH'te python gerekli
  exit /b 2
)

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

"%PY%" "%BASE%watchdog.py" > "%BASE%last-run.txt" 2>&1
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  copy /Y "%BASE%last-run.txt" "%BASE%LAST-ALERT.txt" >nul
) else (
  del /Q "%BASE%LAST-ALERT.txt" 2>nul
)
exit /b %RC%
