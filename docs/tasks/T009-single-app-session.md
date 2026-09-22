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
REIMS_VGPU_GUEST_IMPORT=off  workaround de estabilidade; override explícito preservado
REIMS_VGPU_SAMPLED_IDENTITY=off  mitigação visual; override explícito preservado
```

### Mitigação de estabilidade do guest

O primeiro boot limpo com `reims-vgpu-pci` reproduziu kernel panic/reboot loop
quando o caminho padrão de importação direta da RAM do guest estava ativo. O
mesmo disco chegou ao Setup Assistant com QEMU do host, com `vmware-svga` e
com `REIMS_VGPU_GUEST_IMPORT=off`; neste último caso o dispositivo customizado
permaneceu estável. A sessão dedicada, portanto, força `off` e usa o caminho
de cópia como mitigação temporária. Isso não corrige os glitches visuais nem
marca a T009 como concluída; a investigação do import direto fica separada no
`reims-vgpu`.

O cache de identidade de texturas amostradas também fica desligado por padrão na
sessão T009. Um teste controlado com a mesma instalação mostrou que sua
desativação remove os artefatos stale do ícone, título e corpo da tela; os
artefatos restantes em fontes de listas e botões continuam sendo investigados
separadamente no caminho de upload/formato. A opção continua sendo override
explícito para permitir uma comparação futura.

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

Como controle, a mesma fixture limpa foi iniciada novamente com os recursos
históricos de sua validação (`16G`, `8` cores). O resultado foi idêntico:
primeiro frame Vulkan, porta TCP aberta sem banner SSH completo e
`GUEST_REBOOT`/`guest-reset` com exit 0. A hipótese de que o reboot fosse
causado apenas pelo perfil `8G/4` fica, portanto, descartada.

### Runtime #16: seleção explícita no OpenCore e handoff ao XNU

As sondagens anteriores não distinguiam um timeout/reinício do menu OpenCore
de uma falha do macOS. Em uma rodada controlada, após o primeiro frame, o
harness enviou `Return` por XTest ao display `Xephyr :103`. O log confirmou a
entrega da tecla (`keycode=36`, press/release), e a captura posterior deixou de
mostrar o menu OpenCore: mostrou o boot verbose do macOS. O serial preservado
também registrou `#[EB|LOG:HANDOFF TO XNU]`, sem `SIGSEGV`,
`VK_ERROR_DEVICE_LOST` ou pânico serial.

Esse resultado corrige a interpretação das sondagens da fixture: o estado
marcado como instalado ainda apresentava o menu OpenCore com `1. OSX`, e a
fixture T002 apresentava o fluxo de instalação/recuperação. Portanto,
`GUEST_REBOOT` isolado nessas rodadas não prova que o macOS tenha falhado antes
do boot; era necessário selecionar explicitamente o volume.

Mesmo com a seleção correta, o runtime #16 terminou em
`QMP SHUTDOWN guest=true reason=guest-reset`, com exit 0, antes de uma sessão
SSH utilizável. A tentativa posterior de `shutdown -h now` recebeu conexão
recusada porque o guest já havia reiniciado. A evidência atual estreita o
bloqueio para a estabilidade do boot macOS após o handoff ao XNU; ainda não
confirma desktop, shutdown natural ou conclusão de T009. Artefatos:
`/tmp/reims-t009-r16-2W0d2q/` (`after-enter.png`, `result.json` e serial
preservado).

### Runtime #18: modo pause para preservar o ponto pós-XNU

Para distinguir um reboot do guest de um encerramento imposto por
`-action reboot=shutdown`, foi repetida a sondagem com
`QEMU_REBOOT_ACTION=pause`, em uma cópia isolada do estado instalado, com
`16G/8` (o perfil histórico da fixture). Após o primeiro frame, o mesmo
`Return` foi entregue ao OpenCore por XTest. O QEMU permaneceu vivo por mais
de 25 segundos, e a captura continuou mostrando o boot verbose do macOS; não
houve evento terminal QMP nesse intervalo.

Nesse estado o monitor QMP não respondeu à consulta `query-status`, e a rodada
foi encerrada externamente para liberar os recursos. O resultado final foi,
corretamente, `EXTERNAL_SIGNAL`, não `GUEST_SHUTDOWN` nem `GUEST_REBOOT`. A
rodada é evidência de que o caminho consegue preservar o ponto pós-XNU para
diagnóstico, mas não prova desktop, estabilidade completa ou shutdown natural.
O artefato está em `/tmp/reims-t009-r18-96Qk9u/`; a cópia de estado usada foi
`/home/felipeab10/Documentos/reims-t009-runtime-pause-candidate-reims-t009-r18-96Qk9u/`.

### Runtime #20: pacote de evidência T002 sob o build atual

Foi feita uma nova cópia reflink do pacote de evidência de
T002, `/home/felipeab10/Documentos/reims-t002-fixtures/runtime-sequoia-retry-2`.
`qemu-img check` passou e a cópia vem do diretório onde a evidência T002
documentou `ProductVersion 15.8`, SSH e autoboot. A auditoria posterior abaixo
mostrou que esses discos foram modificados depois daquela prova. Com o
QEMU/reims-vgpu atual do PR, Xephyr e a seleção explícita `Return` no OpenCore,
o comportamento foi novamente: primeiro frame Vulkan, handoff ao XNU,
nenhum login SSH e `QMP SHUTDOWN guest=true reason=guest-reset`.

Essa rodada também resolveu uma ambiguidade de comparação. A evidência histórica
de desktop foi produzida em outro checkout (`reims-macos-appliance-runtime`),
com QEMU pré-construído, Wayland e janela `948x1034`; não é uma validação do
build atual, do servidor Xephyr ou do caminho WM-less desta PR. Portanto, a
fixture não deve mais ser classificada como installer/recovery, mas o desktop
histórico também não pode ser usado como prova de não regressão do build atual.
Artefatos da repetição: `/tmp/reims-t009-r20-i7fElV/`; cópia isolada:
`/home/felipeab10/Documentos/reims-t009-runtime-t002-candidate-reims-t009-r19-7P4V7x/`.

### Runtime #21: reboot do QEMU preservado

