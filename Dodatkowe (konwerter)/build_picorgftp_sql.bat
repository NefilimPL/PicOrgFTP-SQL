@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ================================================
echo   Budowanie PicOrgFTP-SQL (PyInstaller)
echo ================================================
echo.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"
set "SCRIPT_PATH=%PROJECT_DIR%\PicOrgFTP-SQL.pyw"
set "LOCAL_SETTINGS_PATH=%PROJECT_DIR%\local_settings.json"

if not exist "%SCRIPT_PATH%" (
    echo [BŁĄD] Nie znaleziono pliku "%SCRIPT_PATH%".
    exit /b 1
)

set "PYTHON_VERSION=3.11.9"
set "PYTHON_INSTALLER=python-%PYTHON_VERSION%-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_INSTALLER%"
set "PYTHON_INSTALLER_PATH=%TEMP%\%PYTHON_INSTALLER%"

call :EnsurePython
if errorlevel 1 exit /b 1

call :ResolvePythonExe
if errorlevel 1 exit /b 1

echo [INFO] Sprawdzanie pip...
"%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>&1

echo [INFO] Aktualizacja pip do najnowszej wersji...
"%PYTHON_EXE%" -m pip install --upgrade pip || exit /b 1

call :InstallRequiredPackages
if errorlevel 1 exit /b 1

call :EnsurePythonReadyForBuild
if errorlevel 1 exit /b 1

echo [INFO] Konfigurowanie plików ustawień...
call :PrepareConfiguration
if errorlevel 1 exit /b 1

set "HOOK_FILE=%TEMP%\picorgftp_sql_mysql_hook.py"
echo [INFO] Przygotowywanie pliku runtime hook...
>"%HOOK_FILE%" (
    echo # Runtime hook for PicOrgFTP-SQL
    echo try:
    echo     import importlib, mysql.connector.errors as _err
    echo     _ce = importlib.import_module("mysql.connector.locales.eng.client_error")
    echo     _DICT = getattr(_ce, "client_error", None)
    echo     if isinstance(_DICT, dict) and hasattr(_err, "get_client_error"):
    echo         def _get_client_error_fixed(ec):
    echo             try:
    echo                 return _DICT.get(ec)
    echo             except Exception:
    echo                 return None
    echo         _err.get_client_error = _get_client_error_fixed
    echo except Exception:
    echo     pass
)
if not exist "%HOOK_FILE%" (
    echo [BŁĄD] Nie udało się zapisać pliku runtime hook.
    exit /b 1
)

echo [INFO] Czyszczenie poprzednich buildów...
if exist "%PROJECT_DIR%\build" rd /s /q "%PROJECT_DIR%\build"
if exist "%PROJECT_DIR%\dist" rd /s /q "%PROJECT_DIR%\dist"
if exist "%PROJECT_DIR%\PicOrgFTP-SQL.spec" del /q "%PROJECT_DIR%\PicOrgFTP-SQL.spec"

set "LOC_SOURCE=%PROJECT_DIR%\picorgftp_sql\Localization"
set "INCLUDE_LOC=0"
if exist "%LOC_SOURCE%" (
    set "INCLUDE_LOC=1"
)

