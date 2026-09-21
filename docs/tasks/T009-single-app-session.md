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

`Fullscreen::Borderless` continua sendo pedido. Sem WM ele não move nada e, com o monitor dummy do Xephyr, o backend pode retornar antes de solicitar foco. Por isso o appliance solicita e verifica `XSetInputFocus` explicitamente depois de anexar o presenter, pela mesma conexão Xlib da janela; o caminho normal não usa esse foco explícito nem `window.focus_window()`/EWMH.

A decisão é pura e testável, `FullscreenStrategy::resolve(window_system, fullscreen, x11_wmless)`, e só devolve o caminho WM-less quando as três respostas concordam. Wayland, X11 com window manager e `auto` continuam no caminho antigo.

Se `reims-launch.sh` retornar, `reims-session.sh` retorna com o mesmo status (via `exec`); nenhum shell, terminal ou desktop é aberto, e não há fallback silencioso para Wayland ou para um desktop.

Testes controlados: `tests/t009-single-app-session.py` (14 testes, `T009_CONTROLLED_TEST_PASS`), com `REIMS_HOST_ACTION_MODE=disabled` e fake `systemctl` primeiro no `PATH` (nunca chamado). Markers de sessão: `T009_X11_ENV`; `T009_DISPLAY_OVERRIDE`; `T009_XAUTHORITY_PRESERVED`; `T009_FULLSCREEN_CONTRACT`; `T009_HOST_WINDOW_CONTRACT`; `T009_VULKAN_CONTRACT`; `T009_WMLESS_X11_CONTRACT`; `T009_WAYLAND_ENV_CLEARED` e `T009_X11_NO_WAYLAND_ENV`; `T009_LAUNCHER_CHAIN`; `T009_EXIT_STATUS_PRESERVED`; `T009_NO_WM_DEPENDENCY`; `T009_NO_SYSTEMCTL`. Markers do seletor no companion: `T009_VGPU_X11_SELECTOR`; `T009_VGPU_X11_REQUIRES_DISPLAY`; `T009_VGPU_AUTO_COMPAT`. Markers Rust do caminho WM-less: `T009_VGPU_WMLESS_STRATEGY`; `T009_VGPU_WMLESS_GEOMETRY`; `T009_VGPU_WMLESS_X11_FULLSCREEN`; `T009_VGPU_WMLESS_FOCUS_POLICY`; `T009_VGPU_WMLESS_FOCUS_VERIFY`; `T009_VGPU_WMLESS_FOCUS_OBSERVABILITY`; `T009_VGPU_WMLESS_X11_FOCUS`. Markers Rust da política de geometria: `T009_VGPU_WMLESS_PRIMARY_MONITOR`; `T009_VGPU_WMLESS_MONITOR_FALLBACK`; `T009_VGPU_WMLESS_ROOT_FALLBACK`; `T009_VGPU_WMLESS_INVALID_ROOT_REFUSED`; `T009_VGPU_WMLESS_ROOT_ERROR_REFUSED`; `T009_VGPU_WMLESS_GEOMETRY_SOURCE`. Além deles, o reims-vgpu emite na linha always-on `host_window_mode` qual caminho rodou e de onde veio a geometria: `window_system=x11 wm=none fullscreen=override_redirect geometry_source=monitor position=+0,+0 size=1920x1080` (ou `geometry_source=x11_root` quando o fallback respondeu), contra `wm=external fullscreen=ewmh geometry_source=none` no caminho comum. No caminho WM-less, também emite `host_window_focus mechanism=x11_set_input_focus status=verified` somente depois de confirmar `XGetInputFocus`.

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

## Segundo runtime real: geometria corrigida, foco/input ainda falhando

O segundo runtime foi executado no mesmo Xephyr controlado (`:91`, root `1600x900`, sem window manager). A correção de geometria foi comprovada:

```text
host_window_mode window_system=x11 wm=none fullscreen=override_redirect
geometry_source=x11_root position=+0,+0 size=1600x900
Reims window: 1600x900, override_redirect=yes, map_state=IsViewable
```

