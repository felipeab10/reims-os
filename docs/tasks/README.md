# Tasks — Reims OS 0.1.0

Este diretório acompanha a implementação do appliance.

## Convenção de status

- `[ ]` não iniciada
- `[-]` em andamento
- `[x]` concluída e validada
- `[!]` bloqueada

Uma task só deve mudar para `[x]` após existir evidência de implementação e validação.

## Regra de trabalho

1. Uma IA/implementador escolhe uma task.
2. A implementação deve citar o ID da task no commit/PR quando possível.
3. Após a implementação, revisar o diff e executar os critérios de aceitação da task.
4. Somente depois atualizar este arquivo e o arquivo da task para `[x]`.
5. Mudanças arquiteturais devem atualizar `docs/arquitetura.md` e/ou `docs/requisitos.md`.
6. O implementador não deve marcar a própria task como concluída; a conclusão é feita na etapa de validação.

## Backlog 0.1.0

### Fundação

- [x] [T001 — Implementar modo persistente no launcher](T001-persistent-mode.md) — concluída e validada em Sequoia 15.8; shutdown/reboot persistence PASS
- [x] [T002 — Simplificar o VM Manager para fluxo de appliance](T002-vm-manager-appliance.md) — concluída e validada em Sequoia 15.8; reboots, QMP, autoboot e Recovery PASS
- [x] [T003 — Implementar fullscreen nativo obrigatório](T003-fullscreen.md) — concluída e validada em Wayland/niri; fullscreen persistente automático e override windowed PASS
- [x] [T004 — Criar modelo de estado persistente do appliance](T004-state-model.md) — concluída e validada; schema 1, escrita atômica, launcher state-driven e paths fora da checkout PASS

### Lifecycle

- [x] [T005 — Criar supervisor QMP/serial/QEMU](T005-supervisor.md) — concluída e validada; supervisor QMP/serial/PID, classificação, evidência JSONL e runtime Sequoia 15.8 PASS
- [x] [T006 — Shutdown do macOS desliga o host](T006-host-poweroff.md) — concluída e validada; matriz controlada e runtime Sequoia 15.8 em dry-run PASS
- [x] [T007 — Restart do macOS reinicia o host](T007-host-reboot.md) — validada em Sequoia 15.8: Apple Restart → QMP SHUTDOWN reason=guest-reset → GUEST_REBOOT → WOULD_REBOOT; nenhum poweroff
- [x] [T008 — Diferenciar shutdown/reboot normal de crash/kernel panic](T008-lifecycle-classification.md) — corrective ShutdownCause validada em runtime real; matriz reason-aware PASS

### Inicialização automática

- [-] [T009 — Criar sessão gráfica dedicada single-app](T009-single-app-session.md) — sessão Xorg single-app e fullscreen X11 sem window manager implementados, com fallback explícito de geometria para o root X11; o primeiro runtime real falhou na geometria e aguarda novo runtime
- [ ] T010 — Criar serviços systemd do appliance
- [ ] [T011 — Implementar first-boot automático e Reims Setup](T011-firstboot-setup.md)
- [ ] [T012 — Tornar o Linux invisível no fluxo normal](T012-hide-linux-ui.md) — console/desktop Linux não fazem parte da experiência normal
- [ ] [T034 — UI de progresso da instalação](T034-install-progress-ui.md)

### Atualização

- [ ] T013 — Definir layout transacional de releases
- [ ] T014 — Implementar updater transacional do reims-os
- [ ] T015 — Implementar build/test/preflight antes de ativar release
- [ ] T016 — Implementar rollback automático para last-known-good
- [ ] T017 — Criar manifesto de versões por boot

### UX de boot

- [ ] T018 — Implementar tela Plymouth do Reims OS
- [ ] T019 — Mostrar estado de atualização sem expor console técnico
- [ ] T020 — Criar fluxo de recovery em falhas

### Distribuição

- [ ] [T021 — Definir Ubuntu Server minimized e pacote mínimo](T021-ubuntu-server-minimized.md)
- [ ] [T022 — Customizar instalador TUI/Subiquity, rede obrigatória e branding Reims OS](T022-subiquity-network-branding.md)
- [ ] [T023 — Criar overlay e build reproduzível da ISO Reims OS](T023-reims-iso-build.md)
- [ ] [T024 — Validar instalação clean-room da ISO Reims OS](T024-clean-room-install.md) — Ethernet/Wi-Fi → Internet validada → instalação → first boot → macOS

### Matriz macOS

- [ ] T025 — Validar Ventura end-to-end
- [ ] T026 — Validar Sonoma end-to-end
- [ ] T027 — Validar Sequoia end-to-end

### Release

- [ ] T028 — Testar update bem-sucedido
- [ ] T029 — Testar update quebrado + rollback
- [ ] T030 — Teste prolongado/soak
- [ ] T031 — Congelar versões da plataforma 0.1.0
- [ ] [T033 — Polimento de boot nativo OpenCore](T033-opencore-native-boot-polish.md)
- [ ] T032 — Preparar release 0.1.0

## Ordem recomendada

A sequência obrigatória de alto nível é:

```text
T001 → T002 → T003 → T004
          ↓
       T005-T008
          ↓
       T009-T012/T034
          ↓
       T013-T017
          ↓
       T018-T020
          ↓
       T021-T024
          ↓
       T025-T031
          ↓
          T033
          ↓
          T032
```

Não iniciar a construção final da ISO antes de o modo persistente, o VM Manager simplificado, fullscreen e lifecycle estarem funcionais em um host de desenvolvimento conhecido. A ISO 0.1.0 usa Ubuntu Server/Subiquity em modo TUI customizado, exige conectividade real antes de prosseguir e instala uma base minimized sem desktop Linux tradicional.

## Protocolo de handoff para implementação

Antes de implementar qualquer task, o implementador deve ler:

```text
docs/arquitetura.md
docs/requisitos.md
docs/tasks/README.md
docs/tasks/TXXX-....md
```

Ao terminar, deve entregar sem marcar `[x]`:

- ID da task;
- commit/PR;
- arquivos alterados;
- decisões de implementação;
- comandos de teste;
- resultados;
- pendências ou desvios de arquitetura.

A validação da task revisa o diff e os critérios de aceitação antes de atualizar o status.