echo [INFO] Uruchamianie PyInstaller...
pushd "%PROJECT_DIR%" >nul
if "%INCLUDE_LOC%"=="1" (
    "%PYTHON_EXE%" -m PyInstaller ^
        "PicOrgFTP-SQL.pyw" ^
        --name PicOrgFTP-SQL ^
        --noconsole ^
        --onefile ^
        --clean ^
        --distpath "%PROJECT_DIR%\dist" ^
        --workpath "%PROJECT_DIR%\build" ^
        --specpath "%PROJECT_DIR%\build" ^
        --add-data "%LOC_SOURCE%;picorgftp_sql/Localization" ^
        --hidden-import=mysql.connector ^
        --collect-submodules=mysql.connector ^
        --collect-submodules=mysql.connector.locales ^
        --collect-data=mysql.connector ^
        --collect-data=mysql.connector.locales ^
        --hidden-import=mysql.connector.locales.eng.client_error ^
        --hidden-import=mysql.connector.locales.fra.client_error ^
        --hidden-import=mysql.connector.locales.ita.client_error ^
        --hidden-import=mysql.connector.locales.jpn.client_error ^
        --hidden-import=mysql.connector.locales.por.client_error ^
        --hidden-import=mysql.connector.locales.rus.client_error ^
        --hidden-import=mysql.connector.locales.spa.client_error ^
        --hidden-import=mysql.connector.locales.zho.client_error ^
        --collect-submodules=tkinterdnd2 ^
        --collect-data=tkinterdnd2 ^
        --runtime-hook "%HOOK_FILE%"
) else (
    echo [OSTRZEŻENIE] Nie znaleziono katalogu Localization - pomijam dodawanie tłumaczeń.
    "%PYTHON_EXE%" -m PyInstaller ^
        "PicOrgFTP-SQL.pyw" ^
        --name PicOrgFTP-SQL ^
        --noconsole ^
        --onefile ^
        --clean ^
        --distpath "%PROJECT_DIR%\dist" ^
        --workpath "%PROJECT_DIR%\build" ^
        --specpath "%PROJECT_DIR%\build" ^
        --hidden-import=mysql.connector ^
        --collect-submodules=mysql.connector ^
        --collect-submodules=mysql.connector.locales ^
        --collect-data=mysql.connector ^
        --collect-data=mysql.connector.locales ^
        --hidden-import=mysql.connector.locales.eng.client_error ^
        --hidden-import=mysql.connector.locales.fra.client_error ^
        --hidden-import=mysql.connector.locales.ita.client_error ^
        --hidden-import=mysql.connector.locales.jpn.client_error ^
        --hidden-import=mysql.connector.locales.por.client_error ^
        --hidden-import=mysql.connector.locales.rus.client_error ^
        --hidden-import=mysql.connector.locales.spa.client_error ^
        --hidden-import=mysql.connector.locales.zho.client_error ^
        --collect-submodules=tkinterdnd2 ^
        --collect-data=tkinterdnd2 ^
        --runtime-hook "%HOOK_FILE%"
)
set "BUILD_STATUS=!ERRORLEVEL!"
popd >nul

if %BUILD_STATUS% neq 0 (
    echo [BŁĄD] Budowanie zakończone niepowodzeniem (kod %BUILD_STATUS%).
    exit /b %BUILD_STATUS%
)

set "DIST_EXE=%PROJECT_DIR%\dist\PicOrgFTP-SQL.exe"
set "FINAL_EXE=%PROJECT_DIR%\PicOrgFTP-SQL.exe"

if not exist "%DIST_EXE%" (
    echo [BŁĄD] PyInstaller zakończył działanie, ale nie odnaleziono pliku "%DIST_EXE%".
    exit /b 1
)

if exist "%FINAL_EXE%" del /q "%FINAL_EXE%" >nul 2>&1
move /y "%DIST_EXE%" "%FINAL_EXE%" >nul
if errorlevel 1 (
    echo [BŁĄD] Nie udało się przenieść pliku EXE do katalogu projektu.
    exit /b 1
)

if not exist "%FINAL_EXE%" (
    echo [BŁĄD] Wystąpił problem podczas kopiowania pliku wykonywalnego do katalogu projektu.
    exit /b 1
)

if exist "%PROJECT_DIR%\build" rd /s /q "%PROJECT_DIR%\build"
if exist "%PROJECT_DIR%\dist" rd /s /q "%PROJECT_DIR%\dist"
if exist "%PROJECT_DIR%\PicOrgFTP-SQL.spec" del /q "%PROJECT_DIR%\PicOrgFTP-SQL.spec"
if exist "%HOOK_FILE%" del /q "%HOOK_FILE%" >nul 2>&1

echo.
echo ================================================
echo   Gotowe! PicOrgFTP-SQL.exe zapisano w katalogu projektu
echo ================================================
echo Ścieżka: %FINAL_EXE%
exit /b 0

