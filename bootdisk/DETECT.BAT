@echo off
REM Usage: DETECT RH-nnnn [3|6]
REM   (no 2nd arg)  auto: HWiNFO if HWINFO.EXE is on the disk, else MSD
REM   3             force HWiNFO (386+)
REM   6             force MSD (286/8088)
REM One set of batch files works on both disks: the 1.44M HWiNFO disk picks
REM HWiNFO, the 720K MSD disk (no HWINFO.EXE) picks MSD automatically.
if "%1"=="" goto usage
if "%2"=="6" goto low
if "%2"=="3" goto hi
if not exist A:\HWINFO.EXE goto low
:hi
call DET386.BAT %1
goto done
:low
call DETMSD.BAT %1
goto done
:usage
echo.
echo Usage:  DETECT RH-nnnn        auto (HWiNFO if present, else MSD)
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
