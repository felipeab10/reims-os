# T006 — Shutdown do macOS desliga o host

Status: `[-]` em implementação/validação

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

A matriz controlada cobre shutdown elegível, classificações não elegíveis, estado installing, rc=0, recovery guard, resultado inválido, final-result-only, auditoria, dry-run/systemd e idempotência. T006 permanece em implementação/validação até revisão da PR.

## Histórico

Implementação controlada iniciada nesta rodada.
