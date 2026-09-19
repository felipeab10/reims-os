# T008 — Diferenciar shutdown/reboot normal de crash/kernel panic

Status: `[ ]` não iniciada

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

## Histórico

Nenhuma implementação validada ainda.
