# T007 — Restart do macOS reinicia o host

Status: `[x]` concluída e validada

Dependência: **T005** concluída e validada.

## Objetivo

Quando o supervisor comprovar que o macOS já instalado solicitou um reboot normal, o host Linux deve reiniciar de forma limpa e automática, preservando a experiência de máquina dedicada. Reboots ocorridos durante `state=installing` são internos ao instalador e não acionam reboot do host.

## Escopo

- consumir a classificação `GUEST_REBOOT` do supervisor somente quando o estado persistente da VM for `installed`;
- reiniciar o host somente após reset/reboot normal confirmado;
- persistir logs/estado antes da reinicialização;
- permitir dry-run/desativação em ambiente de desenvolvimento;
- evitar loops de reboot em caso de kernel panic ou crash.

## Fora de escopo

- shutdown do host, tratado em T006;
- classificação de reset/panic, tratada em T005/T008;
- UI de recovery;
- criação final dos units systemd, tratada em T010.

## Requisitos de implementação

1. `systemctl reboot` ou mecanismo systemd equivalente só pode ser chamado para `GUEST_REBOOT` confirmado.
2. Um evento RESET isolado deve ser correlacionado com a ausência de kernel panic conforme regras do supervisor.
3. Antes do reboot, persistir:
   - lifecycle final;
   - exit code/estado QEMU;
   - evento que provocou a classificação;
   - caminho do serial/logs.
4. Deve existir dry-run que produza `WOULD_REBOOT` sem reiniciar o host.
5. `GUEST_KERNEL_PANIC`, `QEMU_FATAL`, `REIMS_FATAL`, `EXTERNAL_SIGNAL` e `UNKNOWN_EXIT` nunca podem reiniciar automaticamente o host.
6. Não usar apenas o fechamento da janela ou término do QEMU como sinal de reboot.
7. A ação deve ser idempotente e executada uma única vez por sessão.
8. Não executar QEMU/Reims como root apenas para permitir reboot do host.
9. `state=installing` + RESET/reboot do guest nunca pode executar `systemctl reboot`; o QEMU deve continuar/resetar o guest para que a instalação prossiga sem intervenção manual.

## Critérios de aceitação

### Simulado

Com dry-run:

- `GUEST_REBOOT` → exatamente um `WOULD_REBOOT`;
- `GUEST_SHUTDOWN` → nenhum reboot;
- `GUEST_KERNEL_PANIC` → nenhum reboot;
- `QEMU_FATAL` → nenhum reboot;
- `REIMS_FATAL` → nenhum reboot;
- `UNKNOWN_EXIT` → nenhum reboot.

### Integração

Em host seguro para teste:

1. iniciar a VM;
2. selecionar `Restart` no macOS;
3. supervisor classificar `GUEST_REBOOT`;
4. logs serem persistidos;
5. host Linux reiniciar;
6. após o boot do Linux, o appliance voltar ao fluxo normal de inicialização da VM.

## Segurança

- kernel panic que provoca reset não pode gerar reboot infinito do host;
- falha do QEMU/Reims não pode reiniciar automaticamente o host;
- nenhum broad `pkill`;
- logs devem sobreviver ao reboot.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- testes dry-run;
- evidência de que panic/reset anormal não reinicia o host;
- resultado de pelo menos um reboot real seguro;
- confirmação de que o próximo boot volta ao appliance corretamente quando as tasks de auto-start estiverem disponíveis.

## Implementação controlada em validação

T007 consome exclusivamente o result.json final persistido pelo supervisor/T008. A elegibilidade é classification=GUEST_REBOOT, appliance_state=installed e recovery_required=false; installing permanece sem host reboot. O consumidor compartilhado com T006 diferencia poweroff/reboot, grava WOULD_REBOOT em dry-run, usa host-action.claim com O_CREAT|O_EXCL, persiste audit antes de sync e só então chama systemctl reboot em systemd. Falhas conservadoras, idempotência e integração do supervisor são cobertas por tests/t007-host-reboot.py.

A análise de scripts/reims-launch.sh confirma QEMU_REBOOT_ACTION=reset durante installing e QEMU_REBOOT_ACTION=exit quando installed; o reset interno do instalador não deve virar reboot do host. O teste controlado usa o fake T005, que encerra após RESET e portanto prova somente o guard supervisor/host-action, não a continuidade do QEMU real. A continuidade real do instalador permanece derivada da configuração QEMU_REBOOT_ACTION=reset e não foi executada nesta rodada. Nenhum reboot físico foi executado.

## Runtime real corretivo — Sequoia 15.8

A validação corretiva após o fix do ShutdownCause (T008) foi executada em macOS Sequoia 15.8 real, com o launcher real `scripts/reims-launch.sh`, estado `installed` e `REIMS_HOST_ACTION_MODE=dry-run`.