Para testar se `reboot=shutdown` era apenas um falso bloqueio de lifecycle, a
mesma fixture T002 foi iniciada novamente com o build atual e
`QEMU_REBOOT_ACTION=reset`. Após a seleção explícita no OpenCore, o QEMU
permaneceu vivo por mais de dois minutos, mas o SSH continuou indisponível e
nenhum desktop foi alcançado. A rodada foi encerrada externamente; seu
resultado operacional foi `EXTERNAL_SIGNAL`, sem `SHUTDOWN guest=true`.

Isso separa as duas conclusões: `reboot=shutdown` explica por que as rodadas
anteriores terminavam e eram classificadas como `GUEST_REBOOT`, mas não é a
causa suficiente da ausência de desktop. Com `reboot=reset`, o boot atual ainda
fica preso após o handoff ao XNU. Artefatos: `/tmp/reims-t009-r21-tHXxfA/`.

### A/B do staging: baseline `158888b`

Para verificar se o hardening de `GuestRuns` era a causa do bloqueio, a revisão
imediatamente anterior ao commit `ff076191` foi compilada em um worktree
isolado, ligada a um QEMU separado e executada com a mesma fixture T002,
Xephyr/X11, `1600x900`, OpenCore selecionado explicitamente e
`QEMU_REBOOT_ACTION=reset`. O baseline apresentou o mesmo primeiro frame
Vulkan e o mesmo `#[EB|LOG:HANDOFF TO XNU]`, mas não disponibilizou SSH durante
a janela observada; a rodada também precisou ser encerrada externamente.

Esse A/B não reproduz uma melhora com o staging antigo e elimina o hardening
como causa suficiente do bloqueio atual. A alteração permanece válida para o
SIGSEGV original do runtime #3, mas o problema de boot pós-XNU continua
independente e deve ser investigado no caminho de host-window/X11 ou na
interação gráfica do guest atual. Artefatos: `/tmp/r26-x35N2I/`; baseline:
`158888b33c00fc2832260f6ecbf4ce9d169a7ea7`.

### Runtime #27: replay do estado do runtime #4

Para verificar se o resultado interativo do runtime #4 ainda era reproduzível,
foi feita uma cópia reflink do estado usado naquela rodada
(`/home/felipeab10/Documentos/reims-t009-runtime-20260921-115920`) e a sessão
foi repetida com o build atual, `16G/8`, Xephyr/X11 `1600x900`,
`QEMU_REBOOT_ACTION=reset` e seleção explícita do OpenCore por `Return`.
O primeiro frame Vulkan apareceu e o `XTest` enviou o evento de teclado, mas o
guest não ofereceu SSH nem desktop durante aproximadamente dois minutos. O
QMP registrou somente eventos de execução (RTC/NIC); a rodada foi encerrada
externamente e classificada como `EXTERNAL_SIGNAL`.

Essa repetição não invalida a evidência end-to-end do runtime #4, que continua
provando geometria, foco, capture, cursor, movimento e clique naquela sessão.
Ela mostra, porém, que esse resultado não é reproduzível com o build atual e
que a procedência do estado importa: a cópia do runtime #4 estava marcada
como `recovery` e usava o perfil `8G/4`, enquanto a fixture T002 autoritativa é
`installed` e foi validada historicamente com outro checkout/Wayland. Portanto,
o bloqueio permanece no boot gráfico pós-XNU, não há base para marcar T009 como
concluída e não é seguro avançar para merge.

Artefatos: `/tmp/reims-t009-r27-v5lzwn/`; cópia isolada:
`/home/felipeab10/Documentos/reims-t009-runtime-r4-candidate-reims-t009-r27-v5lzwn/`.

### Auditoria de procedência pós-runtime #27

A comparação binária confirmou que o `OVMF_CODE.fd` e o `OVMF_VARS.fd` são
idênticos entre a cópia do runtime #4 e a fixture T002. Os discos, porém, não
são o mesmo estado: `macos.qcow2` diverge no offset `209735680` e
`OpenCore.qcow2` no offset `1208320`. Isso impede tratar o replay do runtime #4
como uma repetição da fixture autoritativa.

Também foi confirmado que a sessão histórica que chegou ao desktop usava um
ROM GOP antigo (`5544adcc...`), Wayland e o checkout
`reims-macos-appliance-runtime`; o build atual usa outro ROM (`45b34a61...`) e
X11/Xephyr. As repetições #20, #21 e o A/B do baseline, contudo, já usaram a
fixture T002 e o build atual, chegaram ao mesmo handoff ao XNU e não chegaram
ao desktop. A diferença de ROM/servidor explica por que o sucesso histórico
não é uma prova de não regressão, mas ainda não identifica sozinha a causa do
travamento pós-XNU.

### Runtime #29: A/B com o ROM GOP histórico exato

Para testar essa diferença isoladamente, a fixture T002 foi copiada novamente
e executada com o mesmo QEMU atual, Xephyr/X11 `1600x900`, `16G/8`,
`QEMU_REBOOT_ACTION=reset` e o ROM GOP exato referenciado pelo runtime
histórico (`/home/felipeab10/Documentos/REIMS macOS APPLIANCE/crates/reims-vgpu-efi/out/reims-vgpu-gop.rom`). O resultado foi o mesmo: primeiro frame,
`EXITBS:END`, `HANDOFF TO XNU`, nenhum SSH ou desktop e cinco eventos QMP
`RESET` do guest, em intervalos de aproximadamente 25 segundos, antes do
encerramento externo (`EXTERNAL_SIGNAL`).

Logo, trocar o ROM GOP atual pelo artefato histórico não é suficiente para
recuperar o desktop. O ROM permanece uma diferença de proveniência que impede
comparações ingênuas com o runtime histórico, mas o bloqueio reproduzido na
fixture T002 continua no caminho pós-XNU/QEMU.

Artefatos: `/tmp/reims-t009-r29-exact-oldrom-xPRf7L/`; cópia isolada:
`/home/felipeab10/Documentos/reims-t009-runtime-ab-exact-oldrom-r29-exact-oldrom/`.

### Retificação: a fixture T002 não preserva o estado do desktop

