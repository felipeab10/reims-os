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
REIMS_VGPU_X11_WMLESS=1    contrato da sessão, não desligável nela
REIMS_VGPU_WINDOW=1        default se ausente
REIMS_VGPU_FULLSCREEN=1    default se ausente
REIMS_VGPU_BACKEND=vulkan  default se ausente
```

`winit 0.30` não tem `WINIT_UNIX_BACKEND` e prefere Wayland quando `WAYLAND_DISPLAY`/`WAYLAND_SOCKET` e `DISPLAY` coexistam. Por isso o seletor do companion remove as variáveis Wayland em `x11` e recusa quando `DISPLAY` está vazio, e o `boot-x86.sh` não recria `WAYLAND_DISPLAY` nesse modo. Um `DISPLAY` definido, por si só, não prova X11.

## Modo X11 sem window manager (correção do blocker da revisão)

`winit 0.30` implementa `Fullscreen::Borderless` no X11 como um pedido EWMH: envia `_NET_WM_STATE_FULLSCREEN` ao root e espera que um window manager redimensione a janela. A sessão dedicada do Reims não tem window manager por projeto, então o pedido não tem quem o atenda e a janela permanece no tamanho com que foi criada — mesmo com `REIMS_VGPU_FULLSCREEN=1`. Não é defeito do winit; é o contrato do EWMH.

Por isso o appliance tem um caminho explícito, `REIMS_VGPU_X11_WMLESS` (default `0`; só a sessão do Reims o liga):

- a janela é criada `override_redirect`, sem decoração e não redimensionável;
- a geometria vem de uma política pura e única, `WmLessX11Geometry::resolve`, nesta ordem: (1) monitor primário utilizável; (2) primeiro monitor utilizável; (3) retângulo do root X11; (4) recusa explícita;
- "utilizável" é `native_id() != 0`. O backend X11 do `winit` devolve um monitor *placeholder* de `1x1` com id `0` quando o RandR não oferece CRTC, em vez de devolver `None`;
- o root X11 é lido pela conexão que o `ActiveEventLoop` já possui (`HasDisplayHandle` → `RawDisplayHandle::Xlib`, `XRootWindow`/`XGetWindowAttributes` via `x11-dl`): sem `XOpenDisplay`, sem segunda conexão e sem `xrandr`/`xdpyinfo`/`xwininfo` no produto;
- root com dimensão `<= 1` é recusado (`window_x11_root_geometry_invalid`), nunca aplicado.

`Fullscreen::Borderless` continua sendo pedido. Sem WM ele não move nada, e é ele que faz o `winit` chamar `XSetInputFocus` quando a janela fica visível — o foco de teclado independente de `_NET_ACTIVE_WINDOW` de que esta sessão precisa. O que mudou é que ele deixou de ser a única coisa que define a geometria.

A decisão é pura e testável, `FullscreenStrategy::resolve(window_system, fullscreen, x11_wmless)`, e só devolve o caminho WM-less quando as três respostas concordam. Wayland, X11 com window manager e `auto` continuam no caminho antigo.

Se `reims-launch.sh` retornar, `reims-session.sh` retorna com o mesmo status (via `exec`); nenhum shell, terminal ou desktop é aberto, e não há fallback silencioso para Wayland ou para um desktop.

Testes controlados: `tests/t009-single-app-session.py` (14 testes, `T009_CONTROLLED_TEST_PASS`), com `REIMS_HOST_ACTION_MODE=disabled` e fake `systemctl` primeiro no `PATH` (nunca chamado). Markers de sessão: `T009_X11_ENV`; `T009_DISPLAY_OVERRIDE`; `T009_XAUTHORITY_PRESERVED`; `T009_FULLSCREEN_CONTRACT`; `T009_HOST_WINDOW_CONTRACT`; `T009_VULKAN_CONTRACT`; `T009_WMLESS_X11_CONTRACT`; `T009_WAYLAND_ENV_CLEARED` e `T009_X11_NO_WAYLAND_ENV`; `T009_LAUNCHER_CHAIN`; `T009_EXIT_STATUS_PRESERVED`; `T009_NO_WM_DEPENDENCY`; `T009_NO_SYSTEMCTL`. Markers do seletor no companion: `T009_VGPU_X11_SELECTOR`; `T009_VGPU_X11_REQUIRES_DISPLAY`; `T009_VGPU_AUTO_COMPAT`. Markers Rust do caminho WM-less: `T009_VGPU_WMLESS_STRATEGY`; `T009_VGPU_WMLESS_GEOMETRY`; `T009_VGPU_WMLESS_X11_FULLSCREEN`. Markers Rust da política de geometria: `T009_VGPU_WMLESS_PRIMARY_MONITOR`; `T009_VGPU_WMLESS_MONITOR_FALLBACK`; `T009_VGPU_WMLESS_ROOT_FALLBACK`; `T009_VGPU_WMLESS_INVALID_ROOT_REFUSED`; `T009_VGPU_WMLESS_ROOT_ERROR_REFUSED`; `T009_VGPU_WMLESS_GEOMETRY_SOURCE`. Além deles, o reims-vgpu emite na linha always-on `host_window_mode` qual caminho rodou e de onde veio a geometria: `window_system=x11 wm=none fullscreen=override_redirect geometry_source=monitor position=+0,+0 size=1920x1080` (ou `geometry_source=x11_root` quando o fallback respondeu), contra `wm=external fullscreen=ewmh geometry_source=none` no caminho comum.

## Primeiro runtime real: falha de geometria e correção

O primeiro runtime real da T009 rodou num X11 nested controlado (`Xephyr :91`, root `1600x900`, sem window manager) e **falhou**. A evidência fica registrada:

```text
T009_RUNTIME_STATUS=FAIL_WMLESS_GEOMETRY

