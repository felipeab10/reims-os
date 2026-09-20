# T005 — Criar supervisor QMP/serial/QEMU

Status: `[x]` concluída e validada

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

- Implementação e validação concluídas no PR #3, branch `feat/t005-supervisor`.
- Commits de correção relevantes: `d2f537e699a6e059854fbf10a92012274415e705` (framing QMP) e `0726d464bbce969f2e38c4a439fa0f2d8e3401d7` (delimitadores de evidência).
- A primeira execução real revelou `JSON parse error, stray '\\'`; a causa foi o delimitador incorreto de `qmp_capabilities`. A mensagem passou de `sock.sendall(b'{"execute":"qmp_capabilities"}\\n')` para `sock.sendall(b'{"execute":"qmp_capabilities"}\n')`.
- A revisão final corrigiu também o JSONL físico de `lifecycle.log` (`"\\n"` para `"\n"`) e a tokenização de `/proc/<pid>/cmdline` (`b"\\0"` para `b"\0"`).

## Implementação validada

Implementado em `scripts/reims-supervisor.py`, usando Python stdlib. A cadeia é reims-launch/VM manager -> supervisor -> boot-x86 -> QEMU. Cada execução cria `boot-YYYYMMDD-HHMMSS-UUID` sob `REIMS_LOG_ROOT`, com `lifecycle.log` JSONL, `result.json`, `qemu.log` e `serial.log`; `latest` aponta para a sessão mais recente.

O supervisor observa launcher, PID QEMU, QMP, serial, exit codes e o estado do appliance. O `result.json` usa schema 1 e inclui `schema`, `session_id`, `vm_id`, `appliance_state`, `classification`, timestamps, PIDs/exit codes, `external_signal`, `qmp`, `serial`, `process`, `evidence` e `limitations`. O root de produção é `/var/log/reims/`, com pointer `/var/log/reims/latest`.

Classificações estáveis: `GUEST_SHUTDOWN`, `GUEST_REBOOT`, `GUEST_KERNEL_PANIC`, `QEMU_FATAL`, `REIMS_FATAL`, `EXTERNAL_SIGNAL` e `UNKNOWN_EXIT`. A precedência é: (1) guest kernel panic; (2) sinal externo; (3) fatal pré-QEMU Reims/launcher; (4) QEMU identificado com exit code não-zero; (5) `RESET` em `installed`; (6) `SHUTDOWN`; (7) `UNKNOWN_EXIT`. Em `installing`, `RESET` registra `INSTALLER_RESET`, mantém a supervisão e não executa ação de host. Erros QMP pós-handshake geram `QMP_ERROR` e a limitação `qmp_protocol_error`, sem inferir `QEMU_FATAL`.

QEMU só é identificado após qmp.path novo, greeting válido, `qmp_capabilities` válido e child direto inequívoco do launcher. Não há `pgrep qemu`, `pkill` ou `killall`; sinais usam somente o process group exato iniciado pelo supervisor.

## Evidência final de validação

- Runtime real: `/tmp/reims-t005-real-v2-7I2VmJ/logs/boot-20260919-234943-12105b19`, macOS Sequoia 15.8, VM `reims-57f0fd6b61a74542`, fixture source preservada.
- QEMU real identificado em `components/reims-vgpu/vendor/qemu/build/qemu-system-x86_64`; QMP `available=true`.
- Eventos: `RTC_CHANGE`, `NIC_RX_FILTER_CHANGED`, `RTC_CHANGE`, `SHUTDOWN`; evento terminal `SHUTDOWN` com `guest=true` e `reason=guest-shutdown`.
- Resultado real: `classification=GUEST_SHUTDOWN`, serial preservado, panic=false, `limitations=[]`, launcher exit code 0, QEMU exit code 0, nenhuma ação de energia no host.
- Testes: `T005_CONTROLLED_TEST_PASS`, T002, T003 e T004 PASS; dependency check PASS; pins preservados.
- A matriz controlou shutdown, reboot, panic/reset, QEMU fatal, fatal pré-QEMU, QMP indisponível/handshake inválido/erro de protocolo, sinal externo, installer RESET, descoberta atrasada, idle/terminal QMP, late panic, identidade/ambiguidade de PID, ambiguidade serial, resultado atômico/latest pointer, JSONL real, cmdline tokenizado e ausência de broad process control.
- A mensagem `fatal: No names found, cannot describe anything.` é ruído benigno de `scripts/qemu-version.sh` (`git describe ... || :`), não falha QEMU; futuras classificações devem usar evidência contextual, não uma regra genérica por texto.
- Não foi necessário repetir o runtime macOS para as correções de evidência, pois não alteraram classificação, QMP, seleção de PID, serial ou política de lifecycle.