A evidência T002 continua válida: `desktop-reached.txt` registrou macOS 15.8 e
SSH às 19:20 de 18/09/2026, seguido de shutdown solicitado pelo guest. Porém,
os discos persistentes não foram congelados naquele ponto. A cronologia local
mostra `OpenCore.qcow2` modificado às 23:11 e `macos.qcow2` às 23:12 do mesmo
dia, durante rodadas posteriores de T003. Os seriais posteriores já registram
o `Boot0080` inválido e repetições de `HANDOFF TO XNU` sem desktop.

Assim, o diretório é autoritativo como **pacote de evidência**, mas não como
imagem imutável do estado que chegou ao desktop. Os runtimes #20, #21, #26 e
#29 reproduzem de forma consistente o estado posterior em reboot loop; eles
não demonstram regressão do QEMU/Vulkan contra o disco bem-sucedido de 19:20,
que não está preservado em snapshot interno nem em outra cópia local
identificada. O bloqueador passa a ser a ausência de uma fixture instalada e
congelada para validar desktop e shutdown natural no build atual.

### Runtime #30: candidato instalado T001

Como alternativa local, foi copiada por reflink a fixture T001 que documenta
desktop, shutdown e reboot persistentes. Com o build atual, Xephyr/X11,
`1600x900`, `16G/8` e autoboot `Boot0002`, a sessão chegou a `EXITBS:END` e
`HANDOFF TO XNU`, mas não ofereceu SSH durante mais de seis minutos. Diferente
do pacote T002 posterior, não houve `RESET` QMP nesse intervalo; também não foi
emitido `first guest frame presented via rail resident`. A rodada foi encerrada
externamente por `SIGINT` e o QEMU residual foi terminado explicitamente.

Esse candidato evita o reboot loop da imagem T002 tardia, mas ainda não é uma
fixture congelada no instante da prova: seu `macos.qcow2` foi modificado às
14:12, depois das evidências de desktop e persistência registradas entre 14:02
e 14:08. Portanto, ele também não permite atribuir a ausência de desktop ao
build atual sem um A/B adicional com o QEMU histórico exato.

Artefatos: `/tmp/reims-t009-r30b-t001-ZwWWgR/`; cópia isolada:
`/home/felipeab10/Documentos/reims-t009-runtime-t001-candidate-r30-t001/`.

### Runtimes #31–#33: A/B do QEMU/staticlib

O candidato T001 foi repetido com o QEMU histórico exato
(`reims-macos-appliance-runtime`, revisão `bb171c33`) e o ROM GOP histórico.
Esse braço publicou `first guest frame presented via rail resident`, abriu o
serviço SSH e chegou visualmente à tela de login do macOS. A captura
`desktop.png` mostra o lock screen às 18:14. Como a credencial histórica não
estava disponível para autenticação e shutdown, a sessão foi encerrada
externamente e classificada como `EXTERNAL_SIGNAL`; não houve panic ou reset.

Mantendo o mesmo candidato e ROM histórico, mas voltando ao QEMU/staticlib
atual, o guest não chegou à tela de login nem publicou o primeiro frame real;
houve dois resets QMP. Isso isola o ROM GOP: ele não é a causa suficiente da
regressão. O artefato que muda o resultado é o QEMU ligado à staticlib
reims-vgpu.

Por fim, o QEMU pré-hardening da revisão `158888b` foi executado pelo launcher
atual, com a mesma fixture e ROM. Ele também não publicou o primeiro frame do
guest nem ofereceu SSH. Portanto, `ff076191` não introduziu a regressão. O
primeiro commit ruim está no intervalo entre `bb171c33` (bom) e `158888b`
(ruim), que contém as mudanças T009 de seleção X11, fullscreen WM-less,
geometria, foco e cursor.

Artefatos:

- bom histórico: `/tmp/reims-t009-r31-t001-historical-2EwXY1/`;
- QEMU atual + ROM histórico: `/tmp/reims-t009-r32-current-qemu-oldrom-spJ2pM/`;
- pré-hardening `158888b`: `/tmp/reims-t009-r33b-prehardening-avm7DC/`.

### Runtimes #34–#37: bisect do cursor e correção parcial

O intervalo de regressão foi dividido com QEMUs separados, todos ligados à
staticlib da revisão correspondente e executados contra cópias frescas do
candidato T001 e o mesmo ROM histórico. `5199beb` (seleção X11), `2615dd8`
(fullscreen/geometria WM-less) e `9f93935` (foco WM-less) chegaram ao serviço
SSH. O commit seguinte, `a8bda71` (espelhamento do cursor), é o primeiro que
reproduz a perda dessa progressão. Essa classificação é limitada ao progresso
do boot/serviço: os braços bons do bisect não provaram desktop gráfico.

A revisão mostrou que `device_pop_action`, executado no BH do main loop do
QEMU, passou a adquirir `slot.window`, o mesmo lock mantido pela publicação de
frames durante consulta/cópia do residente Vulkan. Assim, uma atualização
cosmética de cursor podia bloquear a entrega das demais ações do guest. A
correção `cc3a6f3` move o slot e o wake do cursor para o dispositivo, fora do
lock de frame/Vulkan. Um teste de regressão mantém `slot.window` adquirido e
confirma que `CursorUpdate` ainda é entregue e espelhado.

O runtime #37 recompilou o QEMU atual com essa correção e repetiu o A/B com
cópia fresca de T001, ROM histórico, Xephyr `1600x900`, `16G/8` e
`QEMU_REBOOT_ACTION=reset`. O guest chegou brevemente ao handshake do sshd e
permaneceu mais de quatro minutos sem `RESET` QMP nem panic, eliminando o
reboot loop observado no braço ruim. Porém, a janela ficou no verbose boot, não
houve `first guest frame presented via rail resident`, e tentativas posteriores
de SSH pararam no banner. O encerramento externo produziu o evento QMP
`SHUTDOWN guest=false reason=host-signal`, mas o processo não terminou após
SIGINT/SIGTERM e precisou de SIGKILL. Portanto a correção resolve a contenção
introduzida pelo cursor, mas não fecha T009: ainda faltam o primeiro frame real,
desktop estável e shutdown natural.

