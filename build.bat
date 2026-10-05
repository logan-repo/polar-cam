@echo off
rem Polar Deer 빌드: PolarDeer.exe (PyInstaller) + 설치 프로그램 (Inno Setup)
rem 필요: Python 3 (tkinter 포함), Inno Setup 6.5 이상
cd /d "%~dp0"

python -m pip install --quiet pyinstaller || goto :err
python -m PyInstaller --noconfirm --onefile --noconsole --name PolarDeer --icon assets\polardeer.ico --add-data "assets;assets" polardeer.py || goto :err

set ISCC=
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist %%P set ISCC=%%~P
if "%ISCC%"=="" (
  echo Inno Setup 6 이 설치되어 있지 않아 설치 프로그램은 건너뜁니다. ^(https://jrsoftware.org/isdl.php^)
  goto :done
)
"%ISCC%" installer\polardeer.iss || goto :err

:done
echo.
echo 완료:
echo   dist\PolarDeer.exe            (단독 실행 파일 - ffmpeg.exe 별도 필요)
echo   dist\PolarDeer-Setup-*.exe    (설치 프로그램 - ffmpeg 자동 설치)
pause
exit /b 0

:err
echo 빌드 실패
pause
exit /b 1
