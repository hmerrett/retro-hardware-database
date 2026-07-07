@echo off
REM Usage: DETECT RH-nnnn [6]
REM   RH-nnnn   asset id -> writes A:\RH-nnnn.TXT
REM   (nothing) 386 or newer -> HWiNFO
REM   6         286 or 8088  -> MSD
REM No CHOICE/menu on purpose: branching on the argument works the same on
REM MS-DOS 5.0 and 6.22 and needs no CHOICE.COM.
if "%1"=="" goto usage
if "%2"=="6" goto low
call DET386.BAT %1
goto done
:low
call DETMSD.BAT %1
goto done
:usage
echo.
echo Usage:  DETECT RH-nnnn        386 or newer  (HWiNFO)
echo         DETECT RH-nnnn 6      286 or 8088   (MSD)
goto end
:done
echo.
if exist A:\%1.TXT echo Saved A:\%1.TXT -- move the floppy to the next machine.
if not exist A:\%1.TXT echo Report NOT saved -- see the messages above.
echo.
pause
:end
