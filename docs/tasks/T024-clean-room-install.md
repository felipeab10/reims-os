# T024 — Validar instalação clean-room da ISO Reims OS

Status: `[ ]` não iniciada

## Objetivo

Validar o produto do zero em hardware/VM de teste sem depender do ambiente de desenvolvimento.

## Matriz mínima

- Ethernet;
- Wi-Fi suportado;
- ausência de Internet;
- disco vazio;
- primeiro boot;
- sessão Xorg single-app;
- Reims Setup;
- instalação do macOS;
- shutdown/reboot do lifecycle quando seguro.

## Fluxo esperado

```text
ISO Reims OS
→ TUI
→ rede obrigatória
→ instalação
→ reboot
→ Plymouth/Reims
→ Xorg single-app
→ Reims Setup
→ macOS
```

## Critérios de aceitação

- sem rede externa o instalador não prossegue;
- Ethernet e Wi-Fi podem concluir a instalação;
- branding Reims OS consistente;
- nenhum desktop Linux tradicional aparece;
- primeiro boot inicia Setup automaticamente;
- máquina configurada inicia macOS automaticamente;
- testes físicos de reboot/poweroff do host só em ambiente seguro e recuperável;
- logs e manifesto permitem reproduzir a build testada.
