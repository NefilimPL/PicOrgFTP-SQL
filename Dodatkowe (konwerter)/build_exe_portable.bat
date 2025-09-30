@echo off
setlocal enabledelayedexpansion

rem ---------------------------------------------------------------------------
rem  Bootstrap variables and resolve important paths
rem ---------------------------------------------------------------------------
for %%i in ("%~dp0.") do set "SCRIPT_DIR=%%~fi"
for %%i in ("%SCRIPT_DIR%\..") do set "REPO_ROOT=%%~fi"
set "REPO_ROOT=%REPO_ROOT%\"

set "TARGET=%~1"
if not defined TARGET set "TARGET=%REPO_ROOT%PicOrgFTP-SQL.pyw"
if not exist "%TARGET%" (
    echo [ERROR] File not found: %TARGET%
    exit /b 1
)

set "BUILDER=%SCRIPT_DIR%Konwerter PY oraz PYW na EXE v0.0.3.py"
if not exist "%BUILDER%" (
    echo [ERROR] Converter helper not found: %BUILDER%
    exit /b 1
)

set "TOOLSDIR=%REPO_ROOT%build-tools"
set "PORTABLE_DIR=%TOOLSDIR%\python-portable"
set "PORTABLE_PY=%PORTABLE_DIR%\python.exe"

rem ---------------------------------------------------------------------------
rem  Locate a Python interpreter that ships with Tk
rem ---------------------------------------------------------------------------
set "PYTHON="
call :FIND_PYTHON
if not defined PYTHON (
    call :ENSURE_PORTABLE || goto :FAIL
)

pushd "%REPO_ROOT%" >nul
"%PYTHON%" "%BUILDER%" "%TARGET%"
set "ERR=%errorlevel%"
popd >nul
if not "%ERR%"=="0" goto :FAIL

echo.
echo ✅ Build finished.
exit /b 0

:FAIL
echo.
echo Build failed.
exit /b 1

rem ---------------------------------------------------------------------------
rem  FIND_PYTHON  --  search PATH, default install dirs and portable cache
rem ---------------------------------------------------------------------------
:FIND_PYTHON
for /f "delims=" %%p in ('where python 2^>nul') do (
    call :CHECK_TK "%%~fp"
    if defined PYTHON exit /b 0
)
if defined LOCALAPPDATA (
    for /f "delims=" %%p in ('where /r "%LOCALAPPDATA%\Programs\Python" python.exe 2^>nul') do (
        call :CHECK_TK "%%~fp"
        if defined PYTHON exit /b 0
    )
)
if exist "%PORTABLE_PY%" (
    call :CHECK_TK "%PORTABLE_PY%"
)
exit /b 0

rem ---------------------------------------------------------------------------
rem  CHECK_TK  --  verify interpreter has tkinter available
rem ---------------------------------------------------------------------------
:CHECK_TK
set "CAND=%~1"
if not exist "%CAND%" exit /b 0
"%CAND%" -c "import tkinter" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYTHON=%CAND%"
exit /b 0

rem ---------------------------------------------------------------------------
rem  ENSURE_PORTABLE  --  download and install a portable toolchain with Tk
rem ---------------------------------------------------------------------------
:ENSURE_PORTABLE
echo Python with Tkinter not found. Preparing portable runtime...
call :PREPARE_DIRS || exit /b 1

if exist "%PORTABLE_PY%" (
    call :CHECK_TK "%PORTABLE_PY%"
    if defined PYTHON (
        call :ENSURE_DEPS
        if defined PYTHON exit /b 0
    )
)

call :INSTALL_PORTABLE || exit /b 1
call :CHECK_TK "%PORTABLE_PY%"
if not defined PYTHON (
    echo [ERROR] Portable interpreter was installed but tkinter is unavailable.
    exit /b 1
)
call :ENSURE_DEPS || exit /b 1
exit /b 0

rem ---------------------------------------------------------------------------
rem  PREPARE_DIRS  --  ensure working directories exist
rem ---------------------------------------------------------------------------
:PREPARE_DIRS
if not exist "%TOOLSDIR%" mkdir "%TOOLSDIR%"
if exist "%PORTABLE_DIR%" goto :PREPARE_DONE
mkdir "%PORTABLE_DIR%"
:PREPARE_DONE
if exist "%PORTABLE_DIR%" exit /b 0
echo [ERROR] Unable to create %PORTABLE_DIR%
exit /b 1

rem ---------------------------------------------------------------------------
rem  INSTALL_PORTABLE  --  run the official installer with explicit options
rem ---------------------------------------------------------------------------
:INSTALL_PORTABLE
echo Downloading portable Python runtime...
set "PY_VERSION=3.11.8"
set "INSTALLER=%TOOLSDIR%\python-%PY_VERSION%-amd64.exe"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe"
if not exist "%INSTALLER%" (
    powershell -NoLogo -NoProfile -Command "$ProgressPreference='SilentlyContinue'; $u='%PY_URL%'; $p='%INSTALLER%'; if (-not (Test-Path $p)) { Invoke-WebRequest -Uri $u -OutFile $p -UseBasicParsing }" || exit /b 1
)

echo Installing portable Python...
if exist "%PORTABLE_DIR%" rmdir /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%"
set "INSTALL_ARGS=/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_test=0 Include_doc=0 Include_tcltk=1 Include_pip=1 Include_symbols=0 Shortcuts=0 SimpleInstall=0 TargetDir=""%PORTABLE_DIR%"" DefaultJustForMeTargetDir=""%PORTABLE_DIR%"" DefaultAllUsersTargetDir=""%PORTABLE_DIR%"" InstallLauncherAllUsers=0"
"%INSTALLER%" %INSTALL_ARGS% || exit /b 1
if not exist "%PORTABLE_PY%" (
    echo [ERROR] The installer did not create %PORTABLE_PY%.
    exit /b 1
)
exit /b 0

rem ---------------------------------------------------------------------------
rem  ENSURE_DEPS  --  bootstrap pip and required packages
rem ---------------------------------------------------------------------------
:ENSURE_DEPS
echo Installing pip and required packages...
set "CAND=%PORTABLE_PY%"
if not exist "%CAND%" exit /b 1
"%CAND%" -m ensurepip --upgrade >nul 2>nul || "%CAND%" -m ensurepip >nul 2>nul || exit /b 1
"%CAND%" -m pip install --upgrade pip || exit /b 1
"%CAND%" -m pip install --upgrade pyinstaller pillow mysql-connector-python certifi tkinterdnd2 openpyxl pyodbc || exit /b 1
set "PYTHON=%CAND%"
exit /b 0