Resultado: `T009_REAL_WMLESS_MODE=PASS`, `T009_REAL_FULLSCREEN_GEOMETRY=PASS` e `T009_REAL_OVERRIDE_REDIRECT=PASS`.

O capture foi construído, mas não engajou:

```text
host_window_capture_mode mechanism=x11_grab_keyboard
host_window_capture_engaged ausente
USER_MOUSE_CONFIRMED=no
USER_KEYBOARD_CONFIRMED=no
```

A causa é o monitor dummy do `winit` (`native_id() == 0`): no caminho `Fullscreen::Borderless`, o backend retorna antes de `set_fullscreen_hint(true)` e do `set_input_focus()` interno. Sem foco, `WindowEvent::Focused(true)` não chega, `Keyboard::focus(true)` não solicita `XGrabKeyboard` e o input não funciona. O encerramento manual da VM foi classificado como `QEMU_FATAL`/`qemu_exit_nonzero`; isso não motivou alterações em T005–T008.

Correção follow-up: no caminho `X11 + fullscreen + WM-less`, depois de criar a janela e anexar o presenter, o Reims usa `XSetInputFocus` pela mesma conexão `Display*` dos raw handles Xlib da janela, confirma `IsViewable` com `XGetWindowAttributes` e valida o alvo com `XGetInputFocus`. A linha `host_window_focus ... status=verified` é emitida somente após essa confirmação. O caminho normal não solicita foco explícito, e `window.focus_window()`/EWMH não é usado.

### Runtime #3: foco/capture confirmados, mouse visual ausente e SIGSEGV GPU

O runtime #1 provou o servidor, mas falhou na geometria; o runtime #2 provou a geometria, mas falhou no input; o runtime #3 confirmou foco, capture e teclado, mas não confirmou o ponteiro visual e terminou com `QEMU_FATAL` por SIGSEGV independente no caminho Vulkan:

```text
geometry_source=x11_root position=+0,+0 size=1600x900
window=1600x900 override_redirect=yes map_state=IsViewable
host_window_focus mechanism=x11_set_input_focus status=verified
host_window_capture_engaged mechanism=x11_grab_keyboard
USER_KEYBOARD_CONFIRMED=yes
USER_MOUSE_CONFIRMED=no
classification=QEMU_FATAL
classification_reason=qemu_runtime_segfault
```

O cursor guest só chegava a `qemu_console_set_mouse`/`qemu_console_set_cursor`, enquanto a janela real usa `winit/Vulkan` com `-display none`; não havia consumidor de posição, glyph ou visibilidade na host-window. O transporte `CursorMoved → InputPointerMove → usb-tablet` ficou não provado por falta de observabilidade. O core mostrou `SIGSEGV` em `write_staging_from_runs → stage_buffer_content`, após falhas `vk_slab_allocate_memory` e pressão de registry/slab; isso não foi atribuído ao mouse.

Correção implementada depois do runtime #3: espelhamento latest-wins do cursor guest para a host-window usando `winit::window::CustomCursor`, sem composição Vulkan, sem warp da posição host e com eventos de cursor separados de `FramePublished`. `CursorUpdate` e `CursorGlyph` continuam sendo devolvidos intactos ao caminho QEMU-console. Foi adicionada observabilidade limitada do primeiro pointer move/button e das mudanças de cursor. O runtime #4 confirmou o caminho end-to-end de geometria, foco, capture, cursor, movimento e clique; T009 continua `[-]` enquanto a finalização natural ainda não é reproduzida.

### Hardening pós-mortem do runtime #3

O core do runtime #3 foi reaberto em modo somente leitura. A falha continua
classificada como `SIGSEGV` em `write_staging_from_runs`, durante o
`copy_nonoverlapping`: a origem estava no `memfd` da RAM do guest e o destino
era o endereço usado pela escrita de staging persistente. A pressão de slab e
as falhas de alocação Vulkan ocorreram no mesmo período, mas não constituem,
sozinhas, prova de causa.

Foi implementado um hardening seletivo no `reims-vgpu`:

- os fallbacks que copiam `GuestRuns` agora usam slots de staging dedicados;
- esses slots fazem `map/write/unmap` por escrita e não retêm ponteiro host;
- o caminho comum de bytes mantém o slab persistente, para não ampliar a
  regressão de desempenho além do caminho que apresentou o crash;
