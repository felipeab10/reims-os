# T007 — Restart do macOS reinicia o host

Status: `[ ]` não iniciada

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

## Histórico

Nenhuma implementação validada ainda.
