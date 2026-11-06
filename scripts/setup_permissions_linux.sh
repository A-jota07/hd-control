#!/usr/bin/env bash
# Script para dispensar senha permanentemente no HD Control Studio no Linux.
# Adiciona o usuário atual ao grupo 'disk' para permitir leitura direta de HDs USB/SATA
# e cria regra sudoers para smartctl e dd sem senha.

set -e

echo "=== Configurando permissões sem senha para o HD Control Studio ==="

CURRENT_USER="${SUDO_USER:-$USER}"

echo "1. Adicionando o usuário '$CURRENT_USER' ao grupo 'disk'..."
sudo usermod -aG disk "$CURRENT_USER"

echo "2. Configurando regra sudoers para smartctl e dd sem senha..."
RULE_FILE="/etc/sudoers.d/99-hd-control"
echo "$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/smartctl, /usr/bin/dd" | sudo tee "$RULE_FILE" > /dev/null
sudo chmod 0440 "$RULE_FILE"

echo "3. Permissões configuradas com sucesso!"
echo "   Para que a alteração de grupo tenha efeito completo na sua sessão,"
echo "   faça logoff e login novamente ou execute no seu terminal: newgrp disk"
echo "=================================================================="