```text
RUNTIME_ROOT=/tmp/reims-t007-corrective-8wpVYZ
SESSION_DIR=/tmp/reims-t007-corrective-8wpVYZ/logs/boot-20260920-131948-38838820
VM_ID=reims-57f0fd6b61a74542
APPLIANCE_STATE=installed
QEMU_REBOOT_ACTION=exit
MACOS_VERSION=sequoia 15.8
```

O QEMU real recebeu `-action reboot=shutdown`. O usuário executou `Apple menu → Restart` sem QMP `system_reset`, sem `system_powerdown`, sem sinais e sem kill. O pedido de restart do guest foi convertido pelo QEMU em um `QMP SHUTDOWN` com `data.guest=true` e `data.reason=guest-reset`, seguido da saída do processo.

Classificação real (T008):

```text
classification=GUEST_REBOOT
classification_reason=qmp_guest_reset_shutdown
primary_evidence={"source":"qmp","event":"SHUTDOWN","guest":true,"reason":"guest-reset"}
appliance_state=installed
recovery_required=false
serial.panic_detected=false
limitations=[]
launcher_exit_code=0
qemu_exit_code=0
```

Host action real (T007, dry-run):

```text
host_action.schema=1
host_action.classification=GUEST_REBOOT
host_action.appliance_state=installed
host_action.action=reboot
host_action.mode=dry-run
host_action.status=WOULD_REBOOT
claim_present=yes
```

Ordem no lifecycle e regressão principal:

```text
CLASSIFICATION_EVENT_INDEX=10
WOULD_REBOOT_EVENT_INDEX=11
CLASSIFICATION_BEFORE_ACTION=true
WOULD_REBOOT_COUNT=1
WOULD_POWEROFF_COUNT=0
HOST_POWEROFF_REQUESTED_COUNT=0
```

State e segurança:

```text
STATE_BEFORE=installed
STATE_AFTER=installed
recovery_required=false
SYSTEMCTL_GUARD_CALLED=no
HOST_REMAINS_ON=yes
REAL_HOST_REBOOT_EXECUTED=no
REAL_HOST_POWEROFF_EXECUTED=no
```

Idempotência (reconsumo do mesmo `result.json` em dry-run):

```text
SECOND_CONSUMER_STATUS=ALREADY_CLAIMED
WOULD_REBOOT_COUNT=1
HOST_ACTION_ALREADY_CLAIMED_PRESENT=yes
host-action.json preservado: action=reboot, status=WOULD_REBOOT
```

Fixture fonte:

```text
SOURCE_FIXTURE_CHANGED=no
macos.qcow2      711213b1b708db259198e07ac1e281e323852fe35482e833b1123b5f8c01f94a
OpenCore.qcow2   3d8f93eb8035c838add9c901fcbf6d6332874bda5b86f7006577c53e17460621
OVMF_CODE.fd     7decd7fa9965e7f943a1f79d1d05ce6d881540d625cc2a9641a57f89721b4577
OVMF_VARS.fd     6ed987af3a3c155be71665f510eae3e007eda9b8b94afd59d45e91c4a11565cc
```

Markers:

```text
T007_RUNTIME_LAYOUT_PREFLIGHT=PASS
T008_REAL_GUEST_RESET_SHUTDOWN_CAUSE=PASS
T008_REAL_REBOOT_CLASSIFICATION=PASS
T008_REAL_PRIMARY_EVIDENCE_CAUSE=PASS
T008_REAL_REBOOT_NO_RECOVERY=PASS
T007_REAL_DRY_RUN_WOULD_REBOOT=PASS
T007_REAL_CLASSIFICATION_BEFORE_ACTION=PASS
T007_REAL_RESTART_NEVER_POWEROFF=PASS
T007_REAL_NO_SYSTEMCTL_CALL=PASS
T007_REAL_HOST_REMAINS_ON=PASS
T007_REAL_IDEMPOTENT=PASS
T007_RUNTIME_SOURCE_FIXTURE_PRESERVED=PASS
```

## Escopo deferido

A T007 está concluída quanto ao seu contrato de lifecycle/host-action: consumir o `result.json` final, classificar `GUEST_REBOOT` como elegível, produzir `WOULD_REBOOT` em dry-run, tratar idempotência e nunca invocar poweroff.

O seguinte permanece deliberadamente deferido para **T010 / T011 / T024 clean-room**, e não é pendência funcional da classificação T007:

```text
systemctl reboot físico
permissões/polkit/systemd reais
units finais
boot Linux → autostart appliance após reboot físico
```

A T006 adotou a mesma separação para o poweroff físico.

## Histórico

Implementação controlada iniciada nesta rodada; matriz T007 controlada com 9 testes. Runtime real inicial revelou o bug de ShutdownCause no T008 (Apple Restart → QMP `SHUTDOWN reason=guest-reset` classificado como `GUEST_SHUTDOWN`). Após o fix corretivo do T008, o runtime real em Sequoia 15.8 produziu `GUEST_REBOOT` → `WOULD_REBOOT` com `WOULD_POWEROFF_COUNT=0`.
