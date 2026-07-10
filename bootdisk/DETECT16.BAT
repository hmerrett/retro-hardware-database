@echo off
echo.
set /p ID=Enter asset id, eg RH-0005:
echo.
echo Running HWiNFO16 (8086/286), writing %ID%.TXT ... please wait.
HWINFO16 -r %ID%.TXT
if exist %ID%.TXT goto ok
echo.
echo Not auto-saved. In HWiNFO16, save the report by hand to %ID%.TXT
goto done
:ok
echo.
echo Saved %ID%.TXT
:done
pause
