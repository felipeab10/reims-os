# T006 — Shutdown do macOS desliga o host

Status: `[x]` concluída e validada

Dependência: **T005** concluída e validada.

## Objetivo

Quando o supervisor comprovar que o macOS realizou um shutdown normal, o host Linux deve desligar de forma limpa e automática.

## Escopo

- consumir a classificação do supervisor;
- executar poweroff apenas para `GUEST_SHUTDOWN` confirmado;
- garantir que logs e estado final da sessão sejam sincronizados antes do desligamento;
- integrar com systemd de forma previsível e auditável;
- permitir desabilitar a ação em modo de desenvolvimento/teste.

## Fora de escopo

- reboot do host, tratado em T007;
- classificação de crash/panic, tratada em T005/T008;
- UI de recovery;
- criação final dos units systemd do appliance, tratada em T010.

## Requisitos de implementação

1. `systemctl poweroff` ou mecanismo systemd equivalente só pode ser chamado após classificação explícita `GUEST_SHUTDOWN`.
2. Exit code `0` do QEMU isoladamente não é prova suficiente.
3. Antes do poweroff, persistir:
   - lifecycle final;
   - exit code;
   - último estado relevante QMP;
   - caminho do serial/logs.
4. Executar `sync`/garantir flush necessário sem desmontagens manuais perigosas.
5. Deve existir modo de desenvolvimento, variável/configuração ou dry-run que registre `WOULD_POWEROFF` sem desligar a máquina.
6. Crash do QEMU, panic do guest, sinal inesperado ou `UNKNOWN_EXIT` não podem desligar o host.
7. A ação deve ser idempotente: múltiplos eventos não podem disparar loops ou múltiplas chamadas concorrentes.
8. Não exigir privilégios root para o QEMU/Reims; elevação deve ser limitada ao mecanismo de lifecycle/systemd.

## Critérios de aceitação

### Simulado

Com o host em dry-run:

- `GUEST_SHUTDOWN` → exatamente uma ação `WOULD_POWEROFF`;
- `GUEST_REBOOT` → nenhuma ação poweroff;
- `GUEST_KERNEL_PANIC` → nenhuma ação poweroff;
- `QEMU_FATAL` → nenhuma ação poweroff;
- `UNKNOWN_EXIT` → nenhuma ação poweroff.

### Integração

Em host de teste onde poweroff é seguro:

1. iniciar appliance/VM;
2. selecionar `Shut Down` no macOS;
3. supervisor classificar `GUEST_SHUTDOWN`;
4. logs serem gravados;
5. host Linux desligar de forma limpa.

O teste real de poweroff só deve ser feito quando houver ambiente seguro e recuperação conhecida.

## Segurança

- nunca desligar host por timeout arbitrário;
- nunca desligar host por ausência de processo QEMU sem classificação;
- nunca desligar host após kernel panic;
- nunca usar broad `pkill`;
- preservar logs antes do poweroff.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- interface usada entre supervisor e ação de poweroff;
- testes dry-run para todas as classificações relevantes;
- logs demonstrando que apenas `GUEST_SHUTDOWN` dispara a ação;
- resultado de pelo menos um teste real seguro ou justificativa explícita se ainda não executável.

## Implementação controlada em validação

T006 consome exclusivamente o result.json final persistido pelo supervisor/T008; não relê QMP, serial, qemu.log ou exit codes para reclassificar a sessão. A combinação elegível é exatamente classification=GUEST_SHUTDOWN, appliance_state=installed e recovery_required=false.

REIMS_HOST_ACTION_MODE possui os modos disabled (default seguro), dry-run e systemd. O consumidor gera host-action.json atomicamente, registra eventos no lifecycle.log, usa claim atômico por sessão para idempotência e executa sync antes de qualquer chamada systemctl poweroff. O caminho systemd não usa sudo/su/pkexec e foi validado somente com executor mockado; nenhum poweroff real foi executado. Modo desconhecido falha conservadoramente. Reboot pertence à T007 e não é implementado aqui.

O supervisor chama o consumidor somente depois de persistir atomicamente result.json e atualizar latest, sempre usando o result_path exato da sessão. Falha do consumidor é registrada como HOST_ACTION_CONSUMER_FAILED, não altera a classificação e preserva o retorno original do launcher/QEMU. disabled registra HOST_ACTION_DISABLED sem criar claim; chamadas duplicadas preservam o host-action.json original. Falhas de sync ou systemctl geram HOST_POWEROFF_FAILED, não chamam poweroff em caso de sync falho e mantêm o claim para impedir retry automático.

A matriz controlada cobre shutdown elegível, classificações não elegíveis, estado installing, rc=0, recovery guard, resultado inválido, final-result-only, integração real do supervisor em dry-run, auditoria, dry-run/systemd, idempotência e falhas conservadoras. A implementação e a validação previstas para T006 foram concluídas; a revisão e o merge da PR permanecem etapas de governança separadas.

## Governança e evidência final

### Arquitetura final

Fluxo validado: supervisor/T008 → classificação final → result.json atomicamente persistido → latest atualizado → reims-host-action.py recebe o result_path exato → valida elegibilidade → disabled / dry-run / systemd.

Elegibilidade exclusiva: classification == GUEST_SHUTDOWN AND appliance_state == installed AND recovery_required == false. T006 usa somente o result.json final persistido e não relê QMP, serial, qemu.log, launcher_exit_code ou qemu_exit_code para reinterpretar o lifecycle. Evidência: T006_FINAL_RESULT_ONLY=PASS.

