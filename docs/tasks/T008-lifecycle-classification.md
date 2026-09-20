# T008 — Diferenciar shutdown/reboot normal de crash/kernel panic

Status: `[-]` corrective validation

Dependências: **T005** implementada; complementa **T006** e **T007**.

## Objetivo

Endurecer as regras de lifecycle para impedir que eventos anormais sejam tratados como ações normais do usuário. Esta task fecha o contrato de classificação usado pelo supervisor antes de permitir poweroff/reboot automático do host.

## Problema

No fluxo atual de desenvolvimento, um kernel panic pode provocar reset do guest e o launcher pode fazer QEMU sair. Sem correlação entre serial, QMP, exit code e sinais externos, um panic pode parecer um reboot normal.

No appliance isso é inaceitável porque poderia causar loops de reboot do host ou esconder falhas reais.

## Escopo

- definir precedência formal entre evidências de serial, QMP, processo e host;
- detectar kernel panic antes de classificar reset/reboot como normal;
- diferenciar término esperado do QEMU de crash/erro;
- registrar razão e evidência usada na classificação;
- garantir que classificações anormais entrem em recovery e nunca disparem T006/T007.

## Fora de escopo

- implementar UI de recovery;
- corrigir bugs do Reims ou do guest;
- reiniciar automaticamente VM após crash;
- coletar telemetry remota.

## Regras mínimas de precedência

A implementação deve seguir uma ordem equivalente a:

1. **kernel panic comprovado no serial** tem precedência sobre RESET/reboot;
2. **erro fatal explícito do Reims/Vulkan/QEMU** tem precedência sobre inferência por exit code;
3. **sinal externo conhecido** deve ser classificado como tal, salvo evidência mais forte anterior;
4. **SHUTDOWN explícito e limpo** pode classificar `GUEST_SHUTDOWN`;
5. **RESET/reboot sem panic/fatal associado** pode classificar `GUEST_REBOOT`;
6. somente `rc=0` não prova shutdown;
7. término sem evidência suficiente deve permanecer `UNKNOWN_EXIT`.

Se o código real exigir uma precedência diferente, ela deve ser documentada e justificada com evidência.

## Padrões mínimos a reconhecer

### Guest kernel panic

```text
Debugger called: <panic>
```

Quando disponível, registrar também linhas contendo:

- `panic(`;
- `AppleParavirtGPU`;
- `AppleParavirtPageTable`;
- `IOAcceleratorFamily2`;
- uptime/build do macOS.

Essas linhas são evidência diagnóstica, não requisitos para declarar panic quando o marcador principal já existe.

### Host/QEMU/Reims

Classificar separadamente quando houver evidência explícita de:

- segmentation fault;
- abort/assert fatal;
- Vulkan device lost;
- NVIDIA Xid/NVRM relacionado temporalmente;
- OOM killer;
- sinal externo enviado ao PID QEMU.

Não inferir esses eventos quando não aparecem nos logs.

## Requisitos de implementação

1. Produzir uma tabela ou função única de classificação, evitando regras duplicadas espalhadas por scripts.
2. Cada resultado deve conter:
   - classificação;
   - timestamp;
   - evidência principal;
   - fontes consultadas;
   - eventuais limitações (`qmp_unavailable`, `serial_missing`, etc.).
3. A classificação deve ser determinística para o mesmo conjunto de eventos.
4. A ordem em que threads/leitores entregam eventos não pode transformar panic comprovado em reboot normal; usar timestamps/correlação ou finalização antes da decisão.
5. T006/T007 devem consumir apenas o resultado final e não reinterpretar logs por conta própria.
6. Eventos desconhecidos devem falhar de forma conservadora: recovery/unknown, nunca poweroff/reboot automático.
7. Preservar logs originais sem truncar a evidência usada.

## Matriz mínima de testes

| Evidência | Resultado esperado |
|---|---|
| QMP SHUTDOWN, sem panic/fatal | `GUEST_SHUTDOWN` |
| QMP RESET, sem panic/fatal | `GUEST_REBOOT` |
| panic no serial + RESET | `GUEST_KERNEL_PANIC` |
| panic no serial + QEMU rc=0 | `GUEST_KERNEL_PANIC` |
| QEMU rc!=0 sem guest event | `QEMU_FATAL` ou `UNKNOWN_EXIT` conforme stderr |
| Vulkan device lost | `REIMS_FATAL`/fatal gráfico equivalente |
| SIGTERM externo conhecido | `EXTERNAL_SIGNAL` |
| processo some sem evidência | `UNKNOWN_EXIT` |
| QMP indisponível + rc=0 | não classificar automaticamente como shutdown |

