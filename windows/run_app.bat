@echo off
title HD Control Studio — Windows
cd /d "%~dp0\.."

:: Verifica se o terminal tem privilégios de Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ============================================================
    echo   AVISO: EXECUTANDO SEM PRIVILEGIOS DE ADMINISTRADOR
    echo ============================================================
    echo   Para detectar discos fisicos e permitir formatacao USB,
    echo   recomenda-se clicar com o botao direito neste arquivo
    echo   e selecionar "Executar como Administrador".
    echo ============================================================
    echo.
    pause
)

python main.py
if %errorlevel% neq 0 (
    echo.
    echo Ocorreu um erro ao executar o HD Control Studio.
    pause
)
