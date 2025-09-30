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
set "PORTABLE_CANON=%PORTABLE_DIR%"
if "!PORTABLE_CANON:~-1!"=="\" set "PORTABLE_CANON=!PORTABLE_CANON:~0,-1!"

call :DETECT_PORTABLE
if not defined PYTHON (
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

:DETECT_PORTABLE
if not exist "%PORTABLE_DIR%\python.exe" call :RESCUE_PYTHON_EXE
set "PYTHON="
set "_CANDIDATE=%PORTABLE_DIR%\python.exe"
if exist "%_CANDIDATE%" (
    call :CHECK_TK_INTERPRETER "%_CANDIDATE%"
    if defined PYTHON goto :DETECT_DONE
)

set "PYTHON="
call :FIND_PYTHON "%PORTABLE_DIR%"
if defined PYTHON (
    set "_ALIGN_SRC=%PYTHON%"
    call :ALIGN_PORTABLE "!_ALIGN_SRC!" || set "PYTHON="
)

:DETECT_DONE
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
set "INSTALLER_OPTS=/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=1 Include_pip=1 Include_symbols=0 Shortcuts=0 SimpleInstall=0"
set "INSTALLER_OPTS=%INSTALLER_OPTS% TargetDir=""%PORTABLE_DIR%"" DefaultJustForMeTargetDir=""%PORTABLE_DIR%"" InstallLauncherAllUsers=0"
"%TOOLSDIR%\%PYSETUP%" %INSTALLER_OPTS% || exit /b 1

call :DETECT_PORTABLE
if not defined PYTHON (
    if defined LOCALAPPDATA call :FIND_PYTHON "%LOCALAPPDATA%\Programs\Python"  || goto :FALLBACK_ERROR
    if not defined PYTHON (
        echo Unable to locate python.exe inside %PORTABLE_DIR%.
        echo Make sure the installer can write to that directory and try again.
        exit /b 1
    )
    set "_ALIGN_SRC=%PYTHON%"
    call :ALIGN_PORTABLE "!_ALIGN_SRC!" || goto :FALLBACK_ERROR
)

echo Installing pip and build dependencies...
powershell -NoLogo -NoProfile -Command "Set-Variable -Name ProgressPreference -Value 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TOOLSDIR%\get-pip.py'" || exit /b 1

"%PYTHON%" "%TOOLSDIR%\get-pip.py" --no-warn-script-location || exit /b 1
"%PYTHON%" -m pip install --upgrade pip || exit /b 1
"%PYTHON%" -m pip install pyinstaller pillow mysql-connector-python certifi tkinterdnd2 openpyxl pyodbc || exit /b 1

del "%TOOLSDIR%\get-pip.py" >nul 2>nul
del "%TOOLSDIR%\%PYSETUP%" >nul 2>nul

"%PYTHON%" -c "import tkinter" >nul 2>nul || exit /b 1
exit /b 0

:ALIGN_PORTABLE
set "_ALIGN_SRC=%~1"
if not defined _ALIGN_SRC exit /b 1
for %%d in ("%_ALIGN_SRC%") do set "_FOUND_DIR=%%~dpd"
set "_FOUND_CANON=!_FOUND_DIR!"
if "!_FOUND_CANON:~-1!"=="\" set "_FOUND_CANON=!_FOUND_CANON:~0,-1!"
if /i "!_FOUND_CANON!"=="!PORTABLE_CANON!" (
    set "PYTHON=%PORTABLE_DIR%\python.exe"
    if not exist "%PYTHON%" (
        set "PYTHON=%_ALIGN_SRC%"
    )
    exit /b 0
)
set "_FOUND_CANON_UP=!_FOUND_CANON!"
call :TOUPPER _FOUND_CANON_UP
set "_PORTABLE_UP=!PORTABLE_CANON!"
call :TOUPPER _PORTABLE_UP
set "_PORTABLE_PREFIX=!_PORTABLE_UP!\"
set "_RELATIVE=!_FOUND_CANON_UP:%_PORTABLE_PREFIX%=!"
if not "!_RELATIVE!"=="!_FOUND_CANON_UP!" (
    call :HOIST_INTERPRETER "!_FOUND_CANON!" || exit /b 1
    set "PYTHON=%PORTABLE_DIR%\python.exe"
    exit /b 0
)

echo Detected Python at !_FOUND_CANON!; copying files into %PORTABLE_DIR%...
call :COPY_INTERPRETER "!_FOUND_CANON!" || exit /b 1
set "PYTHON=%PORTABLE_DIR%\python.exe"
exit /b 0

:HOIST_INTERPRETER
set "_SRC_DIR=%~1"
if not defined _SRC_DIR exit /b 1
if /i "!_SRC_DIR!"=="!PORTABLE_CANON!" exit /b 0
robocopy "%_SRC_DIR%" "%PORTABLE_DIR%" /e >nul
set "RC=%errorlevel%"
if %RC% GEQ 8 exit /b 1
if exist "%_SRC_DIR%" rmdir /s /q "%_SRC_DIR%"
if not exist "%PORTABLE_DIR%\python.exe" exit /b 1
exit /b 0

:RESCUE_PYTHON_EXE
for %%f in ("%PORTABLE_DIR%\python-*.exe") do (
    if exist %%~ff (
        ren "%%~ff" python.exe >nul 2>nul
        if not errorlevel 1 exit /b 0
    )
)
exit /b 0

:TOUPPER
set "_VAR=%~1"
set "_VALUE=!%~1!"
if not defined _VALUE exit /b 0
for %%A in (a b c d e f g h i j k l m n o p q r s t u v w x y z) do set "_VALUE=!_VALUE:%%A=%%A!"
set "%_VAR%=%_VALUE%"
exit /b 0

:FALLBACK_ERROR
echo Unable to configure the portable interpreter.
exit /b 1

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

:FIND_PYTHON
set "_SEARCH_ROOT=%~1"
if not defined _SEARCH_ROOT exit /b 0
if not exist "%_SEARCH_ROOT%" exit /b 0
for /f "delims=" %%p in ('where /r "%_SEARCH_ROOT%" python.exe 2^>nul') do (
    call :CHECK_TK_INTERPRETER "%%p"
    if defined PYTHON exit /b 0
)
exit /b 0

:COPY_INTERPRETER
set "_SRC=%~1"
if not defined _SRC exit /b 1
if /i "!_SRC!"=="!PORTABLE_CANON!" exit /b 0
if exist "%PORTABLE_DIR%" rmdir /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%" >nul 2>nul
robocopy "%_SRC%" "%PORTABLE_DIR%" /mir >nul
set "RC=%errorlevel%"
if %RC% GEQ 8 exit /b 1
if not exist "%PORTABLE_DIR%\python.exe" exit /b 1
exit /b 0

:ERROR
echo.
echo Build failed.
popd >nul
exit /b 1
