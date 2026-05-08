@echo off
echo Starting browserctl bridge...
echo.
echo Make sure the Chrome extension is installed:
echo   1. Open chrome://extensions
echo   2. Enable Developer mode
echo   3. Click "Load unpacked" and select the extension folder
echo.
python -m browserctl.bridge %*
pause
