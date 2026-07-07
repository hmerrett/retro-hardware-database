@echo off
REM Called by DETECT.BAT with the asset id as %1. 386 and newer.
echo.
echo Running HWiNFO (386+), writing A:\%1.TXT ... please wait.
HWINFO -r A:\%1.TXT
if exist A:\%1.TXT goto ok
echo.
echo Not auto-saved. In HWiNFO, press F2 and save the report by hand
echo to A:\%1.TXT  (the -r switch stalls on some machines).
goto done
:ok
echo.
echo HWiNFO done.
:done
