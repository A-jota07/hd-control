# HD Control Studio

Sistema desktop para Linux e Windows (Python + GTK3) desenvolvido para diagnóstico SMART, controle de inventário de HDs/SSDs, formatação e provisionamento (gravação de imagens ISO/IMG e transferência de pacotes de arquivos) com suporte dedicado a leitores de HD externo via porta USB.

## Funcionalidades Principais

- **Leitor USB & Diagnóstico Técnico (`smartctl` + `UDisks2` / PowerShell WMI)**
  - Monitoramento automático (Hotplug) de discos conectados via USB, SATA e NVMe.
  - Leitura de saúde S.M.A.R.T., contagem de *Bad Sectors*, horas de uso e temperatura sem necessidade de senha de root a cada teste.
  - Teste rápido de leitura de superfície (I/O direto em blocos de 128 MB).
  - Classificação rápida em 1 clique (**Funcionando**, **Com Defeito**, **Em Teste**) vinculada à máquina de destino.
  - Layout totalmente responsivo com suporte a redimensionamento livre de tela.
  - Integração direta com o **GSmartControl**.

- **Controle de HDs & Inventário Persistente Dinâmico (`SQLite` + `CSV` / `TXT`)**
  - **Inicialização 100% Limpa por Máquina**: Quando baixado ou executado pela primeira vez em qualquer PC (Linux ou Windows), o sistema inicia com as tabelas de HDs e Computadores totalmente limpas, sem dados pré-preenchidos.
  - **Geração Dinâmica com Escolha de Local**: Ao adicionar o primeiro HD ou o primeiro lote de Computadores, o sistema gera um arquivo limpo e exibe uma mensagem perguntando ao usuário onde deseja salvá-lo (`.csv` ou `.txt`), mantendo-o atualizado automaticamente a cada alteração e pronto para exportação.
  - Registro por Número de Série (evitando retestes duplicados).
  - Numeração 100% dinâmica: ao excluir qualquer HD ou lote de computadores, a numeração é reordenada de imediato sem deixar lacunas ou pular números.
  - Exportação de relatórios de HDs e Computadores em `.csv` (codificação UTF-8-BOM e delimitador `;` para compatibilidade total com Excel e Calc) ou `.txt`.
  - Busca e filtragem por status, modelo, serial ou máquina de destino.

- **Formatação, Instalação de SO e Cópia de Arquivos**
  - **Proteção de Disco do Sistema**: bloqueio automático contra formatação ou sobrescrita do disco principal do sistema operacional.
  - **Formatação**: criação de tabela de partições (`GPT` ou `MBR`) e formatação em `EXT4`, `NTFS`, `exFAT`, `FAT32` ou `BTRFS`.
  - **Gravação de SO (`Direct Flash`)**: gravação de imagens `.iso`, `.img` ou `.raw` diretamente no HD externo.
  - **Kit de Arquivos Padrão**: montagem automática da partição do HD externo e cópia de pastas, drivers ou instaladores.

- **Controle de Bancada / Computadores**
  - Gestão de lotes de computadores e periféricos (total, funcionando, sem funcionar, com/sem memória RAM, com/sem HD ou SSD) para acompanhamento da demanda de discos.

- **Suporte Multiplataforma (Linux & Windows)**
  - Suporte completo no Linux (Arch Linux, Ubuntu, Debian, Fedora, etc.).
  - Suporte nativo no Windows 10/11 através de scripts dedicados na pasta `windows/`.

## Requisitos no Linux (Arch Linux / Derivados)

```bash
sudo pacman -S python python-gobject gtk3 smartmontools gsmartcontrol udisks2 parted dosfstools exfatprogs e2fsprogs btrfs-progs
```

Para dispensar qualquer pedido de senha no terminal e executar testes sem elevação:
```bash
./scripts/setup_permissions_linux.sh
```

## Como Executar no Linux

```bash
git clone git@github.com:A-jota07/hd-control.git
cd hd-control
python3 main.py
```

## Como Executar no Windows

Consulte o guia completo em [`windows/README_WINDOWS.md`](windows/README_WINDOWS.md).
Execute o instalador automatizado no PowerShell como Administrador:
```powershell
cd windows
.\setup_windows.ps1
.\run_app.bat
```
