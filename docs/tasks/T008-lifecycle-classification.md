# T008 — Diferenciar shutdown/reboot normal de crash/kernel panic

Status: `[-]` em implementação/validação

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

## Implementação em validação

Status desta rodada: o supervisor mantém uma única fonte de decisão em `classify_session(facts)`, preservando `classify(facts)` como compatibilidade da T005. A decisão somente ocorre após o término do launcher/QEMU, drenagem do QMP e releitura integral do serial; o `qemu.log` final é analisado com offset registrado na identificação do QEMU.

A precedência efetiva é: (1) marcador de panic no serial; (2) fatal explícito contextual de Vulkan/Reims ou QEMU, incluindo `VK_ERROR_DEVICE_LOST`, segmentation fault e abort/assertion; (3) sinal externo conhecido; (4) último evento terminal QMP, com `SHUTDOWN` ou `RESET` em `installed`; (5) exit code não-zero identificado ou fatal pré-QEMU; (6) término sem evidência suficiente. Exit code zero isolado permanece `UNKNOWN_EXIT`. Exit code não-zero não supera sinal externo nem terminal guest comprovado. O último terminal é usado, portanto RESET → SHUTDOWN resulta em shutdown e SHUTDOWN → RESET em reboot. Panic preservado sempre vence eventos posteriores. O offset do `qemu.log` é capturado uma única vez no primeiro qmp.path fresco e representa bytes; a análise decodifica somente depois do corte.

Cada resultado mantém schema 1 e acrescenta `classification_reason`, `primary_evidence`, `sources_consulted`, `recovery_required`, `recovery` e diagnósticos curtos de panic. A recuperação é tentada somente após a classificação final, via `scripts/reims-state.py transition recovery` e `REIMS_STATE_ROOT`; falha de transição preserva o resultado e adiciona `recovery_transition_failed`. Panic, QEMU fatal, Reims/Vulkan fatal e UNKNOWN exigem recovery; shutdown, reboot e sinal externo não exigem.

A fonte de log de kernel do host para NVIDIA Xid/NVRM e OOM killer não está disponível no desenho atual sem sudo: `HOST_KERNEL_LOG_SOURCE=UNAVAILABLE`. Não há coletor privilegiado nem inferência desses eventos sem evidência. A mensagem `fatal: No names found, cannot describe anything.` é explicitamente ignorada como ruído benigno de `git describe ... || :` quando isolada.

A matriz controlada está em `tests/t008-lifecycle-classification.py` e cobre shutdown, reboot, panic/RESET/SHUTDOWN, fatal precedence, sinais, ordem terminal QMP, rc=0 conservador, texto fatal benigno, QMP error não fatal, evidência primária, fontes consultadas, offset de log, política/transição de recovery e indisponibilidade de host log. T005 permanece em regressão; T006 e T007 não são iniciadas nesta rodada. Nenhuma ação `systemctl poweroff`/`systemctl reboot` e nenhuma VM macOS real foram executadas.
