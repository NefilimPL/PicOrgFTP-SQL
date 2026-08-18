@echo off
setlocal
cd /d "%~dp0"

echo.
echo Budowanie lokalnego EXE z OCR
echo.
echo D - silnik OCR w EXE, model zostanie pobrany przy pierwszym uzyciu
echo M - silnik i model w EXE, gotowy do pracy offline
choice /c DM /n /m "Wybierz wariant"

if errorlevel 2 goto :embedded_model

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_local_exe.ps1" -IncludeVision
goto :finish

:embedded_model
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_local_exe.ps1" -IncludeVision -IncludeVisionModels

:finish
if errorlevel 1 pause
endlocal
