# T023 — Criar overlay e build reproduzível da ISO Reims OS

Status: `[ ]` não iniciada

## Objetivo

Produzir uma ISO instalável e reproduzível contendo Ubuntu Server/minimized, Subiquity customizado, branding e componentes do Reims OS.

## Requisitos

- build automatizado e documentado;
- pins/versionamento da base e componentes registrados;
- overlay do filesystem versionado;
- configuração/autoinstall/Subiquity versionados;
- pacote mínimo vindo de T021;
- branding/rede obrigatória vindos de T022;
- incluir artefatos necessários para first boot, systemd, Xorg single-app e recovery;
- não depender de alterações manuais após gerar a ISO.

## Critérios de aceitação

- duas builds com mesmas entradas produzem conteúdo funcional equivalente e auditável;
- ISO boota em UEFI;
- checksum publicado;
- manifesto informa versões/pins;
- instalação clean-room pode ser iniciada sem checkout de desenvolvimento.
