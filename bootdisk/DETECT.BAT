@echo off
echo.
echo Retro Hardware Database -- hardware detector
echo.
REM CHOICE ships with FreeDOS and MS-DOS 6+. On older DOS it is missing,
REM so run DETECT16.BAT (8086/286) or DET386.BAT (386+) directly instead.
CHOICE /C:36 /T:3,5 Press 3 for 386-or-newer or 6 for 286-or-older
if errorlevel 2 goto old
call DET386.BAT
goto end
:old
call DETECT16.BAT
:end
