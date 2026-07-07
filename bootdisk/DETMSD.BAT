@echo off
REM Called by DETECT.BAT with the asset id as %1. 8088/286 (and any DOS PC).
REM MSD /P writes the full report to the named file with no prompts.
echo.
echo Running MSD (8088/286), writing A:\%1.TXT ... please wait.
MSD /P A:\%1.TXT
if exist A:\%1.TXT goto ok
echo.
echo MSD did not save. If it hung during detection, reboot and run:
echo    MSD /I /P A:\%1.TXT       (skips the initial hardware scan)
echo On odd video try adding /B (mono):  MSD /B /P A:\%1.TXT
goto done
:ok
echo.
echo MSD done.
:done