## Critérios de aceitação

- todos os casos da matriz têm teste automatizado ou fixture reproduzível;
- nenhum caso de panic dispara `WOULD_REBOOT` ou `WOULD_POWEROFF` em dry-run;
- nenhum `UNKNOWN_EXIT` dispara ação de energia;
- classificação e evidência final são persistidas;
- uma execução real com encerramento normal é classificada corretamente;
- uma execução simulada/fixture de panic é classificada como panic mesmo contendo RESET posterior.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- tabela final de precedência;
- arquivos de fixture/teste;
- saída dos testes da matriz;
- exemplo de resultado estruturado para shutdown, reboot e panic;
- confirmação de integração segura com T006/T007.

## Implementação e validação final

Status desta rodada: o supervisor mantém uma única fonte de decisão em `classify_session(facts)`, preservando `classify(facts)` como compatibilidade da T005. A decisão somente ocorre após o término do launcher/QEMU, drenagem do QMP e releitura integral do serial; o `qemu.log` final é analisado com offset registrado na identificação do QEMU.

A precedência final validada é: (1) kernel panic comprovado no serial; (2) fatal explícito contextual Reims/Vulkan/QEMU; (3) external signal conhecido; (4) último evento terminal guest QMP; (5) QEMU identificado com exit code não-zero; (6) launcher pré-QEMU com exit code não-zero; (7) `UNKNOWN_EXIT`. Em forma resumida: `PANIC > EXPLICIT_FATAL > EXTERNAL_SIGNAL > GUEST_TERMINAL > PROCESS_NONZERO > UNKNOWN`. Panic nunca vira reboot por RESET posterior; fatal explícito vence shutdown/reset/signal; sinal externo vence exit code não-zero; terminal QMP comprovado vence exit code não-zero; e `rc=0` isoladamente nunca prova shutdown. O último terminal é usado: RESET → SHUTDOWN resulta em `GUEST_SHUTDOWN`; SHUTDOWN → RESET em `installed` resulta em `GUEST_REBOOT`; RESET em `installing` não representa reboot normal do host. O offset do `qemu.log` é capturado uma única vez no primeiro `qmp.path` fresco, em bytes, e a análise faz slice em bytes antes do decode.

Cada resultado mantém schema 1 e acrescenta `classification_reason`, `primary_evidence`, `sources_consulted`, `recovery_required`, `recovery` e diagnósticos curtos de panic. A recuperação é tentada somente após a classificação final, via `scripts/reims-state.py transition recovery` e `REIMS_STATE_ROOT`; falha de transição preserva o resultado e adiciona `recovery_transition_failed`. Panic, QEMU fatal, Reims/Vulkan fatal e UNKNOWN exigem recovery; shutdown, reboot e sinal externo não exigem.

A fonte de log de kernel do host para NVIDIA Xid/NVRM e OOM killer não está disponível no desenho atual sem sudo: `HOST_KERNEL_LOG_SOURCE=UNAVAILABLE`. Não há coletor privilegiado nem inferência desses eventos sem evidência. A mensagem `fatal: No names found, cannot describe anything.` é explicitamente ignorada como ruído benigno de `git describe ... || :` quando isolada.

A matriz controlada está em `tests/t008-lifecycle-classification.py`: 19 testes com `T008_CONTROLLED_TEST_PASS`, cobrindo shutdown, reboot, panic/RESET/SHUTDOWN, fatal precedence, sinais, terminal QMP + exit não-zero, rc=0 conservador, texto fatal benigno, QMP error não fatal, evidência primária, fontes consultadas, boundary em bytes, recovery normal, mismatch, falha preservando result.json e isolamento de state. T005 permanece em regressão com 16 testes; T002/T003/T004 e dependency check também passaram. T006 e T007 continuam não implementadas; nenhuma ação de host foi executada.

## Follow-up corrective: QMP ShutdownCause

