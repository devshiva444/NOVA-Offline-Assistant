@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0

if not exist ".env" (
    echo [ERROR] .env not found.
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "K=%%A"
    set "V=%%B"
    if not "!K!"=="" if not "!K:~0,1!"=="#" set "!K!=!V!"
)

if not defined MODELS_DIR set MODELS_DIR=models
if not defined LLM_MODEL_NAME set LLM_MODEL_NAME=sarvam-1-2b-instruct-q8_0.gguf
if not defined LLM_CONTEXT set LLM_CONTEXT=2048
if not defined LLM_THREADS set LLM_THREADS=4
if not defined LLM_PORT set LLM_PORT=8080
if not defined LLAMA_BIN_DIR set LLAMA_BIN_DIR=llama\bin

set "MODEL_PATH=%MODELS_DIR%\%LLM_MODEL_NAME%"
set "SERVER_EXE=%LLAMA_BIN_DIR%\llama-server-cpu.exe"

if not exist "%SERVER_EXE%" set "SERVER_EXE=%LLAMA_BIN_DIR%\llama-server.exe"
if not exist "%SERVER_EXE%" (
    echo [ERROR] llama server executable not found in %LLAMA_BIN_DIR%
    pause
    exit /b 1
)

if not exist "%MODEL_PATH%" (
    echo [ERROR] Model not found: %MODEL_PATH%
    pause
    exit /b 1
)

echo [INFO] Starting LLM server...
start "NOVA LLM" "%SERVER_EXE%" -m "%MODEL_PATH%" -c %LLM_CONTEXT% -t %LLM_THREADS% --port %LLM_PORT% --chat-template chatml

timeout /t 5 /nobreak >nul

echo [INFO] Starting UI...
nova_env\Scripts\python.exe main.py

pause