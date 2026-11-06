# HD Control Studio — Guia de Instalação e Uso no Windows

Este guia orienta como executar o **HD Control Studio** nativamente no **Windows 10 / Windows 11**.

---

## 1. Requisitos do Sistema
- **Windows 10 ou 11** (64-bit)
- **Python 3.10+** instalado
- **Terminal com privilégios de Administrador** (necessário para ler discos físicos `\\.\PhysicalDrive` e executar formatações)
- Opcional: **smartmontools** (para leitura completa dos atributos SMART de fábrica)

---

## 2. Instalação Rápida (Recomendada via PowerShell)

Abra o **PowerShell como Administrador** e execute o script automatizado:

```powershell
cd hd-control\windows
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_windows.ps1
```

Esse script irá:
1. Verificar a versão do Python instalada.
2. Instalar os pacotes necessários (`requirements-windows.txt`).
3. Instalar o `smartmontools` via Windows Package Manager (`winget`) se disponível.
4. Criar o atalho de inicialização `run_app.bat`.

---

## 3. Instalação Manual Passo a Passo

### Passo 1: Instalar o Python
Baixe em [python.org](https://www.python.org/) e marque a opção **"Add Python to PATH"**.

### Passo 2: Instalar o PyGObject (GTK 3) para Windows
O HD Control utiliza a interface gráfica GTK 3. No Windows, você pode instalar o GTK 3 via MSYS2 ou através do instalador do PyGObject para Windows:

#### Opção A (Via Winget e MSYS2 - Mais Estável):
```powershell
winget install MSYS2.MSYS2
# No terminal do MSYS2 MINGW64:
pacman -S mingw-w64-x86_64-python mingw-w64-x86_64-python-gobject mingw-w64-x86_64-gtk3
```

#### Opção B (Via pip com wheels pré-compiladas):
```powershell
pip install -r windows/requirements-windows.txt
```

### Passo 3: Instalar Utilitários SMART (Opcional, mas recomendado)
Para obter leitura avançada de horas de uso e setores defeituosos detalhados no Windows:
```powershell
winget install smartmontools
winget install gsmartcontrol
```

---

## 4. Como Executar o Aplicativo

Para que o Windows permita acessar dispositivos de armazenamento brutos e leitores de disco USB, **inicie como Administrador**:

1. Clique com o botão direito em `windows\run_app.bat` e escolha **"Executar como Administrador"**.
2. Ou via terminal:
```powershell
python main.py
```

---

## 5. Recursos Suportados no Windows
- [x] **Leitor USB e Discos Conectados**: Detecção via `Get-Disk` e `Get-Partition` (PowerShell nativo).
- [x] **Diagnóstico SMART**: Leitura nativa via subsistema de armazenamento do Windows e integração automática com `smartctl.exe`.
- [x] **Teste de Leitura I/O Direta**: Teste de blocos com streaming sem travamento da interface.
- [x] **Formatação e Particionamento**: Suporte a GPT/MBR e sistemas de arquivos NTFS, FAT32 e exFAT via `diskpart` com proteção contra formatação do disco de boot (`C:`).
- [x] **Exportação Dinâmica CSV**: Arquivo com codificação UTF-8-BOM (`utf-8-sig`) e delimitador `;`, abrindo perfeitamente no Excel e LibreOffice sem corromper caracteres acentuados.
