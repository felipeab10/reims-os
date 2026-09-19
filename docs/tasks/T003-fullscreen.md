# T003 — Implementar fullscreen nativo obrigatório

Status: `[x]` concluída e validada

Dependência: **T001** e integração básica de **T002**.

## Objetivo

Garantir que a janela própria do Reims abra automaticamente em tela cheia no fluxo do appliance, tanto durante a instalação do macOS quanto nos boots normais.

## Resultado esperado

O usuário não deve precisar usar atalhos, clicar em controles de janela ou interagir com o compositor Linux para colocar o macOS em fullscreen.

## Escopo

- adicionar uma configuração explícita de fullscreen no caminho da janela host do Reims;
- manter `REIMS_VGPU_WINDOW=1` como caminho normal do appliance;
- manter QEMU sem janela própria no caminho Reims, usando o comportamento existente de `-display none`;
- garantir fullscreen desde a abertura inicial da janela;
- preservar um escape/recovery técnico documentado para desenvolvimento;
- funcionar no compositor Wayland usado na fase de desenvolvimento e ser compatível com o compositor mínimo futuro.

## Fora de escopo

- remover Wayland/compositor;
- DRM/KMS direto;
- resolução dinâmica avançada;
- multi-monitor;
- seleção gráfica pelo usuário;
- criação da sessão gráfica mínima, tratada em T009.

## Requisitos de implementação

1. Criar uma configuração de produto explícita, preferencialmente `REIMS_VGPU_FULLSCREEN=1`, ou outra interface igualmente clara se o código real exigir.
2. A decisão de fullscreen deve acontecer no código que cria/controla a janela Reims, não por `xdotool`, `wmctrl` ou automação de teclado.
3. O modo deve respeitar semântica de presença/booleano consistente com as demais variáveis Reims.
4. Fullscreen deve ser solicitado antes da primeira apresentação útil, evitando flash prolongado de uma janela normal quando possível.
5. O caminho sem fullscreen deve continuar disponível para desenvolvimento/diagnóstico.
6. O appliance deve ativar fullscreen automaticamente; o usuário não deve ser perguntado.
7. Não alterar comportamento gráfico de backend, swapchain, guest import ou refresh rate nesta task.
8. Não introduzir dependência em X11 como requisito do produto.

## Critérios de aceitação

### Estático

- `cargo check --package reims-vgpu --no-default-features --features backend-vulkan,host-window` passa;
- configuração fullscreen está documentada;
- não há uso novo de `xdotool`, `wmctrl` ou simulação de atalhos para obter fullscreen.

### Funcional

Em host de desenvolvimento conhecido:

1. iniciar uma VM com Reims e fullscreen habilitado;
2. confirmar que a janela abre em fullscreen automaticamente;
3. confirmar que o framebuffer guest ocupa a superfície esperada sem depender de ação manual;
4. reiniciar a VM e confirmar repetibilidade;
5. iniciar uma vez com fullscreen explicitamente desabilitado e confirmar que o modo de desenvolvimento continua disponível.

### Regressão

- input de teclado continua funcionando;
- input absoluto do mouse/tablet continua funcionando;
- janela continua apresentando frames;
- não criar nova regressão conhecida de boot/presentação.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- arquivos alterados;
- API/configuração final de fullscreen;
- compositor e sessão usados no teste;
- comandos de build/check;
- evidência de boot fullscreen automático em pelo menos duas execuções;
- resultado do teste com fullscreen desabilitado.

## API e integração atual

- `REIMS_VGPU_FULLSCREEN=1`: a janela host existente solicita `winit::window::Fullscreen::Borderless(None)` antes de `create_window()`.
- `REIMS_VGPU_FULLSCREEN=0`: mantém o modo `WindowMode::Sized` para desenvolvimento.
- `--persistent`: o launcher exporta `REIMS_VGPU_FULLSCREEN=1` somente quando a variável não estava presente; `0`, `1` e até valor vazio explicitamente fornecidos pelo operador são preservados.
- `--testing`, `--interactive` e `--capture`: não recebem fullscreen automático.

## Validação final

- implementação: `dd6ba80e9c2588b9e79dfffddced6a47b1a349ca`;
- PR: #3;
- merge em `master`: `6b517cdb62fc6fd62c4459a7dd67401b62ace5d1`;
- host de validação: Wayland + niri;
- `cargo check --package reims-vgpu --no-default-features --features backend-vulkan,host-window`: PASS;
- testes host-window: 50 passed, 0 failed;
- regressão T002: PASS;
- boot persistente 1: fullscreen automático, `REIMS_VGPU_FULLSCREEN=1`, QEMU `-display none`: PASS;
- boot persistente 2: fullscreen automático repetível: PASS;
- override `REIMS_VGPU_FULLSCREEN=0`: modo windowed/sized: PASS;
- apresentação: primeiro frame e primeiro guest frame via rail resident: PASS;
- nenhum workaround externo de fullscreen foi usado.

A indisponibilidade de SSH observada durante essa rodada foi classificada separadamente como problema não pertencente à T003. O caminho de input não foi alterado por esta task e os testes existentes de host-window permaneceram passando.

## Histórico

T003 concluída após revisão remota da PR #3 e validação runtime do fullscreen automático e do override windowed.
