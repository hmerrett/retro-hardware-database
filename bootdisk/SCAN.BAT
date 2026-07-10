@echo off
REM Non-interactive scan: pick the next free SCANnn.TXT and run MSD into it.
REM MS-DOS batch has no date/time/random vars, so reports are auto-numbered
REM (MSD writes the real date/time inside each report). Up to 15 per disk;
REM read them off and delete them to reuse the disk.
set F=
for %%N in (15 14 13 12 11 10 09 08 07 06 05 04 03 02 01) do if not exist SCAN%%N.TXT set F=SCAN%%N
if "%F%"=="" goto full
echo.
echo Scanning this machine -- writing %F%.TXT
echo Please wait ~15 seconds; do not remove the disk.
MSD /P %F%.TXT
if not exist %F%.TXT goto fail
echo.
echo =================================================
echo   DONE.  Saved %F%.TXT
echo   Power off and move the floppy to the next PC.
echo =================================================
goto end
:fail
echo.
echo MSD did not save (it may have hung). Reboot to retry. If it keeps
echo hanging on this PC, edit SCAN.BAT to:  MSD /I /P %F%.TXT
goto end
:full
echo.
echo This disk already holds SCAN01-SCAN15 (or is full). Read the reports
echo off it, delete them, and reuse the disk.
:end
