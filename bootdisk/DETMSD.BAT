@echo off
REM Called by DETECT.BAT with the asset id as %1. 8088/286 (and any DOS PC).
REM MSD /P writes the full report to the named file with no prompts.
if not exist MSD.EXE goto missing
echo.
echo Running MSD (8088/286), writing %1.TXT ... please wait.
MSD /P %1.TXT
if exist %1.TXT goto ok
echo.
echo MSD did not save. If it hung during detection, reboot and run:
echo    MSD /I /P %1.TXT       (skips the initial hardware scan)
goto done
:missing
echo.
echo MSD.EXE is not on this disk. Copy it on -- it ships with MS-DOS 6.x
echo (look in C:\DOS\MSD.EXE on a 6.x machine).
goto done
:ok
echo.
echo MSD done.
:done
