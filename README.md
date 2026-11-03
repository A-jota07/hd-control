# HD Control Studio

Sistema desktop nativo para Linux (Python + GTK3) desenvolvido para diagnóstico SMART, controle de inventário de HDs/SSDs, formatação e provisionamento (gravação de imagens ISO/IMG e transferência de pacotes de arquivos) com suporte dedicado a leitores de HD externo via porta USB.

## Funcionalidades Principais

- **Leitor USB & Diagnóstico Técnico (`smartctl` + `UDisks2`)**
  - Monitoramento automático (Hotplug) de discos conectados via USB, SATA e NVMe.
  - Leitura de saúde S.M.A.R.T., contagem de *Bad Sectors*, horas de uso e temperatura (incluindo suporte a adaptadores USB-SATA via `-d sat`).
  - Teste rápido de leitura de superfície (I/O direto).
  - Classificação rápida em 1 clique (**Funcionando**, **Com Defeito**, **Em Teste**) vinculada à máquina de destino.
  - Integração direta com o **GSmartControl**.

- **Controle de HDs & Inventário Persistente (`SQLite` + `CSV`)**
  - Registro por Número de Série (evitando retestes duplicados).
  - Busca e filtragem por status, modelo, serial ou máquina.
  - Exportação de relatórios completos em `.csv`.

- **Formatação, Instalação de SO e Cópia de Arquivos**
  - **Proteção de Disco do Sistema**: bloqueio automático contra formatação ou sobrescrita do disco principal do sistema operacional.
  - **Formatação**: criação de tabela de partições (`GPT` ou `MBR`) e formatação em `EXT4`, `exFAT`, `FAT32` ou `BTRFS`.
  - **Gravação de SO (`Direct Flash`)**: gravação de imagens `.iso`, `.img` ou `.raw` diretamente no HD externo.
  - **Kit de Arquivos Padrão**: montagem automática da partição do HD externo e cópia de pastas, drivers ou instaladores.

- **Controle de Bancada / Computadores**
  - Gestão de lotes de computadores e periféricos (total, funcionando, sem funcionar, com/sem memória RAM, com/sem HD ou SSD) para acompanhamento da demanda de discos.

- **Interface Intuitiva P&B (Tema Escuro e Claro)**
  - Design monocromático de alto contraste em preto e branco com alternância em tempo real entre **Tema Escuro** e **Tema Claro**.

## Requisitos no Linux (Arch Linux / Derivados)

```bash
sudo pacman -S python python-gobject gtk3 smartmontools gsmartcontrol udisks2 parted dosfstools exfatprogs e2fsprogs btrfs-progs
```

## Como Executar

```bash
git clone git@github.com:A-jota07/hd-control.git
cd hd-control
python3 main.py
```
