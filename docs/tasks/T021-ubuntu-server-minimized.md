# T021 — Definir Ubuntu Server minimized e pacote mínimo

Status: `[ ]` não iniciada

## Objetivo

Congelar a base Ubuntu Server/minimized e o conjunto mínimo de pacotes necessários ao Reims OS.

## Requisitos

Incluir somente o necessário para:

- systemd;
- NetworkManager e suporte Ethernet/Wi-Fi;
- Xorg single-app;
- KVM/QEMU;
- Vulkan/Mesa e/ou driver suportado;
- áudio;
- Reims VGPU;
- Subiquity/instalação e recovery quando aplicável;
- updater e observabilidade.

Não incluir por padrão:

- GNOME/KDE/XFCE;
- Openbox/lxpanel;
- suíte de desktop de uso geral;
- serviços opcionais sem função no appliance.

## Evidência

- manifesto de pacotes versionado;
- tamanho da instalação base;
- boot funcional até sessão Reims;
- rede Ethernet e Wi-Fi funcionais;
- ausência de dependência transitiva que instale desktop completo.
