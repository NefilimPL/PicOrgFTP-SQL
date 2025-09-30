@echo off
setlocal enabledelayedexpansion

set SCRIPT=%~1
if "%SCRIPT%"=="" (
    echo Usage: %~nx0 path\to\app.pyw
    exit /b 1
)
if not exist "%SCRIPT%" (
    echo File not found: %SCRIPT%
    exit /b 1
)

set ROOT=%~dp0
pushd "%ROOT%" >nul

where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where python ^| findstr /i "python.exe"') do (
        set PYTHON=%%i
        goto :HAVE_PYTHON
    )
)

set TOOLSDIR=%ROOT%build-tools
set PORTABLE_DIR=%TOOLSDIR%\python-embed
set PYTHON=%PORTABLE_DIR%\python.exe
if not exist "%PYTHON%" (
    call :SETUP_PORTABLE || goto :ERROR
)

:HAVE_PYTHON

set BUILDER=%ROOT%Dodatkowe (konwerter)\Konwerter PY oraz PYW na EXE v0.0.3.py
"%PYTHON%" "%BUILDER%"
if errorlevel 1 goto :ERROR

echo.
echo Done.
popd >nul
exit /b 0

:SETUP_PORTABLE
echo Python not found in PATH. Downloading portable runtime...
if not exist "%TOOLSDIR%" mkdir "%TOOLSDIR%"
set VERSION=3.11.8
set PYZIP=python-!VERSION!-embed-amd64.zip
set PYURL=https://www.python.org/ftp/python/!VERSION!/%PYZIP%

powershell -NoLogo -NoProfile -Command "^"
  $ProgressPreference='SilentlyContinue'; ^
  $out='%TOOLSDIR%\\%PYZIP%'; ^
  Invoke-WebRequest -Uri '%PYURL%' -OutFile $out; ^
  if (-not (Test-Path $out)) { exit 1 }" || exit /b 1

powershell -NoLogo -NoProfile -Command "^"
  $zip='%TOOLSDIR%\\%PYZIP%'; ^
  $dest='%PORTABLE_DIR%'; ^
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }; ^
  Expand-Archive -Path $zip -DestinationPath $dest; ^
  (Get-Content "$dest\\python311._pth") -replace '#import site','import site' | Set-Content "$dest\\python311._pth"; ^
  Remove-Item $zip" || exit /b 1

echo Installing pip and build dependencies...
powershell -NoLogo -NoProfile -Command "^"
  $ProgressPreference='SilentlyContinue'; ^
  Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TOOLSDIR%\\get-pip.py'" || exit /b 1

"%PYTHON%" "%TOOLSDIR%\get-pip.py" --no-warn-script-location || exit /b 1
"%PYTHON%" -m pip install --upgrade pip || exit /b 1
"%PYTHON%" -m pip install pyinstaller pillow mysql-connector-python certifi || exit /b 1

del "%TOOLSDIR%\get-pip.py" >nul 2>nul
exit /b 0

:ERROR
echo.
echo Build failed.
popd >nul
exit /b 1
