@echo off
REM Called by DETECT.BAT with the asset id as %1. 386 and newer.
if not exist HWINFO.EXE goto missing
echo.
echo Running HWiNFO (386+), writing %1.TXT ... please wait.
HWINFO -r %1.TXT
if exist %1.TXT goto ok
echo.
echo Not auto-saved. In HWiNFO press F2 and save by hand to %1.TXT.
goto done
:missing
echo.
echo HWINFO.EXE is not on this disk. Copy it on (see bootdisk\README.md),
echo or for a 286/8088 run:  DETECT %1 6
goto done
:ok
echo.
echo HWiNFO done.
:done
