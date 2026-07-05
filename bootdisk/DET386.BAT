@echo off
echo.
set /p ID=Enter asset id, eg RH-0005:
echo.
echo Running HWiNFO (386+), writing A:\%ID%.TXT ... please wait.
HWINFO -rA:\%ID%.TXT
if exist A:\%ID%.TXT goto ok
echo.
echo Not auto-saved. In HWiNFO, save the report by hand to A:\%ID%.TXT
goto done
:ok
echo.
echo Saved A:\%ID%.TXT
:done
pause
