@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ================================================
echo   Budowanie PicOrgFTP-SQL (PyInstaller)
echo ================================================
echo.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"
set "SCRIPT_PATH=%PROJECT_DIR%\PicOrgFTP-SQL.pyw"

if not exist "%SCRIPT_PATH%" (
    echo [BŁĄD] Nie znaleziono pliku "%SCRIPT_PATH%".
    exit /b 1
)

set "PYTHON_CMD="
for %%C in ("py -3" "py" "python" "python3") do (
    call :TestPython %%~C
    if defined PYTHON_CMD goto :PythonFound
)

echo [BŁĄD] Nie znaleziono interpretera Python w zmiennej PATH.
exit /b 1

:PythonFound
for /f "delims=" %%P in ('%PYTHON_CMD% -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%P"
echo [INFO] Używany interpreter: %PYTHON_EXE%
echo.

echo [INFO] Sprawdzanie pip...
"%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>&1

echo [INFO] Aktualizacja pip do najnowszej wersji...
"%PYTHON_EXE%" -m pip install --upgrade pip || exit /b 1

echo [INFO] Instalowanie wymaganych pakietów...
"%PYTHON_EXE%" -m pip install --upgrade ^
    pyinstaller ^
    pillow ^
    mysql-connector-python ^
    openpyxl ^
    pyodbc ^
    tkinterdnd2 ^
    certifi || exit /b 1

set "HOOK_FILE=%TEMP%\picorgftp_sql_mysql_hook.py"
echo [INFO] Przygotowywanie pliku runtime hook...
"%PYTHON_EXE%" -c "from pathlib import Path; Path(r'%HOOK_FILE%').write_text('# Runtime hook for PicOrgFTP-SQL\ntry:\n    import importlib, mysql.connector.errors as _err\n    _ce = importlib.import_module(\"mysql.connector.locales.eng.client_error\")\n    _DICT = getattr(_ce, \"client_error\", None)\n    if isinstance(_DICT, dict) and hasattr(_err, \"get_client_error\"):\n        def _get_client_error_fixed(ec):\n            try:\n                return _DICT.get(ec)\n            except Exception:\n                return None\n        _err.get_client_error = _get_client_error_fixed\nexcept Exception:\n    pass\n', encoding='utf-8')" || exit /b 1

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

echo.
echo ================================================
echo   Gotowe! Plik EXE znajduje się w folderze dist
echo ================================================
exit /b 0

:TestPython
%* --version >nul 2>&1
if %ERRORLEVEL%==0 set "PYTHON_CMD=%*"
exit /b
