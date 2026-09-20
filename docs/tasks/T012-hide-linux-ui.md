# T012 — Tornar o Linux invisível no fluxo normal

Status: `[ ]` não iniciada

## Objetivo

Garantir que o usuário perceba o Reims OS como appliance dedicado ao macOS, sem desktop/console Linux no uso normal.

## Requisitos

- ocultar login TTY/console técnico no caminho normal;
- não instalar desktop tradicional, WM ou painel;
- boot normal deve mostrar somente branding/telas Reims e macOS;
- falha deve abrir Recovery do Reims, não shell automaticamente;
- manter acesso técnico deliberado para desenvolvimento/recovery administrativo.

## Critérios de aceitação

- boot normal não mostra Ubuntu, shell, desktop ou painel;
- saída do QEMU não deixa o usuário em desktop Linux;
- mensagens técnicas ficam em logs;
- modo de manutenção continua disponível por ação explícita.