- o recycle do fallback recusa slots slab persistentes já livres;
- a métrica de alocação dedicada é separada como `staging_buffer`.

Validação local: os cinco testes de `staging_mapping_tests` passaram, incluindo
o teste de mistura entre slot persistente e snapshot CPU. A suíte da biblioteca
teve 2249 testes aprovados e uma falha temporal preexistente em
`runtime::drain::tests::the_drain_duty_census_separates_a_flush_tail_from_a_flush_mean`.
Os exemplos de host-window foram atualizados para a assinatura atual do cursor;
`cargo test --no-run` do pacote passou. O clippy estrito continua bloqueado por
avisos preexistentes fora desta mudança; com esses avisos explicitamente
permitidos, o clippy do alvo modificado passa.

O runtime #4 não reproduziu o crash, mas não alcançou shutdown natural. A task
permanece `[-]` até uma validação live controlada confirmar estabilidade e
finalização do lifecycle após este hardening.

### Runtime #5: estabilidade Vulkan/QEMU após o hardening

Foi executada uma rodada live controlada em `Xephyr :92`, root `1600x900`, sem
window manager, usando a sessão dedicada, Vulkan e o estado instalado já
validado. O QEMU foi identificado pelo supervisor, o QMP ficou disponível e o
primeiro frame foi apresentado como `1600x900` com três drawables. A janela
observada foi `Reims vGPU`, `1600x900+0+0`, ocupando o root do Xephyr.

Durante aproximadamente três minutos de execução, não houve
`VK_ERROR_DEVICE_LOST`, `SIGSEGV`, abort, assertion ou pânico serial. O
resultado foi encerrado pelo timeout controlado para não deixar a VM indefinida:

```text
host_window_mode ... wm=none fullscreen=override_redirect
reims-vgpu-window: first frame presented (1600x900, 3 drawables)
QMP: available=true, SHUTDOWN reason=host-signal, guest=false
classification=EXTERNAL_SIGNAL
recovery_required=false
```

A evidência completa está em `/tmp/reims-t009-r5-AnZvyL/`, incluindo
`result.json`, `lifecycle.log`, `qemu.log` e `serial.log`. O encerramento do
supervisor deixou o processo QEMU filho como zumbi até a limpeza explícita do
harness; não houve processo QEMU/Xephyr ativo após a limpeza. Esta rodada
confirma estabilidade Vulkan/QEMU dentro da janela observada, mas não confirma
shutdown natural do guest; por isso T009 continua `[-]`.

Uma sondagem posterior de lifecycle (runtime #7) também terminou sem sinal
externo: `QMP SHUTDOWN guest=true reason=guest-reset`, `qemu_exit_code=0` e
`classification=GUEST_REBOOT`. Isso confirma que o supervisor correlaciona e
classifica um terminal produzido pelo guest, sem marcadores Vulkan fatais, mas
não substitui `guest-shutdown`; a distinção continua aberta para T009.

Para separar estado persistente contaminado de regressão do hardening, a fixture
limpa de `/home/felipeab10/Documentos/reims-t002-fixtures/runtime-sequoia-retry-2`
foi clonada por reflink para um runtime isolado. `qemu-img check` não encontrou
erros; a sessão atual apresentou o primeiro frame Vulkan e `guest_frame` via
rail resident, mas o guest terminou novamente em `GUEST_REBOOT` antes de
completar o banner SSH (`Connection timed out during banner exchange`). Não
houve SIGSEGV, `VK_ERROR_DEVICE_LOST` ou pânico serial. A fixture original não
foi escrita. Isso reforça que o bloqueio restante é a finalização/boot do guest,
não uma falha Vulkan observada nesta implementação.

`mechanism=x11_grab_keyboard` (`XGrabKeyboard`, na linha `window_capture_mode`) prova que o `winit` abriu X11 e não Wayland — é a evidência do **backend**. Ela não prova que o servidor é Xorg: o Xwayland da sessão niri também oferece X11/Xlib e produziria o mesmo mecanismo. São duas camadas, e uma não substitui a outra:

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
