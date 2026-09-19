# T005 — Criar supervisor QMP/serial/QEMU

Status: `[ ]` não iniciada

Dependências: **T001–T004**.

## Objetivo

Criar o processo responsável por supervisionar uma sessão macOS do appliance, observando simultaneamente o processo QEMU, QMP e serial para produzir um resultado de lifecycle confiável.

## Resultado esperado

O supervisor deve saber distinguir, no mínimo, que uma sessão terminou por:

- shutdown normal;
- reset/reboot solicitado pelo guest;
- kernel panic;
- crash/erro do QEMU;
- crash/erro do Reims;
- encerramento por sinal externo;
- causa desconhecida.

Nesta task o supervisor **classifica e registra**. As ações de desligar/reiniciar o host ficam em T006/T007.

## Escopo

- iniciar ou acompanhar o QEMU da VM principal;
- conhecer o PID exato da instância supervisionada;
- consumir QMP/eventos quando disponível;
- acompanhar o serial desta execução;
- registrar timestamps e eventos em log persistente;
- preservar exit code do QEMU;
- produzir um resultado final estruturado da sessão;
- consumir a fase atual do appliance (`installing`, `installed`, `recovery`) para que a ação posterior possa distinguir reboot interno do instalador de reboot normal de uso diário;
- nunca depender de `pgrep`/`pkill` amplo para controlar a VM.

## Fora de escopo

- executar `systemctl poweroff`;
- executar `systemctl reboot`;
- UI de recovery;
- updater;
- watchdog de hardware;
- tentar reparar automaticamente kernel panic ou Vulkan device lost.

## Requisitos de implementação

1. O supervisor deve receber/descobrir de forma inequívoca:
   - PID QEMU;
   - socket QMP;
   - arquivo serial;
   - diretório de log da execução.
2. Eventos QMP devem ser timestampados.
3. O serial deve ser preservado mesmo se QEMU encerrar inesperadamente.
4. O exit code do QEMU deve ser registrado.
5. O supervisor deve reconhecer o padrão já usado pelo projeto para kernel panic (`Debugger called: <panic>`), sem concluir que todo reset é panic.
6. O supervisor não pode inferir shutdown normal apenas porque `rc=0`.
7. Deve haver precedência explícita entre sinais conflitantes. Exemplo: panic detectado antes de RESET não pode ser reclassificado como reboot normal.
8. Se QMP ficar indisponível, registrar a limitação e usar somente evidência disponível, sem inventar causa.
9. O resultado final deve ser escrito em formato legível por scripts, por exemplo JSON ou key/value estável.
10. Logs devem ficar fora da checkout, sob `/var/log/reims/` no appliance; testes podem usar diretório temporário.
11. Nunca usar broad `pkill`.
12. Encerramento do supervisor não deve apagar evidência da sessão.
13. Durante `state=installing`, um RESET/reboot normal do guest deve ser registrado como evento de instalação e não deve implicar encerramento da sessão nem reboot do host.
14. A classificação que habilita T007 só pode ser emitida no contexto `state=installed`, após excluir kernel panic/crash conforme as regras de precedência.

## Classificações mínimas

A implementação deve possuir nomes estáveis equivalentes a:

```text
GUEST_SHUTDOWN
GUEST_REBOOT
GUEST_KERNEL_PANIC
QEMU_FATAL
REIMS_FATAL
EXTERNAL_SIGNAL
UNKNOWN_EXIT
```

Pode haver estados intermediários adicionais.

## Critérios de aceitação

### Testes controlados sem depender de macOS

Sempre que possível, criar fixtures ou um pequeno harness capaz de alimentar eventos/logs simulados e validar:

1. `SHUTDOWN` limpo → `GUEST_SHUTDOWN`;
2. `RESET` sem panic → `GUEST_REBOOT` ou estado de reset equivalente;
3. serial contendo panic + RESET → `GUEST_KERNEL_PANIC`;
4. QEMU sai com erro sem shutdown/reset → `QEMU_FATAL`/`UNKNOWN_EXIT`, conforme evidência;
5. processo recebe sinal externo conhecido → `EXTERNAL_SIGNAL`;
6. QMP indisponível → não classificar falsamente como shutdown/reboot.

### Integração real

Em uma execução de teste:

- QMP é acompanhado;
- serial é preservado;
- PID/exit code são registrados;
- resultado final é produzido após QEMU terminar.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- arquivos criados;
- formato do resultado final;
- tabela de precedência de classificação;
- testes simulados executados;
- pelo menos uma execução real supervisionada;
- exemplo anonimizado/seguro de lifecycle log.

## Histórico

Nenhuma implementação validada ainda.