:EnsurePython
set "PYTHON_EXE="

call :FindExistingPython
if defined PYTHON_EXE (
    call :NormalizePythonExe
    call :ValidatePython
    if not errorlevel 1 goto :eof
    echo [OSTRZEŻENIE] Wykryty Python jest uszkodzony lub niekompletny - nastąpi ponowna instalacja.
    set "PYTHON_EXE="
)

echo [INFO] Nie znaleziono kompletnego środowiska Python - rozpoczynam instalację.
call :InstallPython
if errorlevel 1 exit /b 1

call :ValidatePython
if errorlevel 1 (
    echo [BŁĄD] Zainstalowany interpreter Python nadal nie przechodzi testów weryfikacyjnych.
    exit /b 1
)
exit /b 0

:FindExistingPython
set "PYTHON_EXE="

py -3 --version >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
)
if defined PYTHON_EXE goto :eof

py --version >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "delims=" %%P in ('py -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
)
if defined PYTHON_EXE goto :eof

python --version >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
)
if defined PYTHON_EXE goto :eof

python3 --version >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "delims=" %%P in ('python3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
)
goto :eof

:InstallPython
for /f "tokens=1-3 delims=." %%A in ("%PYTHON_VERSION%") do (
    set "PYTHON_MAJOR=%%A"
    set "PYTHON_MINOR=%%B"
)
set "PYTHON_MM=%PYTHON_MAJOR%%PYTHON_MINOR%"
set "PYTHON_TARGET=%LocalAppData%\Programs\Python\Python%PYTHON_MM%"
if exist "%PYTHON_INSTALLER_PATH%" del /q "%PYTHON_INSTALLER_PATH%" >nul 2>&1

echo [INFO] Pobieranie instalatora Python %PYTHON_VERSION%...
call :DownloadFile "%PYTHON_URL%" "%PYTHON_INSTALLER_PATH%"
if errorlevel 1 (
    echo [BŁĄD] Nie udało się pobrać instalatora Pythona.
    exit /b 1
)

echo [INFO] Instalowanie Python %PYTHON_VERSION%...
"%PYTHON_INSTALLER_PATH%" /quiet InstallAllUsers=0 Include_launcher=0 Include_test=0 Include_pip=1 Include_tcltk=1 PrependPath=1 TargetDir="%PYTHON_TARGET%"
if errorlevel 1 (
    echo [BŁĄD] Instalator Pythona zakończył się błędem.
    exit /b 1
)

if not exist "%PYTHON_TARGET%\python.exe" (
    echo [BŁĄD] Po instalacji nadal nie znaleziono interpretera Python.
    exit /b 1
)

set "PYTHON_EXE=%PYTHON_TARGET%\python.exe"
call :NormalizePythonExe
set "PATH=%PYTHON_TARGET%;%PYTHON_TARGET%\Scripts;%PATH%"
exit /b 0

:ValidatePython
if not defined PYTHON_EXE exit /b 1
call :NormalizePythonExe
if not exist "%PYTHON_EXE%" exit /b 1
"%PYTHON_EXE%" -c "import sys" >nul 2>&1
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -c "import tkinter" >nul 2>&1
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -c "import ensurepip" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:InstallRequiredPackages
if not defined PYTHON_EXE (
    echo [BŁĄD] Nie można zainstalować pakietów - brak interpretera Python.
    exit /b 1
)

echo [INFO] Instalowanie wymaganych pakietów...
"%PYTHON_EXE%" -m pip install --upgrade ^
    pyinstaller ^
    pillow ^
    mysql-connector-python ^
    openpyxl ^
    pyodbc ^
    tkinterdnd2 ^
    certifi || (
        echo [BŁĄD] Nie udało się zainstalować wymaganych pakietów Pythona.
        exit /b 1
    )
exit /b 0

:EnsurePythonReadyForBuild
if not defined PYTHON_EXE (
    echo [BŁĄD] Nie można zweryfikować środowiska - brak interpretera Python.
    exit /b 1
)

set "VERIFY_ATTEMPT=0"