Validação local da correção: QEMU x86_64/Vulkan recompilado com sucesso; teste
novo passou; suíte serial `2250 passed, 1 ignored`, com apenas o flaky já
conhecido `the_drain_duty_census_separates_a_flush_tail_from_a_flush_mean`.
O lint estrito continua barrado somente pelos quatro avisos baseline de
`chunks_exact_to_as_chunks` em `reims-vgpu-observe`.

Artefatos:

- `5199beb`: `/tmp/reims-t009-r34-5199-9Ie60p/`;
- `2615dd8`: `/tmp/reims-t009-r35-2615-rqWOzL/`;
- `9f93935`: `/tmp/reims-t009-r36-9f93935-gsFeQD/`;
- correção `cc3a6f3`: `/tmp/reims-t009-r37-cursor-unblocked-pFEsj7/`.

### Runtime #39: staging transitório corrigido, reset pós-XNU ainda aberto

O pós-mortem do runtime #3 encontrou uma segunda falha no hardening: os slots
dedicados de snapshot eram mapeados para a escrita, mas não eram desmapeados
antes de voltar ao pool. A segunda reutilização do mesmo `VkDeviceMemory`
tentava mapear uma alocação ainda marcada pelo driver como mapeada. A correção
`33ba39d` passa a devolver junto do ponteiro se o mapeamento foi transitório e
faz `vkUnmapMemory` exatamente ao fim das três escritas (`bytes`, `swap_rb` e
`GuestRuns`). O teste de staging agora recicla o mesmo snapshot, escreve uma
segunda vez e confirma a sequência map/write/unmap.

O QEMU foi recompilado com essa revisão e executado contra uma cópia fresca de
T001, ROM histórico, Xephyr `:106`/`1920x1080`, X11 WM-less, `16G/8` e
`QEMU_REBOOT_ACTION=reset`. O resultado separa claramente as duas partes:

- `first frame presented (1920x1080, 3 drawables)`;
- `first guest frame presented via rail resident (same-device zero-copy)`;
- nenhum `SIGSEGV`, `VK_ERROR_DEVICE_LOST`, abort ou pânico serial;
- depois do handoff ao XNU, o QMP registrou `RESET guest=true reason=guest-reset`
  aproximadamente a cada 65 segundos, repetindo `EFI GOP → EXITBS:END →
  HANDOFF TO XNU` no serial;
- a rodada foi encerrada externamente e classificada como
  `EXTERNAL_SIGNAL`, sem shutdown natural.

Assim, o unmap corrigido elimina a falha de mapeamento identificada no código
e permite publicar o primeiro frame, mas não resolve o reset pós-XNU. T009
continua `[-]`; o próximo diagnóstico deve comparar o caminho pós-frame/guest
watchdog, sem atribuir o reset ao staging na ausência de evidência Vulkan.

Artefatos: `/tmp/reims-t009-r39-staging-unmap-u2KFoO/`, especialmente
`logs/boot-20260921-191733-1b7e075f/{qemu.log,serial.log,lifecycle.log,result.json}`.

### Runtime #40: pausa pós-XNU sem reset observável

Foi feita uma sondagem somente diagnóstica em uma cópia reflink separada da
fixture #39, com `QEMU_REBOOT_ACTION=pause`, Xephyr `:107`, `16G/8` e trace
QEMU filtrado para `kvm_reset_vmfd`. O trace precisou ser reduzido a um evento:
o filtro combinado inicialmente foi rejeitado pelo QEMU por interpretar
`uefi_hard_reset` como opção booleana, e essa tentativa não chegou a criar uma
VM.

Na tentativa válida, o serial registrou um único ciclo completo de GOP,
`EXITBS:END` e `HANDOFF TO XNU`. Durante 105 segundos:

- o QMP permaneceu disponível, sem `RESET` ou `SHUTDOWN guest=true`;
- não houve `kvm_reset_vmfd`, panic serial ou erro Vulkan;
- a janela publicou apenas `first frame presented`, sem
  `first guest frame presented via rail resident`.

O supervisor foi interrompido pelo timeout controlado e classificou a sessão
como `EXTERNAL_SIGNAL`; o QEMU encerrou limpo após o sinal. A rodada não prova
estabilidade do desktop, mas preserva uma distinção útil: o reset observado em
`reset` não é reproduzido deterministically em `pause`, enquanto a publicação
do frame do convidado também não é determinística. Não há base para alterar o
guest-reset, o supervisor ou o caminho Vulkan sem uma captura que contenha o
evento causal.

Artefatos: `/tmp/reims-t009-r40b-trace/` e
`/home/felipeab10/Documentos/reims-t009-runtime-t001-r40-pause-trace/vms/reims-57f0fd6b61a74542/run-r40b/`.

### A/B #41/#42/#43: a regressão está no staticlib Rust atual e a entrada tinha uma corrida de foco

Para separar QEMU, firmware, disco e servidor X11 do código Rust, os braços
foram executados com a mesma cópia-base de T001, o mesmo OpenCore/OVMF, a
mesma ROM GOP, Xephyr e perfil `16G/8`. O QEMU também permaneceu no mesmo
commit do submódulo (`bd88218d`); variou apenas o checkout que produz o
staticlib Vulkan:

