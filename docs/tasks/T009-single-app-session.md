# T009 — Criar sessão gráfica dedicada single-app

Status: `[-]` em implementação/validação

## Objetivo

Criar a sessão gráfica mínima do Reims OS sem desktop tradicional, window manager ou painel.

## Arquitetura alvo

```text
systemd
  ↓
Xorg :0
  ↓
reims-session
  ↓
reims-vgpu / QEMU
  ↓
macOS fullscreen
```

## Requisitos

- usar Xorg somente como infraestrutura gráfica para a janela host do Reims;
- não depender de GNOME, KDE, XFCE, Openbox ou lxpanel;
- iniciar a sessão automaticamente no boot normal;
- `REIMS_VGPU_WINDOW=1` e fullscreen devem funcionar sem interação com UI Linux;
- falha da sessão deve cair no fluxo de recovery, não em um desktop;
- Setup/Recovery podem usar aplicações gráficas próprias na mesma sessão dedicada.

## Critérios de aceitação

- boot sem desktop tradicional;
- nenhum WM/painel necessário;
- Reims abre fullscreen em Xorg;
- teclado/mouse continuam funcionais;
- encerramento/crash da aplicação não expõe shell/desktop por padrão;
- logs da sessão ficam disponíveis para diagnóstico.

## Fora de escopo

- DRM/KMS direto;
- desktop Linux de uso geral;
- implementação dos units systemd finais, tratada em T010.

## Implementação e validação controlada

Implementado nesta rodada (T009 permanece `[-]`; os units systemd são T010):

- `scripts/reims-session.sh` — único cliente gráfico da sessão. Estabelece o contrato X11, aplica default de produto sem sobrescrever intenção explícita do operador e delega para `scripts/reims-launch.sh` (nunca para `boot-x86.sh` ou QEMU direto), preservando T004–T008.
- companion PR em `felipeab10/reims-vgpu` (`feat/t009-x11-window-system`) adicionando `vm/window-system-env.sh` e o seletor `REIMS_VGPU_WINDOW_SYSTEM=auto|x11|wayland` aplicado por `vm/boot-x86.sh`; neste repositório o gitlink `components/reims-vgpu` aponta para o commit dessa PR.

Contrato da sessão X11:

```text
XDG_SESSION_TYPE=x11
DISPLAY=${REIMS_X11_DISPLAY:-:0}          override explícito preservado
WAYLAND_DISPLAY unset
WAYLAND_SOCKET unset
XAUTHORITY preservado; REIMS_XAUTHORITY é override explícito
REIMS_VGPU_WINDOW_SYSTEM=x11
REIMS_VGPU_WINDOW=1        default se ausente
REIMS_VGPU_FULLSCREEN=1    default se ausente
REIMS_VGPU_BACKEND=vulkan  default se ausente
```

`winit 0.30` não tem `WINIT_UNIX_BACKEND` e prefere Wayland quando `WAYLAND_DISPLAY`/`WAYLAND_SOCKET` e `DISPLAY` coexistam. Por isso o seletor do companion remove as variáveis Wayland em `x11` e recusa quando `DISPLAY` está vazio, e o `boot-x86.sh` não recria `WAYLAND_DISPLAY` nesse modo. Um `DISPLAY` definido, por si só, não prova X11.

Se `reims-launch.sh` retornar, `reims-session.sh` retorna com o mesmo status (via `exec`); nenhum shell, terminal ou desktop é aberto, e não há fallback silencioso para Wayland ou para um desktop.

Testes controlados: `tests/t009-single-app-session.py` (13 testes, `T009_CONTROLLED_TEST_PASS`), com `REIMS_HOST_ACTION_MODE=disabled` e fake `systemctl` primeiro no `PATH` (nunca chamado). Markers: `T009_X11_ENV`; `T009_DISPLAY_OVERRIDE`; `T009_XAUTHORITY_PRESERVED`; `T009_FULLSCREEN_CONTRACT`; `T009_HOST_WINDOW_CONTRACT`; `T009_VULKAN_CONTRACT`; `T009_WAYLAND_ENV_CLEARED` e `T009_X11_NO_WAYLAND_ENV`; `T009_LAUNCHER_CHAIN`; `T009_EXIT_STATUS_PRESERVED`; `T009_VGPU_X11_SELECTOR`; `T009_VGPU_X11_REQUIRES_DISPLAY`; `T009_VGPU_AUTO_COMPAT`; `T009_NO_WM_DEPENDENCY`; `T009_NO_SYSTEMCTL`.

### Validação real pendente

A validação em runtime real fica para a rodada seguinte, depois da revisão remota. Ela deve procurar evidência de que o `winit` abriu X11 de fato, e não Wayland: o mecanismo de captura do reims-vgpu reporta `x11_grab_keyboard` quando faz `XGrabKeyboard` e `x11_unavailable` quando recusa. A prova exigida é essa observação (`window_capture_mode` / `mechanism=x11_grab_keyboard`) combinada com a janela fullscreen, não apenas a presença de `DISPLAY` no ambiente.

Nesta rodada: `REAL_XORG_SESSION_STARTED=no`, `REAL_MACOS_VM_STARTED=no`, nenhum unit systemd criado, T010 não iniciada.
