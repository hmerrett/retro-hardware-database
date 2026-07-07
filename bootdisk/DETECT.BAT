@echo off
REM Usage: DETECT RH-nnnn [3|6]
REM   RH-nnnn  the machine's asset id (becomes A:\RH-nnnn.TXT)
REM   3        force the 386+ path (HWiNFO)
REM   6        force the 286/8088 path (MSD)
REM No 2nd arg: use the CHOICE menu if present (MS-DOS 6.x / FreeDOS),
REM otherwise default to 386+ (MS-DOS 5.0 has no CHOICE).
if "%1"=="" goto usage
if "%2"=="6" goto low
if "%2"=="3" goto hi
if exist A:\CHOICE.COM goto menu
echo.
echo (no CHOICE on this DOS -- assuming 386+. For a 286/8088: DETECT %1 6)
goto hi
:menu
echo.
CHOICE /C:36 /T:3,5 Press 3 for 386-or-newer or 6 for 286/8088
if errorlevel 2 goto low
:hi
call DET386.BAT %1
goto done
:low
call DETMSD.BAT %1
goto done
:usage
echo.
echo Usage:  DETECT RH-nnnn        (eg  DETECT RH-0005)
echo         DETECT RH-nnnn 3      force 386+  (HWiNFO)
echo         DETECT RH-nnnn 6      force 286/8088  (MSD)
goto end
:done
echo.
if exist A:\%1.TXT echo Saved A:\%1.TXT -- move the floppy to the next machine.
if not exist A:\%1.TXT echo Report NOT saved -- see the messages above.
echo.
pause
:end