- #41, revisão histórica `bb171c33`, chegou a `first guest frame presented via
  rail resident` e não registrou reset durante a janela controlada;
- #42, revisão atual `fcc2d39`/`33ba39d`, publicou apenas o primeiro frame e
  registrou `RESET guest=true reason=guest-reset` aproximadamente 62 segundos
  depois, repetindo o ciclo EFI → XNU;
- #43, revisão anterior ao espelhamento do cursor (`9f93935`), recompilado
  isoladamente, publicou o frame do convidado e permaneceu sem reset durante
  105 segundos;
- #45, revisão atual, no caminho WM-less válido e com `pause`, voltou a publicar
  o frame do convidado durante 105 segundos.

Esse conjunto não prova uma regressão determinística no staticlib Rust: o braço
atual também consegue chegar ao frame quando o reset é impedido de reiniciar o
guest. O reset observado continua aberto e precisa de repetição com evidência
causal; T009 continua `[-]` até haver desktop macOS estável e shutdown natural.

A mesma investigação explicou a tela do OpenCore sem teclado/mouse observada
no Xephyr: a janela podia confirmar foco X11, mas a captura era solicitada
somente quando o `winit` emitia `Focused(true)`. Se esse evento chegasse antes
da ligação do presenter, a imagem aparecia sem a posse efetiva dos dispositivos.
O commit `7da0a360d4` torna a transição idempotente: após `XSetInputFocus` e
`XGetInputFocus` confirmarem a janela, o estado de teclado é marcado como
focado e `x11_grab_keyboard` é solicitado imediatamente. Os 33 testes do
presenter passaram com `--no-default-features --features backend-vulkan,host-window`.

Artefatos A/B: `/tmp/reims-t009-r41-historical-qemu/`,
`/tmp/reims-t009-r42-current-qemu-samebase/` e
`/home/felipeab10/Documentos/reims-t009-runtime-t001-r43-historical-rust/`.

O runtime #44 repetiu somente o braço atual com `QEMU_REBOOT_ACTION=pause`,
Xephyr `:112` e a mesma cópia-base. Publicou o frame de criação da janela,
mas não o primeiro frame do convidado e não registrou `VK_ERROR_DEVICE_LOST`,
panic ou shutdown natural antes do timeout. O resultado confirma que `pause`
interrompe a consequência visível do guest-reset, mas não corrige a ausência
da publicação pós-XNU; não há base para uma nova alteração especulativa no
backend Vulkan.

O #44 foi invalidado no pós-mortem: faltou `REIMS_VGPU_FULLSCREEN=1` e ele
rodou no caminho comum (`wm=external`, `fullscreen=sized`), fora do contrato
WM-less da T009. O artefato permanece somente como tentativa inválida:
`/home/felipeab10/Documentos/reims-t009-runtime-t001-r44-current-pause/`.

Artefato válido mais recente: `/home/felipeab10/Documentos/reims-t009-runtime-t001-r45-current-wmless-pause/`.

O runtime supervisionado #46 repetiu o braço atual com `reset`, agora com
`lifecycle.log`/`result.json` do supervisor preservados. A sessão usou o
caminho válido `wm=none fullscreen=override_redirect`, publicou apenas
`first frame presented` e não publicou `first guest frame`. O QMP registrou
`RESET guest=true reason=guest-reset` em aproximadamente 62 s e novamente em
aproximadamente 122 s; não houve panic serial, `VK_ERROR_DEVICE_LOST` ou erro
fatal Vulkan. O timeout externo veio depois da segunda repetição, portanto o
supervisor classificou a sessão como `EXTERNAL_SIGNAL`, sem apagar os resets
anteriores.

Esse é o padrão temporal mais forte até aqui: quando o caminho pós-XNU não
chega ao frame residente do convidado, o guest reinicia em ciclos de cerca de
60 s. Ainda não prova qual espera interna do guest expira, mas permite que a
próxima instrumentação correlacione o último `present`/`stamp` antes de cada
reset.

Artefato: `/home/felipeab10/Documentos/reims-t009-runtime-t001-r46-supervised-reset/logs/boot-20260921-213457-86bba867/`.

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

## Correção do postmortem — propagação do modo WM-less

O postmortem acima precisava de uma correção de cadeia. `reims-session.sh`
atribuía `REIMS_VGPU_X11_WMLESS=1`, mas a variável não estava na lista de
variáveis exportadas para o launcher. Assim, sondagens iniciadas pelo launcher
podiam registrar `fullscreen=on` e ainda chegar ao QEMU com
`x11_wmless=unset`, isto é, no caminho `wm=external`. Os artefatos que
registram essa combinação não são evidência válida do contrato WM-less e não
devem ser usados para concluir sobre a estabilidade da T009.

A correção foi aplicada no PR #8 em `8dd1844`: o seletor agora é exportado
junto com os demais parâmetros da sessão, e o teste T009 exige explicitamente
essa exportação. A cadeia passou novamente nos 14 testes controlados.

### Runtime #48 — primeiro boot realmente WM-less após a correção

Fixture isolada: `/home/felipeab10/Documentos/reims-t009-runtime-t001-r48-export-fix-1790041545/`.
O log confirmou simultaneamente:

```text
host_window_mode ... wm=none fullscreen=override_redirect geometry_source=x11_root position=+0,+0 size=1600x900
vgpu_env ... fullscreen=on x11_wmless=on ... window_system=x11
host_window_capture_engaged ... mechanism=x11_grab_keyboard
```

O runtime permaneceu vivo por 125 s sem `RESET` QMP, mas a fixture ficou no
picker do OpenCore porque essa sondagem não enviou `Return`; portanto não
houve `first guest frame`. Esse resultado valida a sessão e a captura, não o
boot do macOS.

### Runtime #49 — handoff ao XNU e bloqueador Vulkan/QEMU reproduzido

Fixture isolada: `/home/felipeab10/Documentos/reims-t009-runtime-t001-r49-return-wmless-1790041722/`.
O serial chegou a `#[EB|LOG:HANDOFF TO XNU]`, e o diagnóstico confirmou
`wm=none`, `x11_wmless=on` e captura engajada. Depois do handoff, o convidado
produziu trabalho gráfico e o backend registrou `vulkan_guest_reset` com
`resident=2`, seguido de `device_reset`; o supervisor classificou a sessão
como `GUEST_REBOOT`. Não houve `VK_ERROR_DEVICE_LOST`, SIGSEGV ou pânico
serial. Portanto o problema de teclado/captura e de seleção do caminho
WM-less está resolvido; o bloqueador restante é a estabilidade do guest após
o handoff gráfico, ainda sem base para marcar a T009 como concluída.

### Postmortem do runtime #4 — glitches Vulkan ainda não atribuídos

O runtime controlado com a instalação limpa do Ventura chegou ao Setup Assistant
com o caminho WM-less correto, foco/capture ativos e input funcional, mas exibiu
corrupção parcial em textos, ícones e controles. O mesmo padrão apareceu nas
telas “Transfer Your Data to This Mac” e “Written and Spoken Languages”. A
janela host não é a causa: o caminho QEMU com `vmware-svga` chegou ao mesmo
setup sem depender do renderizador Vulkan do `reims-vgpu`.

