# T022 — Customizar instalador TUI/Subiquity, rede obrigatória e branding Reims OS

Status: `[ ]` não iniciada

## Objetivo

Usar Ubuntu Server/Subiquity como engine do instalador, mantendo interface TUI leve e transformando o fluxo em uma instalação Reims OS.

## Fluxo obrigatório

```text
Boot ISO
→ Reims OS Setup
→ idioma/teclado
→ rede
   ├─ Ethernet/DHCP
   └─ Wi-Fi scan/SSID/senha
→ validar rota + DNS + HTTPS
→ disco
→ instalar Reims OS
```

## Requisitos de rede

- Internet é obrigatória na 0.1.0;
- não oferecer “continuar sem rede”;
- obter IP local não é prova suficiente;
- validar default route, DNS e HTTPS;
- Wi-Fi deve poder ser configurado no TUI quando hardware suportado estiver presente;
- falha deve permitir tentar novamente ou selecionar outra rede;
- credenciais Wi-Fi não podem aparecer em logs públicos.

## Branding

- nome visível: `Reims OS`;
- remover referências desnecessárias a “Ubuntu Server” da experiência do usuário;
- preservar derivação técnica correta, por exemplo `ID=reims`, `ID_LIKE=ubuntu`;
- customizar `/etc/os-release`, `/etc/issue`, boot/installer branding e demais superfícies pertinentes;
- respeitar licenças e avisos upstream.

## Simplificação do instalador

Não apresentar opções sem função no appliance, como desktop, Ubuntu Pro, snaps opcionais ou SSH quando não forem necessários.

## Critérios de aceitação

- Ethernet online permite prosseguir;
- Wi-Fi pode ser selecionado e autenticado no TUI;
- sem Internet o instalador bloqueia avanço;
- DNS quebrado e HTTPS indisponível são detectados;
- instalação final identifica-se visualmente como Reims OS;
- base continua tecnicamente rastreável como derivada de Ubuntu.