host_window_mode window_system=x11 wm=none fullscreen=override_redirect position=+0,+0 size=1x1
xwininfo -id 0x200002  Width 1, Height 1, Override Redirect State: yes, Map State: IsViewable
root X11              Width 1600, Height 900
```

O caminho WM-less foi selecionado corretamente (`wm=none fullscreen=override_redirect`); a janela é que ficou com um pixel. Causa: o backend X11 do `winit 0.30.13` enumera monitores por **CRTCs do RandR 1.2**, e o Xephyr não anexa CRTC ao seu output (`CRTC: 0`, `CRTCs: 0`). Com a lista de CRTCs vazia, `primary_monitor()` devolve o monitor *placeholder* interno do winit — `id: 0`, `1x1`, posição `0,0` — e nunca `None`. A política antiga só tratava `None` como ausência, então `window_no_monitor` nunca disparava e a janela era criada em `1x1`: a mesma classe de falha que o caminho WM-less existe para evitar, apenas com outro número no lugar de 1280x800.

Correção (reims-vgpu PR #5, commit `fix(window): fall back to X11 root geometry [T009]`): a geometria virou uma política pura, `WmLessX11Geometry::resolve`, com a ordem já descrita e a fonte carregada no resultado. O placeholder é reconhecido por **identidade** (`native_id() == 0`; `is_dummy()` do winit é exatamente `id == 0` e é `pub(crate)`), não por tamanho. Sem monitor utilizável, o retângulo do root X11 é a resposta, lido pela conexão do próprio event loop. Recusas tipadas: `window_x11_root_handle` (display handle não é Xlib), `window_x11_root_geometry` (a chamada Xlib falhou) e `window_x11_root_geometry_invalid` (root `<= 1`). A linha `host_window_mode` ganhou `geometry_source=monitor|x11_root|none`, para que um fallback nunca passe por monitor medido.

O runtime que falhou não foi descartado: a evidência ficou em `/tmp/reims-t009-xephyr-oY7L8A/` (`reims-vgpu-fail.delta.frozen.log`, `qemu.environ`, `xwininfo-*`) e em `/home/felipeab10/Documentos/reims-t009-runtime-oY7L8A/` (`result.json`, `lifecycle.log`). O encerramento dele classificou `EXTERNAL_SIGNAL`/`supervisor_signal` porque a janela de 1 pixel tornava o Apple menu inalcançável; isso não é defeito de T005–T008 e nada foi alterado por causa disso.

### Validação real pendente

O primeiro runtime provou o backend e o servidor, mas falhou na geometria. Com a correção acima, um novo runtime é necessário para provar a janela de verdade. `mechanism=x11_grab_keyboard` (`XGrabKeyboard`, na linha `window_capture_mode`) prova que o `winit` abriu X11 e não Wayland — é a evidência do **backend**. Ela não prova que o servidor é Xorg: o Xwayland da sessão niri também oferece X11/Xlib e produziria o mesmo mecanismo. São duas camadas, e uma não substitui a outra:

1. **Backend do winit** — `mechanism=x11_grab_keyboard` em `window_capture_mode`; depois que a janela recebe foco, `window_capture_engaged` com o mesmo mecanismo.
2. **Servidor** — o `DISPLAY` atendido por um servidor Xorg/Xephyr controlado nesta sessão dedicada, explicitamente não pelo Xwayland do niri. A evidência é qual servidor atende o display, não o nome da variável.

Além do log, medir a janela. `REIMS_VGPU_FULLSCREEN=1` é variável de ambiente e não prova fullscreen; a linha `host_window_mode` diz o que foi *pedido* (`wm=none fullscreen=override_redirect position=+0,+0 size=1920x1080`), e a prova é a geometria observada contra o root X11:

```text
root X11          = 1920x1080
Reims window      = 1920x1080
position          = +0+0
override_redirect = yes
```

O valor exato depende do servidor usado. No harness `Xephyr` já validado, o esperado depois da correção é `geometry_source=x11_root` com `position=+0,+0 size=1600x900`, porque aquele servidor não tem CRTC; num Xorg físico, `geometry_source=monitor`.

Nesta rodada: `REAL_XORG_SESSION_STARTED=no`, `REAL_MACOS_VM_STARTED=no`, nenhum unit systemd criado, T010 não iniciada.
