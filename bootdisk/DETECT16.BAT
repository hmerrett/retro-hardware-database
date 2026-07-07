@echo off
echo.
set /p ID=Enter asset id, eg RH-0005:
echo.
echo Running HWiNFO16 (8086/286), writing A:\%ID%.TXT ... please wait.
HWINFO16 -r A:\%ID%.TXT
if exist A:\%ID%.TXT goto ok
echo.
echo Not auto-saved. In HWiNFO16, save the report by hand to A:\%ID%.TXT
goto done
:ok
echo.
echo Saved A:\%ID%.TXT
:done
pause
