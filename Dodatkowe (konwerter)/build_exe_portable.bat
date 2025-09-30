@echo off
setlocal enabledelayedexpansion

for %%i in ("%~dp0") do set "ROOT=%%~fi\"
for %%i in ("%ROOT%..") do set "REPO_ROOT=%%~fi\"

set "TARGET=%~1"
if not defined TARGET set "TARGET=%REPO_ROOT%PicOrgFTP-SQL.pyw"
if not exist "%TARGET%" (
    echo File not found: %TARGET%
    exit /b 1
)

pushd "%REPO_ROOT%" >nul

set "PYTHON="
where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where python ^| findstr /i "python.exe"') do (
        call :CHECK_TK_INTERPRETER "%%i"
        if defined PYTHON goto :HAVE_PYTHON
    )
)

set "TOOLSDIR=%REPO_ROOT%build-tools"
set "PORTABLE_DIR=%TOOLSDIR%\python-portable"
set "PYTHON=%PORTABLE_DIR%\python.exe"
if not exist "%PYTHON%" (
    call :SETUP_PORTABLE || goto :ERROR
)

:HAVE_PYTHON

set "BUILDER=%ROOT%Konwerter PY oraz PYW na EXE v0.0.3.py"
"%PYTHON%" "%BUILDER%" "%TARGET%"
if errorlevel 1 goto :ERROR

echo.
echo Done.
popd >nul
exit /b 0

:SETUP_PORTABLE
echo Python not found in PATH or missing tkinter. Downloading portable runtime...
if not exist "%TOOLSDIR%" mkdir "%TOOLSDIR%"
set VERSION=3.11.8
set PYSETUP=python-!VERSION!-amd64.exe
set PYURL=https://www.python.org/ftp/python/!VERSION!/%PYSETUP%

powershell -NoLogo -NoProfile -Command "Set-Variable -Name ProgressPreference -Value 'SilentlyContinue'; $out = '%TOOLSDIR%\%PYSETUP%'; Invoke-WebRequest -Uri '%PYURL%' -OutFile $out; if (-not (Test-Path $out)) { exit 1 }" || exit /b 1

if exist "%PORTABLE_DIR%" (
    rmdir /s /q "%PORTABLE_DIR%"
)
"%TOOLSDIR%\%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=1 Include_pip=1 Include_symbols=0 Shortcuts=0 TargetDir="%PORTABLE_DIR%" || exit /b 1

echo Installing pip and build dependencies...
powershell -NoLogo -NoProfile -Command "Set-Variable -Name ProgressPreference -Value 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TOOLSDIR%\get-pip.py'" || exit /b 1

"%PYTHON%" "%TOOLSDIR%\get-pip.py" --no-warn-script-location || exit /b 1
"%PYTHON%" -m pip install --upgrade pip || exit /b 1
"%PYTHON%" -m pip install pyinstaller pillow mysql-connector-python certifi tkinterdnd2 openpyxl pyodbc || exit /b 1

del "%TOOLSDIR%\get-pip.py" >nul 2>nul
del "%TOOLSDIR%\%PYSETUP%" >nul 2>nul

"%PYTHON%" -c "import tkinter" >nul 2>nul || exit /b 1
set "PYTHON=%PORTABLE_DIR%\python.exe"
exit /b 0

:CHECK_TK_INTERPRETER
set "TMP_PY=%~1"
"%TMP_PY%" -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo Detected Python at %TMP_PY% but tkinter module is missing.
    set "PYTHON="
) else (
    set "PYTHON=%TMP_PY%"
)
exit /b 0

:ERROR
echo.
echo Build failed.
popd >nul
exit /b 1
