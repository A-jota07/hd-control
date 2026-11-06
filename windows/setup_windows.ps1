# HD Control Studio - Script de Instalação e Configuração para Windows
# Execute este script no PowerShell como Administrador

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  HD Control Studio - Assistente de Configuração Windows   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verifica privilégios de Administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warning "AVISO: Este script e o aplicativo precisam ser executados como Administrador"
    Write-Warning "para permitir a leitura física de discos no Windows."
}

# 2. Verifica instalação do Python
Write-Host "`n[1/4] Verificando ambiente Python..." -ForegroundColor Yellow
$pythonExe = Get-Command python -ErrorAction SilentlyContinue
if ($pythonExe) {
    $pyVer = & python --version 2>&1
    Write-Host "OK: $pyVer encontrado." -ForegroundColor Green
} else {
    Write-Error "ERRO: Python não foi encontrado no PATH. Instale o Python 3.10+ e adicione ao PATH."
    Exit 1
}

# 3. Instala dependências do Python
Write-Host "`n[2/4] Instalando dependências Python..." -ForegroundColor Yellow
$reqPath = Join-Path $PSScriptRoot "requirements-windows.txt"
if (Test-Path $reqPath) {
    python -m pip install --upgrade pip
    python -m pip install -r $reqPath
} else {
    Write-Host "Arquivo de requisitos não encontrado em $reqPath"
}

# 4. Verifica e sugere instalação do smartmontools via winget
Write-Host "`n[3/4] Verificando utilitários de diagnóstico SMART..." -ForegroundColor Yellow
$smartctl = Get-Command smartctl -ErrorAction SilentlyContinue
if ($smartctl) {
    Write-Host "OK: smartctl já está instalado e disponível no PATH." -ForegroundColor Green
} else {
    Write-Host "smartctl não detectado. Tentando instalar via Winget..." -ForegroundColor Cyan
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id smartmontools.smartmontools -e --silent --accept-package-agreements --accept-source-agreements
        winget install --id GSmartControl.GSmartControl -e --silent --accept-package-agreements --accept-source-agreements
    } else {
        Write-Host "DICA: Para diagnóstico aprofundado, instale manualmente o smartmontools e gsmartcontrol." -ForegroundColor DarkYellow
    }
}

# 5. Conclusão
Write-Host "`n[4/4] Configuração finalizada com sucesso!" -ForegroundColor Green
Write-Host "Para iniciar o app, execute como Administrador o arquivo: windows\run_app.bat" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
