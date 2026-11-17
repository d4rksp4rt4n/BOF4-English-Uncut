@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
cd /d "%~dp0"
cl /nologo /O2 /EHsc loopcap.cpp /Fe:loopcap.exe || exit /b 1
del loopcap.obj 2>nul