REIMS_HOST_ACTION_MODE=disabled é o default seguro; dry-run registra WOULD_POWEROFF; systemd é o caminho produtivo para systemctl poweroff; modo desconhecido produz NO_ACTION. Não são usados sudo, su ou pkexec.

### Idempotência, auditoria e falhas

host-action.json é persistido atomicamente. host-action.claim usa O_CREAT | O_EXCL para dry-run/systemd; disabled não cria claim. Segunda chamada retorna ALREADY_CLAIMED sem sobrescrever o audit original. A ordem validada é classification → result.json → latest → consumer → host-action intent → sync → systemctl poweroff. Falha de sync impede systemctl; falha de systemctl mantém claim e audit; falha do consumer registra HOST_ACTION_CONSUMER_FAILED sem alterar classification, result.json ou return code original.

### Matriz controlada final

13 tests
OK
T006_CONTROLLED_TEST_PASS

Markers cobertos: T006_WOULD_POWEROFF, T006_DEFAULT_DISABLED, T006_REBOOT_NO_POWEROFF, T006_PANIC_NO_POWEROFF, T006_QEMU_FATAL_NO_POWEROFF, T006_REIMS_FATAL_NO_POWEROFF, T006_EXTERNAL_SIGNAL_NO_POWEROFF, T006_UNKNOWN_NO_POWEROFF, T006_INSTALLING_NO_POWEROFF, T006_RC0_NOT_POWEROFF, T006_RECOVERY_GUARD, T006_DRY_RUN_IDEMPOTENT, T006_SYSTEMD_IDEMPOTENT, T006_SYSTEMD_COMMAND, T006_SYNC_BEFORE_POWEROFF, T006_RESULT_BEFORE_ACTION, T006_FINAL_RESULT_ONLY, T006_HOST_ACTION_AUDIT, T006_UNKNOWN_MODE_SAFE, T006_SUPERVISOR_INTEGRATION, T006_CLASSIFICATION_BEFORE_ACTION, T006_SUPERVISOR_UNKNOWN_NO_POWEROFF, T006_IDEMPOTENT_AUDIT_PRESERVED, T006_FAILED_AUDIT_PRESERVED, T006_DISABLED_NO_CLAIM, T006_SYNC_FAILURE_NO_POWEROFF, T006_SYSTEMD_FAILURE_AUDIT, T006_CONSUMER_FAILURE_PRESERVES_RESULT, T006_CONSUMER_FAILURE_PRESERVES_RC, T006_CONSUMER_FAILURE_FAKE_SYSTEMCTL e T006_REGRESSION_HOST_ACTION_DISABLED.

### Runtime Sequoia 15.8

RUNTIME_ROOT=/tmp/reims-t006-real-u8Xog3
SESSION_DIR=/tmp/reims-t006-real-u8Xog3/logs/boot-20260920-082650-533b0b9a
VM_ID=reims-57f0fd6b61a74542
SOURCE_FIXTURE=/home/felipeab10/Documentos/reims-t002-fixtures/runtime-sequoia-retry-2/vms/reims-57f0fd6b61a74542
REIMS_HOST_ACTION_MODE=dry-run

O shutdown foi iniciado manualmente pelo usuário via Apple menu → Shut Down, sem QMP system_powerdown e sem signals ao QEMU. T008 registrou classification=GUEST_SHUTDOWN, classification_reason=qmp_shutdown, primary_evidence={source:qmp,event:SHUTDOWN}, appliance_state=installed, launcher_exit_code=0, qemu_exit_code=0, recovery_required=false, recovery.attempted=false, serial.panic_detected=false, limitations=[]; QMP informou guest=true e reason=guest-shutdown, sem erros.

T006 registrou schema=1, classification=GUEST_SHUTDOWN, appliance_state=installed, action=poweroff, mode=dry-run, status=WOULD_POWEROFF e claim presente. Evidências: T006_REAL_DRY_RUN_WOULD_POWEROFF=PASS, T006_REAL_CLASSIFICATION_BEFORE_ACTION=PASS, T006_REAL_NO_SYSTEMCTL_CALL=PASS, T006_REAL_HOST_REMAINS_ON=PASS, T006_REAL_IDEMPOTENT=PASS e T006_RUNTIME_SOURCE_FIXTURE_PRESERVED=PASS. O guard systemctl não foi chamado; o host permaneceu operacional; state permaneceu installed; a fixture fonte não sofreu alterações.

### Poweroff físico deferido

O caminho produtivo systemctl poweroff foi validado com executor fake, incluindo comando exato, sync antes da chamada, idempotência, falhas de sync/systemctl, preservação de audit e falha do consumer sem reclassificação. O runtime real validou GUEST_SHUTDOWN → WOULD_POWEROFF sem chamar systemctl.

Um poweroff físico do host de desenvolvimento foi deliberadamente deferido. A integração definitiva de permissões e units systemd pertence à T010; o teste físico deve ocorrer em host/appliance de teste com recuperação conhecida, preferencialmente em T024 ou etapa posterior clean-room. Isso é deferred integration validation, não bug conhecido da T006.

### Regressões e status

T006: 13 tests PASS; T008: 19 tests PASS; T005: 16 tests PASS; T002/T003/T004: PASS; dependency check: PASS; pins unchanged. PR #5 permanece aberta e não mergeada. T007 permanece não implementada.

## Histórico

Implementação controlada e validação runtime concluídas nesta rodada de governança.