:EnsurePythonReadyLoop
set /a VERIFY_ATTEMPT+=1

call :ValidatePython
if errorlevel 1 goto :RepairPythonEnv

"%PYTHON_EXE%" -m pip --version >nul 2>&1 || goto :RepairPythonEnv

call :CheckPythonImports
if errorlevel 1 goto :RepairPythonEnv

"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1 || goto :RepairPythonEnv

set "VERIFY_ATTEMPT="
exit /b 0

:RepairPythonEnv
if %VERIFY_ATTEMPT% geq 2 (
    echo [BŁĄD] Nie udało się przygotować kompletnego środowiska Python.
    set "VERIFY_ATTEMPT="
    exit /b 1
)

echo [OSTRZEŻENIE] Wykryto niekompletne środowisko - trwa ponowna instalacja Pythona i pakietów.
call :InstallPython
if errorlevel 1 exit /b 1

call :ValidatePython
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>&1
"%PYTHON_EXE%" -m pip install --upgrade pip || exit /b 1

call :InstallRequiredPackages
if errorlevel 1 exit /b 1

goto :EnsurePythonReadyLoop

:CheckPythonImports
if not defined PYTHON_EXE exit /b 1
set "VERIFY_SCRIPT=%TEMP%\picorgftp_verify_imports.py"
>"%VERIFY_SCRIPT%" (
    echo import importlib
    echo import sys
    echo modules = [
    echo     "tkinter",
    echo     "PyInstaller",
    echo     "PIL",
    echo     "mysql.connector",
    echo     "openpyxl",
    echo     "pyodbc",
    echo     "tkinterdnd2",
    echo     "certifi",
    echo ]
    echo missing = []
    echo for name in modules:
    echo ^    try:
    echo ^        importlib.import_module(name)
    echo ^    except Exception as exc:
    echo ^        missing.append(f"{name}: {exc}")
    echo if missing:
    echo ^    sys.stderr.write("\n".join(missing))
    echo ^    sys.exit(1)
)
"%PYTHON_EXE%" "%VERIFY_SCRIPT%" >nul 2>&1
set "VERIFY_ERROR=%ERRORLEVEL%"
del /f /q "%VERIFY_SCRIPT%" >nul 2>&1
if not "%VERIFY_ERROR%"=="0" exit /b %VERIFY_ERROR%
exit /b 0

:PrepareConfiguration
if not exist "%PROJECT_DIR%" (
    echo [BŁĄD] Nieprawidłowa ścieżka projektu: %PROJECT_DIR%
    exit /b 1
)
if not defined PYTHON_EXE (
    echo [BŁĄD] Nie odnaleziono interpretera Python do przygotowania konfiguracji.
    exit /b 1
)
set "PROJECT_DIR_ESC=%PROJECT_DIR:\=\\%"
set "LOCAL_SETTINGS_ESC=%LOCAL_SETTINGS_PATH:\=\\%"
set "HELPER_SCRIPT=%TEMP%\picorgftp_prepare_config.py"
>"%HELPER_SCRIPT%" echo import json
>>"%HELPER_SCRIPT%" echo import sys
>>"%HELPER_SCRIPT%" echo from pathlib import Path
>>"%HELPER_SCRIPT%" echo
>>"%HELPER_SCRIPT%" echo PROJECT_DIR = Path(r"%PROJECT_DIR_ESC%")
>>"%HELPER_SCRIPT%" echo LOCAL_SETTINGS = Path(r"%LOCAL_SETTINGS_ESC%")
>>"%HELPER_SCRIPT%" echo LOCAL_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
>>"%HELPER_SCRIPT%" echo data = {"base_dir_override": str(PROJECT_DIR), "language": "auto"}
>>"%HELPER_SCRIPT%" echo if LOCAL_SETTINGS.exists():
>>"%HELPER_SCRIPT%" echo ^    try:
>>"%HELPER_SCRIPT%" echo ^        existing = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
>>"%HELPER_SCRIPT%" echo ^    except Exception:
>>"%HELPER_SCRIPT%" echo ^        existing = {}
>>"%HELPER_SCRIPT%" echo ^    if isinstance(existing, dict):
>>"%HELPER_SCRIPT%" echo ^        existing["base_dir_override"] = str(PROJECT_DIR)
>>"%HELPER_SCRIPT%" echo ^        existing.setdefault("language", "auto")
>>"%HELPER_SCRIPT%" echo ^        data = existing
>>"%HELPER_SCRIPT%" echo LOCAL_SETTINGS.write_text(json.dumps(data, indent=4), encoding="utf-8")
>>"%HELPER_SCRIPT%" echo sys.path.insert(0, str(PROJECT_DIR))
>>"%HELPER_SCRIPT%" echo try:
>>"%HELPER_SCRIPT%" echo ^    from picorgftp_sql.config import load_config, save_config
>>"%HELPER_SCRIPT%" echo except Exception:
>>"%HELPER_SCRIPT%" echo ^    sys.exit(0)
>>"%HELPER_SCRIPT%" echo config = load_config()
>>"%HELPER_SCRIPT%" echo try:
>>"%HELPER_SCRIPT%" echo ^    save_config(config)
>>"%HELPER_SCRIPT%" echo except Exception:
>>"%HELPER_SCRIPT%" echo ^    pass
"%PYTHON_EXE%" "%HELPER_SCRIPT%" >nul 2>&1
set "PREP_ERROR=%ERRORLEVEL%"
del /f /q "%HELPER_SCRIPT%" >nul 2>&1
if not "%PREP_ERROR%"=="0" (
    echo [BŁĄD] Nie udało się przygotować plików ustawień (kod %PREP_ERROR%).
    exit /b %PREP_ERROR%
)
exit /b 0

