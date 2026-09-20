# T009 — Criar sessão gráfica dedicada single-app

Status: `[ ]` não iniciada

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