O runtime real da T007 revelou que Apple menu → Restart, com `-action reboot=shutdown`, pode produzir `QMP SHUTDOWN` com `data.guest=true` e `data.reason=guest-reset`. O comportamento anterior descartava `data.reason` e classificava qualquer `SHUTDOWN` como `GUEST_SHUTDOWN`, levando incorretamente a `WOULD_POWEROFF`. A correção preserva a mensagem QMP estruturada e classifica `SHUTDOWN reason=guest-reset` como `GUEST_REBOOT` quando `appliance_state=installed`, mantendo `SHUTDOWN reason=guest-shutdown` como `GUEST_SHUTDOWN`. Causas `guest-panic`, `host-error`, `host-signal`, causas host-side ambíguas e reason ausente/desconhecido são conservadoras e não elegíveis a host action. Em `installing`, `guest-reset` não é reboot normal do host.

## Evidência final de runtime

A validação real foi executada em macOS Sequoia 15.8 com a VM reims-57f0fd6b61a74542. Artefatos preservados: runtime root /tmp/reims-t008-real-nRxmee; session /tmp/reims-t008-real-nRxmee/logs/boot-20260920-061036-4a0fb31c; source fixture /home/felipeab10/Documentos/reims-t002-fixtures/runtime-sequoia-retry-2/vms/reims-57f0fd6b61a74542. A fixture original foi usada somente como backing source e permaneceu inalterada.

Fatos estruturados: classification=GUEST_SHUTDOWN; classification_reason=qmp_shutdown; primary_evidence={"source":"qmp","event":"SHUTDOWN"}; sources_consulted=[serial, qmp, process, qemu_log, supervisor_signal]; host_kernel_log não consultado; recovery_required=false; recovery.required=false, attempted=false, succeeded=null, error=null; state before/after=installed/installed; limitations=[]; launcher exit=0; QEMU exit=0; serial panic=false.

QMP: RTC_CHANGE, NIC_RX_FILTER_CHANGED, RTC_CHANGE, SHUTDOWN. O raw terminal comprovou guest=true e reason=guest-shutdown; QMP errors=none.

QEMU: PID 68828; executable /home/felipeab10/Documentos/reims-os/components/reims-vgpu/vendor/qemu/build/qemu-system-x86_64; cmdline corretamente tokenizada; identity=PASS. Boundary: qemu_runtime_log_offset=2270, qemu_runtime_boundary offset=2270, qemu_identified offset=2270, qemu.log=3292 bytes, OFFSET_VALID=true. Após o boundary não apareceram VK_ERROR_DEVICE_LOST, SIGSEGV, SEGMENTATION FAULT, ASSERTION FAILED, QEMU: ASSERT ou ABORTED.

O runtime real registrou fatal: No names found, cannot describe anything. no qemu.log. Mesmo assim classification=GUEST_SHUTDOWN e classification_reason=qmp_shutdown, comprovando que o ruído pré-runtime não gera falso QEMU_FATAL. serial.log não vazio; panic_detected=false; Debugger called: <panic> ausente. Before/after stat comparison teve zero differences para macos.qcow2, OpenCore.qcow2, OVMF_CODE.fd e OVMF_VARS.fd.

### Markers finais e regressões

Matriz final: 19 tests, OK, T008_CONTROLLED_TEST_PASS. Markers críticos: T008_PANIC_PRECEDENCE=PASS; T008_EXPLICIT_FATAL_PRECEDENCE=PASS; T008_EXTERNAL_SIGNAL_QEMU_NONZERO=PASS; T008_EXTERNAL_SIGNAL_PRE_QEMU=PASS; T008_SHUTDOWN_BEATS_EXIT_NONZERO=PASS; T008_REBOOT_BEATS_EXIT_NONZERO=PASS; T008_RUNTIME_LOG_BYTE_OFFSET=PASS; T008_RUNTIME_LOG_BOUNDARY=PASS; T008_RUN_UNKNOWN_TO_RECOVERY=PASS; T008_RUN_NORMAL_NO_RECOVERY=PASS; T008_RECOVERY_VM_ID_GUARD=PASS; T008_RECOVERY_FAILURE_PRESERVES_RESULT=PASS; T008_RECOVERY_VM_MISMATCH_NO_MUTATION=PASS; T008_TEST_STATE_ISOLATION=PASS.

T005: 16 tests PASS, T005_CONTROLLED_TEST_PASS. T002, T003, T004 e dependency check: PASS. Pins unchanged. No systemctl poweroff/reboot was executed. T006/T007 remain unimplemented.