:ResolvePythonExe
if not defined PYTHON_EXE (
    echo [BŁĄD] Nie udało się ustalić ścieżki do Pythona.
    exit /b 1
)
call :NormalizePythonExe

if not exist "%PYTHON_EXE%" (
    echo [BŁĄD] Zweryfikowany interpreter Python nie istnieje: %PYTHON_EXE%
    exit /b 1
)

"%PYTHON_EXE%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [BŁĄD] Interpreter Python jest uszkodzony lub nieprawidłowy: %PYTHON_EXE%
    exit /b 1
)

echo [INFO] Używany interpreter: %PYTHON_EXE%
exit /b 0

:DownloadFile
set "__URL=%~1"
set "__DEST=%~2"

where powershell >nul 2>&1
if %ERRORLEVEL%==0 (
    powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%__URL%' -OutFile '%__DEST%' -UseBasicParsing -ErrorAction Stop } catch { exit 1 }"
    if %ERRORLEVEL%==0 goto :DownloadOk
)

where curl >nul 2>&1
if %ERRORLEVEL%==0 (
    curl -f -L -o "%__DEST%" "%__URL%"
    if %ERRORLEVEL%==0 goto :DownloadOk
)

where bitsadmin >nul 2>&1
if %ERRORLEVEL%==0 (
    bitsadmin /transfer PicOrgBuild /download /priority HIGH "%__URL%" "%__DEST%" >nul
    if %ERRORLEVEL%==0 goto :DownloadOk
)

exit /b 1

:DownloadOk
exit /b 0

:NormalizePythonExe
if not defined PYTHON_EXE exit /b 0
set "PYTHON_EXE=%PYTHON_EXE:'=%"
set "PYTHON_EXE=%PYTHON_EXE:"=%"
if defined PYTHON_EXE if "%PYTHON_EXE:~0,1%"=="\\" if "%PYTHON_EXE:~2,1%"==":" set "PYTHON_EXE=%PYTHON_EXE:~1%"
if defined PYTHON_EXE if "%PYTHON_EXE:~-1%"=="\\" set "PYTHON_EXE=%PYTHON_EXE:~0,-1%"
for %%P in ("%PYTHON_EXE%") do set "PYTHON_EXE=%%~fP"
for /f "tokens=*" %%P in ("%PYTHON_EXE%") do set "PYTHON_EXE=%%P"
exit /b 0
