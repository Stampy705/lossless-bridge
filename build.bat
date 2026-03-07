@echo off
echo ========================================
echo  Lossless Bridge - EXE Builder
echo ========================================
echo.

:: Use the same Python you always use
set PYTHON=C:\Users\shant\AppData\Local\Python\pythoncore-3.14-64\python.exe

:: Install PyInstaller if not already installed
echo [1/3] Installing PyInstaller...
%PYTHON% -m pip install pyinstaller --quiet

echo.
echo [2/3] Building EXE...
echo.

%PYTHON% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "LosslessBridge" ^
    --hidden-import=customtkinter ^
    --hidden-import=spotipy ^
    --hidden-import=spotipy.oauth2 ^
    --hidden-import=requests ^
    --hidden-import=pyautogui ^
    --hidden-import=pycaw ^
    --hidden-import=pycaw.pycaw ^
    --hidden-import=psutil ^
    --hidden-import=pywinauto ^
    --hidden-import=pywinauto.application ^
    --hidden-import=pywinauto.Desktop ^
    --hidden-import=win32crypt ^
    --hidden-import=win32con ^
    --hidden-import=win32api ^
    --hidden-import=Crypto ^
    --hidden-import=Crypto.Cipher ^
    --hidden-import=Crypto.Cipher.AES ^
    --hidden-import=PIL ^
    --hidden-import=PIL._tkinter_finder ^
    --hidden-import=darkdetect ^
    --hidden-import=packaging ^
    --collect-all customtkinter ^
    --collect-all spotipy ^
    --collect-all pywinauto ^
    lossless_bridge.py

echo.
echo [3/3] Done!
echo.

if exist "dist\LosslessBridge.exe" (
    echo  SUCCESS: dist\LosslessBridge.exe is ready.
    echo.
    echo  Copy LosslessBridge.exe to any folder and run it.
    echo  profiles.json and config.json will be created next to the exe.
) else (
    echo  BUILD FAILED - check the output above for errors.
)

echo.
pause
