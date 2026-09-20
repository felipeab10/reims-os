# T011 — Implementar first-boot automático e Reims Setup

Status: `[ ]` não iniciada

## Objetivo

Após a instalação da ISO Reims OS, iniciar automaticamente o Setup quando `/var/lib/reims/state.json` ainda não representar uma VM configurada.

## Fluxo

```text
primeiro boot
→ sessão Reims
→ estado unconfigured
→ Reims Setup
→ macOS + CPU + RAM + disco
→ provisionamento
→ instalação macOS
```

## Requisitos

- não expor desktop Linux;
- solicitar somente Ventura/Sonoma/Sequoia, CPU, RAM e disco >= 70 GiB;
- gerar VM ID, SMBIOS/serial/OpenCore/OVMF automaticamente;
- consumir o contrato de progresso estruturado do provisionador;
- rede já deve estar disponível pela instalação do host; falha de rede deve gerar UI acionável;
- permitir recovery sem exigir terminal.

## Critérios de aceitação

- primeiro boot unconfigured entra no Setup automaticamente;
- sistema configured não reabre o Setup;
- nenhum parâmetro interno de QEMU/OpenCore é solicitado ao usuário;
- erro preserva estado e logs.
