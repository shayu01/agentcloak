@echo off
echo Starting browserctl bridge...
echo.
echo Make sure the Chrome extension is installed:
echo   1. Open chrome://extensions
echo   2. Enable Developer mode
echo   3. Click "Load unpacked" and select the extension folder
echo.
REM Use --host 0.0.0.0 to listen on all interfaces for remote connections.
REM Configure token in ~/.browserctl/bridge.toml for auth.
python -m browserctl.bridge --host 0.0.0.0 %*
pause
