@echo off
rem ----------------------------------------------------------------------
rem  CRIAR-INSTALADOR  -  de dois cliques neste arquivo.
rem  Ele instala o que faltar (Python e Inno Setup), monta o programa e gera
rem  o instalador:  installer_output\VibeGrap-Setup.exe
rem  Precisa de internet. Leva de 5 a 15 minutos.
rem ----------------------------------------------------------------------
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Criando o instalador do VibeGrap

if not exist "ytdlp_gui.py" goto nofile

rem ---------- 1. Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY="%LocalAppData%\Programs\Python\Python312\python.exe""
if defined PY goto havepy

echo [Python] Nao encontrado. Instalando automaticamente (pelo winget)...
where winget >nul 2>nul
if errorlevel 1 goto nopython
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY="%LocalAppData%\Programs\Python\Python312\python.exe""
if not defined PY goto nopython

:havepy
echo [1/5] Python OK.
echo.
echo [2/5] Instalando bibliotecas...
%PY% -m pip install --upgrade pip
if errorlevel 1 goto fail
%PY% -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 goto fail

echo.
echo [3/5] Compilando o programa (pode levar alguns minutos)...
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --name "VibeGrap" --icon assets\VibeGrap_icon.ico ^
  --add-data "assets;assets" ^
  --collect-all customtkinter ^
  --collect-submodules yt_dlp ^
  --collect-all yt_dlp_ejs ^
  --collect-all certifi ^
  --hidden-import mutagen --hidden-import Cryptodome --hidden-import brotli --hidden-import websockets ^
  --hidden-import PIL._imagingtk --hidden-import PIL._tkinter_finder --hidden-import PIL.ImageTk ^
  ytdlp_gui.py
if errorlevel 1 goto fail

echo.
echo [4/5] Baixando ffmpeg e Deno para dentro do programa...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $d='dist\VibeGrap'; " ^
  "Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile ffmpeg.zip; " ^
  "Expand-Archive ffmpeg.zip -DestinationPath ffmpeg_tmp -Force; " ^
  "Get-ChildItem ffmpeg_tmp -Recurse -Include ffmpeg.exe,ffprobe.exe | Copy-Item -Destination $d; " ^
  "New-Item -ItemType Directory -Force ($d + '\licenses') | Out-Null; " ^
  "$l = Get-ChildItem ffmpeg_tmp -Recurse -Filter LICENSE.txt | Select-Object -First 1; Copy-Item $l.FullName ($d + '\licenses\ffmpeg-LICENSE-GPLv3.txt'); " ^
  "try { Invoke-WebRequest 'https://raw.githubusercontent.com/denoland/deno/main/LICENSE.md' -OutFile ($d + '\licenses\deno-LICENSE.md') } catch {}; " ^
  "Invoke-WebRequest 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' -OutFile deno.zip; " ^
  "Expand-Archive deno.zip -DestinationPath deno_tmp -Force; Copy-Item deno_tmp\deno.exe $d; " ^
  "Remove-Item ffmpeg.zip,deno.zip,ffmpeg_tmp,deno_tmp -Recurse -Force"
if errorlevel 1 goto fail

echo.
echo [5/5] Gerando o instalador...
call :findiscc
if defined ISCC goto haveiscc
echo [Inno Setup] Nao encontrado. Instalando automaticamente (pelo winget)...
where winget >nul 2>nul
if errorlevel 1 goto noinno
winget install -e --id JRSoftware.InnoSetup --scope user --accept-package-agreements --accept-source-agreements
call :findiscc
if not defined ISCC goto noinno

:haveiscc
"%ISCC%" installer.iss
if errorlevel 1 goto fail
echo.
echo ======================================================================
echo  PRONTO!  O instalador esta em:
echo  %~dp0installer_output\VibeGrap-Setup.exe
echo ======================================================================
explorer "%~dp0installer_output"
pause
exit /b 0

:findiscc
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
exit /b 0

:noinno
echo.
echo Nao consegui instalar o Inno Setup sozinho.
echo Baixe e instale em https://jrsoftware.org/isdl.php e de dois cliques neste arquivo de novo.
echo (O programa ja funciona sem instalador em: %~dp0dist\VibeGrap\VibeGrap.exe)
pause
exit /b 1

:nopython
echo.
echo Nao consegui instalar o Python sozinho.
echo Baixe em https://www.python.org/downloads/ (marque "Add python.exe to PATH") e de dois cliques neste arquivo de novo.
pause
exit /b 1

:nofile
echo Nao encontrei ytdlp_gui.py nesta pasta. Descompacte o .zip inteiro e rode este arquivo de dentro da pasta.
pause
exit /b 1

:fail
echo.
echo Algo deu errado. Copie a mensagem de erro acima e me envie.
pause
exit /b 1