O postmortem foi somente leitura sobre os artefatos existentes; não houve novo
runtime, alteração de disco/EFI ou merge. A instrumentação registrou amostras
de residentes em `B8G8R8A8_UNORM`, com swizzle identidade, e também mostrou o
caminho normal de texturas de convidado (`bytes`/`guest_runs`). O modo
experimental que forçava snapshots para amostras residentes foi compilado e
executado como A/B; os glitches permaneceram. Isso descarta o snapshot como
correção suficiente e não justifica mantê-lo no código.

Há uma população pequena de quatro draws parciais classificados como
`draw_partial_preserving_unseeded_guest_backed`, com 13.884 texels de área
não coberta. Essa classificação é uma telemetria conservadora feita antes da
montagem final do `DrawRequest`; ela ainda não prova que esses quatro draws
destruíram pixels, pois o engine pode resolver o conteúdo por residente ou
backing compartilhado depois. A próxima implementação deve correlacionar essa
classificação com `Color0Load`, `load_uses_gpu_content`, identidade do alvo e
estado `content_ready` no ponto de admissão do render pass.

O resultado é consistente com a issue upstream
[`steelbrain/reims-vgpu#90`](https://github.com/steelbrain/reims-vgpu/issues/90),
que descreve corrupção tiled/white no caminho Vulkan Linux e recomenda
classificar o primeiro draw parcial incorreto e auditar LOAD/store, continuação
de pass e estado do residente. O bloqueador atual permanece aberto: há base
para uma próxima correção causal no backend Vulkan, mas não para marcar T009
como concluída.

### A/B seguinte — `REIMS_VGPU_COLOR_GENERAL=off`

O braço de controle repetiu a mesma fixture e os mesmos parâmetros, alterando
somente `REIMS_VGPU_COLOR_GENERAL=off`, para separar o layout unificado
`GENERAL` da sincronização de residentes. O guest chegou novamente ao Setup
Assistant, publicou `first guest frame presented via rail resident` e terminou
por timeout controlado, sem `VK_ERROR_DEVICE_LOST` ou reset observável. A tela
continuou com a mesma corrupção em textos, ícones e botões.

Esse braço aumentou os barriers esperados (`passheld_outside_resident_layout`),
mas os draws preservadores continuaram entrando majoritariamente como
`engine_partial_preserve_with_gpu_content`. Assim, tanto LOAD/store sem fonte
quanto o layout `GENERAL` foram descartados como explicação suficiente para os
glitches reproduzidos na instalação limpa. A próxima investigação deve focar a
produção/consumo dos residentes amostrados — especialmente a validade do
conteúdo entre o Store/writeback e o bind de textura — e não mais alternar
layouts globalmente.

### Auditoria estática seguinte — backing compartilhado e bind de residente

A revisão do ciclo `Store → residente → bind` não encontrou uma janela sem
estado de conteúdo. O caminho de amostra marca o residente como usado antes da
validação, exige geometria e `content_ready`, e só então escolhe entre bind
direto, snapshot ou feedback. Depois do submit, o alvo é publicado com o
`ColorWrite`/`ColorFeedback` efetivo; uma amostra residente avança para
`ShaderRead`, enquanto snapshot/feedback não sobrescrevem indevidamente o
estado do alvo que também é attachment.

Também foi confirmado o caso de primeiro LOAD a partir de memória compartilhada:
o import Vulkan nasce em `PREINITIALIZED`, e o draw grava a barreira para
`GENERAL` incluindo `HOST_WRITE` antes do render pass. O teste
`loading_shared_backing_orders_both_the_prior_gpu_access_and_host_writes`
protege essa relação. Portanto não há correção causal segura para aplicar nessa
camada com a evidência atual; o próximo dado necessário é o primeiro bind de
residente que chega com `content_ready/access/generation` incompatíveis com o
Store que o produziu.

### Instrumentação do próximo runtime — admissão de amostra residente

O PR #5 agora registra, no ponto efetivo de bind de `SampledSource::Target`, a
primeira combinação suspeita por geometria: residente ausente, `content_ready`
falso, dimensões divergentes ou multisampling incompatível. O evento inclui
`access`, geração, indicação de backing compartilhado e o motivo de reclaim
mais recente. A telemetria é limitada por `first_sight`, não altera barreiras,
layouts ou seleção de snapshot/feedback, e foi adicionada em
`abb9ccb8a9`.

Validações: 58 testes do executor Vulkan e build release passaram; nenhum
runtime novo foi iniciado. O próximo runtime controlado deve procurar
`sampled_resident_admission_suspect` no log antes de qualquer nova alteração de
sincronização.

### Runtime #50 — diagnóstico de admissão sem anomalia

Fixture controlada: `/home/felipeab10/Documentos/reims-t009-clean-sequoia-v2/`;
serial: `components/reims-vgpu/vm/disks/run/serial-20260922-014812.log`.
O runtime usou o QEMU in-tree com `reims-vgpu-pci`, `GUEST_MEMORY=false`,
`wm=none`, captura X11 e `QEMU_REBOOT_ACTION=reset`. Publicou o primeiro frame
do guest via residente e permaneceu 180 s até o timeout controlado, sem
`RESET`, `VK_ERROR_DEVICE_LOST` ou `vulkan_guest_reset` no artefato serial.

O evento `sampled_resident_admission_suspect` não apareceu. A hipótese de que
um residente ausente, não-pronto, com geração/geometria divergente ou
multisampling incompatível esteja sendo aceito no primeiro bind fica, portanto,
sem evidência neste cenário. A instrumentação permanece no PR #5 para capturar
o caso se ele surgir em outro ciclo; a causa dos glitches segue aberta no nível
de produção/consumo de conteúdo já válido ou no caminho Vulkan/QEMU posterior.

### A/B runtime #51 — importação direta do guest não é a correção

O braço repetiu a fixture limpa com a única mudança
`REIMS_VGPU_GUEST_IMPORT=on`. O guest chegou ao handoff do XNU, mas não
publicou o frame residente antes do timeout; o log Vulkan registrou
`vulkan_guest_reset resident=2 sampled=1 context=1` em `t=115361`, seguido de
`device_reset`. A tela permaneceu no logo da Apple após o reboot, como observado
na VM.

Esse resultado descarta a importação direta como solução dos glitches e mostra
que ela ainda piora a estabilidade do caminho atual. O perfil de trabalho volta
a ser `REIMS_VGPU_GUEST_IMPORT=off`; não houve alteração de código nem de disco
neste A/B.

### Runtime #52 — reset do guest após pressão de residentes, causa ainda inconclusiva

Foi iniciado um runtime controlado em `/home/felipeab10/Documentos/reims-t009-clean-sequoia-v2/validation-79ee/`
com `REIMS_VGPU_GUEST_IMPORT=off`, `REIMS_VGPU_SAMPLED_IDENTITY=off`,
`GUEST_MEMORY=false`, QEMU in-tree e `reims-vgpu-pci`. A execução apresentou o
primeiro frame e permaneceu aproximadamente 80 minutos sem texto de panic no
serial. Antes do reset, o census registrava `current=367/1525mib`,
`resident_samples=1560`, `resample_peak_ms=60782/2000` e `slab_mib=1750/2192`.

O evento final foi `vulkan_guest_reset resident=367 pooled_targets=0 sampled=109
storage=9 context=1`, seguido de `device_reset ... mappings=25 tasks=15
host_gva=5 frame_valid=1 frame_mapping=5 boundary=1 unmapped_views=17`. Isso é
o caminho de reset do dispositivo chamado pelo QEMU quando o guest reinicia;
não é, isoladamente, `VK_ERROR_DEVICE_LOST` nem prova de que a pressão de
residentes causou o reboot. Após o reset, o host-window caiu para
`host_window_cpu_fallback reason=slate_no_source` e os recursos foram liberados.

A VM foi encerrada depois do evento para preservar a evidência. O resultado
estreita o próximo diagnóstico para a correlação entre o reset/reboot do guest,
o último ciclo de apresentação e a pressão de residentes, mas não justifica
alterar reclaim, writeback ou barreiras sem uma captura QMP/serial do mesmo
evento. T009 continua `[-]`.

### Runtime #53 — captura visual correlacionada ao reset

Foi repetido o perfil seguro em `/home/felipeab10/Documentos/t009-clean-sequoia-v2/validation-79ee/`,
com o serial `components/reims-vgpu/vm/disks/run/serial-20260922-040115.log`.
Além do log Vulkan, foi capturada diretamente a janela X11 `Reims vGPU` pelo
window id `0x1000002`, sem capturar a área de trabalho do host. A imagem inicial
mostrou o logo da Apple; na amostra seguinte a janela ficou totalmente preta.

O intervalo correspondente no log é:

```text
registry_pressure current=447/2016mib ... resident_samples=2598 ... t=6088167
vulkan_guest_reset resident=447 pooled_targets=0 sampled=140 storage=9 context=1 t=6089016
device_reset id=1 seq=2 mappings=28 tasks=12 host_surface=2 host_texture=0 host_gva=13 host_linear=0 frame_valid=1 frame_mapping=4 boundary=1 unmapped_views=20 t=6089031
host_window_cpu_fallback reason=slate_no_source want=0x0 seen=absent t=6089034
```

Essa é a primeira correlação visual objetiva entre a perda do conteúdo exibido e
o reset do guest/dispositivo. O `device_reset` ocorre sem
`VK_ERROR_DEVICE_LOST`; portanto, a captura confirma o sintoma e a ordem dos
eventos, mas ainda não identifica se o reboot foi provocado pelo guest ou se
houve uma falha Vulkan anterior. O runtime foi encerrado imediatamente após o
evento, sem destruir os discos. T009 continua `[-]`.

Como experimento A/B derivado dessa evidência, o PR #5 passou a aceitar
`REIMS_VGPU_WINDOW_FORCE_CPU=on`. Essa chave não altera o padrão: apenas força o
presenter a ignorar o residente Vulkan e usar o `WindowCpuFrame` completo. Se a
imagem corrigir, a falha está no residente ou na transferência residente→janela;
se permanecer igual, a origem está antes desse ponto, no frame CPU/writeback.
O teste Vulkan/X11 do presenter passou (6 testes); a validação live ainda está
pendente.

### A/B runtime #54 — caminho CPU forçado não produz imagem

O build de `8e620f3a2a` foi executado com
`REIMS_VGPU_WINDOW_FORCE_CPU=on`, mantendo o restante do perfil seguro. A
captura `/tmp/reims-t009-force-cpu-current.png` mostrou apenas o slate escuro:
o Setup Assistant não apareceu. O runtime publicou alguns frames iniciais, mas
depois permaneceu em `same_key` com o caminho CPU forçado, sem recuperar uma
imagem completa. Esse resultado elimina o fallback CPU como correção direta e
confirma que o próximo diagnóstico deve preservar o residente Vulkan e
investigar como seus pixels são escritos/transferidos antes da publicação.

O runtime foi encerrado após a captura; os discos não foram alterados nem
destruídos.

Como próximo experimento isolado, o PR #5 também recebeu
`REIMS_VGPU_WINDOW_FORCE_COPY=on`. Em uma janela 1:1 essa chave mantém o
residente, mas troca `vkCmdBlitImage` por `vkCmdCopyImage`, removendo filtro e
transformação de viewport da apresentação. Os 6 testes do presenter passaram;
o A/B visual ainda precisa ser executado.

### A/B runtime #55 — cópia direta não altera o glitch

Com `REIMS_VGPU_WINDOW_FORCE_COPY=on`, a VM chegou ao mesmo Setup Assistant e
produziu a mesma corrupção estável na barra de rolagem e nos botões inferiores.
O caminho trocou o blit filtrado pela cópia direta 1:1, mas a captura
`/tmp/reims-t009-force-copy-20260922-0756.png` permaneceu visualmente igual ao
baseline. Isso elimina o filtro/viewport da apresentação como causa primária e
move o próximo diagnóstico para a escrita, sincronização ou formato do
residente antes do presenter.

O runtime foi encerrado após a captura, sem alteração destrutiva dos discos.

### A/B runtime #56 — identidade de amostra não corrige o frame

Foi repetida a mesma fixture com `REIMS_VGPU_GUEST_IMPORT=off`, mas com
`REIMS_VGPU_SAMPLED_IDENTITY=on` em vez do perfil seguro `off`. A captura
`/tmp/reims-t009-sampled-identity-on-0810.png` perdeu a lista inteira do Setup
Assistant, enquanto a corrupção dos botões inferiores permaneceu. Portanto o
cache de amostras por identidade não é uma correção; no perfil T009 ele deve
continuar desligado. O runtime foi encerrado após a captura, sem reset Vulkan
ou alteração destrutiva dos discos.

Também foi testado, apenas em modo diagnóstico e depois removido, forçar
re-sementeação de alvos GVA a partir da memória do guest. A faixa corrompida
aumentou e a barra/botões continuaram defeituosos. Isso descarta a falta de
semente GVA como explicação suficiente para esta tela. A evidência acumulada
agora localiza o defeito antes da apresentação, no conteúdo produzido por
draws/targets válidos; não há patch de produção justificado ainda.

### A/B runtime #57 — quebrar continuação de render pass não corrige o frame

Foi repetida a fixture com o perfil seguro e `REIMS_VGPU_PASS_CHURN=on`. Essa
chave já existente é diagnóstica: força o encerramento da continuação do render
pass e abre uma instância separada por draw, sem alterar a apresentação. O log
confirmou `render_pass_continuations=0`, mas a captura
`/tmp/reims-t009-pass-churn-on.png` manteve a mesma corrupção estável no
scrollbar e nos botões do Setup Assistant. A hipótese de continuação de render
pass, isoladamente, fica descartada; não foi criado patch de produção.

### A/B runtime #58 — o mesmo glitch aparece no console gráfico do QEMU

O mesmo `reims-vgpu-pci` foi executado com `REIMS_VGPU_WINDOW=0`, portanto sem
a janela Vulkan/winit do Reims e usando somente o display gráfico tradicional do
QEMU. A captura direta da janela QEMU `0x1200009`,
`/tmp/reims-t009-qemu-display-0821.png`, reproduziu visualmente o mesmo padrão:
o scrollbar e os botões inferiores já chegaram corrompidos ao
`DisplaySurface`. Isso elimina o presenter X11/winit, o blit/copy da janela e a
captura X11 como causa. O defeito está antes da apresentação, no conteúdo
Vulkan que o `reims-vgpu-pci` entrega ao console; o caminho `vmware-svga` segue
sendo apenas um controle do QEMU, pois não executa esse produtor Vulkan.

Os dois runtimes foram encerrados após as capturas, sem merge, sem alteração
destrutiva dos discos e sem alteração de código. T009 continua `[-]`.

### Runtime #59 — probe de conteúdo antes/depois do draw parcial

Foi adicionado ao PR #5 o probe diagnóstico `REIMS_VGPU_TARGET_CONTENT_PROBE=on`.
Ele permanece desligado por padrão e, somente para draws parciais que declaram
preservação, lê o residente antes do draw, força um readback depois e compara os
pixels fora do scissor após normalizar a ordem BGRA/RGBA. O build Vulkan/QEMU foi
reconstruído e executado na fixture limpa com `REIMS_VGPU_GUEST_IMPORT=off`,
`REIMS_VGPU_SAMPLED_IDENTITY=off`, `GUEST_MEMORY=false` e
`reims-vgpu-pci`; a janela X11 foi capturada em
`/tmp/reims-t009-target-probe-final.png`. Serial:
`components/reims-vgpu/vm/disks/run/serial-20260922-083719.log`.

As amostras registraram, entre outras, as seguintes linhas:

```text
target_content_probe ... size=848x897 scissor=0,0,45,44 ... changed_outside=0 changed_inside=552
target_content_probe ... size=1920x1080 scissor=918,310,84,84 ... changed_outside=0 changed_inside=7056
target_content_probe ... size=846x895 scissor=0,0,57,68 ... changed_outside=0 changed_inside=3368
```

O resultado é importante: o conteúdo fora da região escrita permanece idêntico
no residente antes/depois, enquanto a captura visual ainda mostra a corrupção
na interface. Isso reduz fortemente a hipótese de perda do LOAD, limpeza do
alvo ou sincronização que destrói a área preservada. O próximo alvo causal é a
produção dentro do scissor — coordenadas viewport/scissor, shader, blend ou
formato — e não o presenter X11/QEMU nem a preservação do frame anterior.
O probe foi mantido apenas como instrumentação no PR #5; não há patch de
produção justificado por este runtime. A VM foi encerrada após a captura e os
discos foram preservados. T009 continua `[-]`.

### Runtime #60 — geometria parcial e auditoria de texturas

O probe foi estendido com `geometry_probe`, condicionado ao mesmo
`REIMS_VGPU_TARGET_CONTENT_PROBE=on`, para registrar a geometria efetivamente
enviada a `vkCmdSetViewport`/`vkCmdSetScissor` nos draws parciais. As amostras
mostraram a transformação esperada: viewport full-target com Y invertido e
scissors dentro do alvo, por exemplo `848x898` com scissor `0,0,43,42` e
`1920x1080` com scissor `918,310,84,84`. Não houve retângulo negativo,
overflow ou deslocamento incompatível com o alvo.

Como controle separado, o runtime também usou
`REIMS_VGPU_GATHER_AUDIT_ALL=on`, mantendo `REIMS_VGPU_GUEST_IMPORT=off`. O
serial `components/reims-vgpu/vm/disks/run/serial-20260922-084720.log` registrou
auditorias `gw_audit_ok` e nenhuma falha de gather, mismatch de residente ou
recusa de textura amostrada. A captura continuou visualmente com o padrão de
corrupção nos elementos da interface.

Esse runtime reduz a hipótese de geometria viewport/scissor e de cópia RAM→
textura como causa primária. O próximo alvo é o conteúdo produzido dentro do
fragmento/pipeline ou os dados de textura que já chegam válidos ao shader. Os
probes foram publicados no PR #5, continuam desligados por padrão, e não houve
patch de produção nem alteração destrutiva dos discos. T009 continua `[-]`.
