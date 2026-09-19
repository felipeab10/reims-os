# Arquitetura — Reims OS 0.1.0

> Documento vivo. Mudanças arquiteturais relevantes devem ser refletidas aqui antes ou junto da implementação.

## 1. Objetivo

O **Reims OS** é uma distribuição Linux mínima que existe apenas para fornecer a infraestrutura necessária para executar macOS x86_64 sobre KVM/QEMU com `reims-vgpu`.

A experiência desejada é a de uma máquina dedicada ao macOS:

```text
Power on
  ↓
Linux mínimo
  ↓
Inicialização gráfica discreta
  ↓
Atualização/validação do Reims, quando necessária
  ↓
QEMU + KVM + Reims VGPU
  ↓
OpenCore
  ↓
macOS em tela cheia
```

O Linux é a infraestrutura do appliance, não o ambiente de uso principal.

## 2. Escopo da versão 0.1.0

A versão 0.1.0 suporta somente:

- macOS Ventura 13;
- macOS Sonoma 14;
- macOS Sequoia 15.

Tahoe e versões anteriores ficam fora do escopo da 0.1.0.

A base Linux será inicialmente Ubuntu LTS em instalação mínima. A ISO deve permitir que o usuário faça a instalação normal oferecida pela distribuição base. A customização do Reims OS entra no primeiro boot do sistema instalado.

## 3. Princípios arquiteturais

### 3.1 Linux invisível durante o uso normal

Após a instalação do Linux, o usuário não deve precisar abrir terminal, desktop Linux ou iniciar manualmente QEMU/Reims.

### 3.2 Uma única VM principal

A 0.1.0 trabalha com uma única instalação macOS principal por host.

O usuário não escolhe nome de VM. Um identificador interno aleatório é gerado uma única vez, por exemplo:

```text
reims-7c91a243
```

Esse identificador não faz parte da experiência normal do usuário.

### 3.3 Reims sempre ativo

O fluxo de produto não pergunta se o usuário deseja iniciar com Reims. `reims-vgpu-pci` é o caminho gráfico padrão tanto no instalador quanto nos boots normais.

Modos sem Reims continuam possíveis para desenvolvimento e diagnóstico, mas não fazem parte do fluxo principal do appliance.

### 3.4 Persistência real de uso diário

O modo de uso normal não deve depender de clones descartáveis ou da promoção manual de snapshots.

Será introduzido um modo persistente no launcher, conceitualmente:

```text
vm/boot-x86.sh --persistent
```

Nesse modo, QEMU abre os discos persistentes diretamente em leitura/escrita:

```text
/var/lib/reims/vms/<vm-id>/
├── installer/
├── persistent/
│   ├── macos.qcow2
│   ├── OpenCore.qcow2
│   ├── OVMF_CODE.fd
│   └── OVMF_VARS.fd
├── run/
├── serial/
└── serial-work/
```

Alterações feitas dentro do macOS são persistidas continuamente no disco virtual. Não é necessário criar um novo snapshot a cada desligamento.

O sistema atual de rails/snapshots deve ser preservado para desenvolvimento, testes, recuperação e rollback.

## Decisão de repositórios e dependências

O `reims-os` é o produto/appliance e `reims-vgpu` é seu componente de virtualização. `OSX-KVM` e `osx-serial-generator` são dependências upstream pinadas. Releases são definidas pela combinação dos SHAs registrados nos submodules; atualizações só entram após validação e commit do novo ponteiro.

## 4. Fluxo de instalação

### 4.1 Live Linux

```text
Boot da ISO
  ↓
Instalador normal da distribuição base
  ↓
Usuário escolhe idioma, teclado, disco, usuário e rede
  ↓
Instalação do Linux
  ↓
Reboot
```

A 0.1.0 não terá instalador de Linux próprio.

### 4.2 Primeiro boot

Se ainda não existir uma configuração válida em `/var/lib/reims/state.json`, o sistema inicia automaticamente o wizard de instalação do macOS.

O wizard apresenta somente:

1. versão do macOS:
   - Ventura;
   - Sonoma;
   - Sequoia;
2. quantidade de CPU;
3. quantidade de RAM;
4. tamanho do disco, mínimo 70 GiB.

Não apresentar ao usuário:

- nome da VM;
- rail;
- snapshot;
- backend Vulkan;
- OpenCore;
- OVMF;
- SMBIOS;
- serial;
- opção para habilitar/desabilitar Reims.

O sistema gera automaticamente:

- ID interno da VM;
- identidade única do OpenCore/SMBIOS;
- serial/MLB/ROM/SystemUUID;
- OpenCore próprio;
- disco principal;
- OVMF_VARS persistente;
- configuração da VM.

O fluxo atual de `scripts/reims-vm-manager.sh` deve ser simplificado, reaproveitando o download via OSX-KVM, validação de chunklist, criação das imagens e geração da identidade.

### 4.3 Contrato de progresso do provisionamento

O provisionador deve separar saída técnica de estado apresentado ao usuário.

Cada operação longa deve poder publicar eventos estruturados equivalentes a:

```text
phase
label
state
current
total
percent
started_at
elapsed_seconds
message
```

`current/total/percent` são opcionais e só devem existir quando a operação possui progresso real mensurável. Builds ou operações sem unidade confiável usam estado indeterminado.

As fases mínimas previstas incluem:

```text
preflight
download
verify
convert
create_disk
generate_identity
build_opencore
prepare_firmware
launch_installer
```

A UI do first boot consome esses eventos e apresenta uma única experiência contínua de instalação. Logs técnicos completos continuam sendo gravados separadamente para diagnóstico.

### 4.4 OpenCore e seleção automática do sistema

O OpenCore da VM é parte do estado persistente da máquina e deve ser personalizado por instalação. A imagem compartilhada do projeto é apenas uma fonte/base; o appliance nunca deve depender de um `config.plist` gerado que não tenha sido efetivamente instalado dentro do `OpenCore.qcow2` da VM.

Durante `state=installing`, o OpenCore precisa continuar descobrindo e permitindo os estágios transitórios criados pelo instalador do macOS, como Recovery, `macOS Installer` e Preboot. A seleção padrão não deve ser fixada cedo demais.

Depois que a VM alcançar um macOS instalado e utilizável, a seleção padrão deve persistir para o volume principal do macOS. O boot normal desejado é:

```text
OpenCore
  ↓
descobre volumes APFS
  ↓
volume macOS instalado = padrão persistente
  ↓
timeout
  ↓
boot automático
```

A configuração deve permitir persistência da seleção padrão (incluindo `AllowSetDefault` e roteamento de variáveis de boot do OpenCore quando aplicável), sem remover a possibilidade de acessar picker/Recovery em recuperação.

Na experiência normal pós-instalação, o usuário não deve precisar selecionar manualmente `Macintosh HD`/volume equivalente a cada boot.

### 4.5 Polimento de boot nativo — somente após validação funcional

Depois que persistência, instalação, autoboot, fullscreen, lifecycle, atualização e matriz Ventura/Sonoma/Sequoia estiverem validados, será feita uma etapa separada de polimento para aproximar a experiência visual/sonora de um Mac nativo.

Essa etapa pode incluir ocultar o picker do OpenCore no boot normal, reduzir/remover elementos visuais intermediários, usar o chime de inicialização suportado pela configuração OpenCore e manter um mecanismo de recuperação para tornar o picker visível quando necessário.

Esse polimento não deve ser usado para mascarar problemas durante o desenvolvimento. Enquanto a plataforma ainda estiver sendo validada, o picker e logs permanecem visíveis quando forem úteis ao diagnóstico.

## 5. Boot normal

Depois que a instalação está configurada:

```text
UEFI/firmware
  ↓
Linux kernel + systemd
  ↓
Plymouth/tela de boot
  ↓
Rede mínima
  ↓
reims-update.service
  ↓
reims-session.service
  ↓
compositor Wayland mínimo
  ↓
reims-appliance.service
  ↓
QEMU persistent
  ↓
Reims fullscreen
  ↓
OpenCore
  ↓
macOS
```

O Linux não deve expor um desktop tradicional no caminho normal.

## 6. Janela gráfica

O caminho de produto utiliza a janela própria do Reims:

```text
REIMS_VGPU_WINDOW=1
```

Com Reims ativo, QEMU pode continuar usando `-display none` enquanto a janela Vulkan do Reims apresenta o guest.

Será adicionada uma configuração explícita de fullscreen, preferencialmente implementada dentro da criação da janela Reims, por exemplo:

```text
REIMS_VGPU_FULLSCREEN=1
```

A 0.1.0 não deve depender de automações frágeis como `xdotool`, `wmctrl` ou atalhos manuais para entrar em tela cheia.

## 7. Compositor

A 0.1.0 mantém um compositor Wayland mínimo no host.

Não faz parte do primeiro release remover completamente Wayland/compositor e apresentar diretamente via DRM/KMS. Saída DRM/KMS direta pode ser estudada em versões futuras.

## 8. Lifecycle do macOS e do host

Um supervisor do appliance será responsável por observar QMP, serial e o processo QEMU.

### 8.1 Política de reboot por fase

O appliance possui fases distintas e o mesmo evento de reboot do guest não pode produzir a mesma ação em todas elas.

Durante `installing`, reinicializações do macOS são parte normal do instalador. O QEMU deve permanecer ativo e resetar o guest no mesmo processo/janela, preservando os mesmos discos persistentes. O caminho esperado é usar a política equivalente a:

```text
QEMU_REBOOT_ACTION=reset
```

Nessa fase, um reboot do guest **não** deve reiniciar o host Linux e não deve exigir relançamento manual da VM.

Depois que o estado for `installed`, um Restart solicitado pelo macOS passa a ser um evento de lifecycle do appliance. O supervisor deve distinguir reboot normal de kernel panic/crash e somente então T007 poderá reiniciar o host Linux.

Portanto:

```text
state=installing + guest reboot
→ QEMU permanece vivo
→ guest reseta
→ instalação continua

state=installed + GUEST_REBOOT confirmado
→ supervisor persiste logs
→ host Linux reinicia
```

O fechamento da janela/QEMU durante cada reboot do instalador não faz parte da experiência final esperada.

### 8.2 Shutdown normal do macOS

```text
macOS solicita shutdown
  ↓
QMP/estado confirma desligamento normal
  ↓
QEMU termina limpo
  ↓
systemctl poweroff
```

### 8.3 Restart normal do macOS

```text
macOS solicita restart
  ↓
QMP confirma reset/reboot normal
  ↓
supervisor finaliza a sessão
  ↓
systemctl reboot
```

### 8.4 Falha não deve desligar/reiniciar o host automaticamente

Os seguintes eventos não podem ser tratados como reboot/shutdown normal:

- crash do QEMU;
- crash do Reims;
- Vulkan device lost;
- kernel panic do guest;
- erro fatal de build/runtime;
- encerramento por sinal externo inesperado.

Nesses casos o sistema entra em fluxo de recuperação, preservando logs.

## 9. Persistência e snapshots

### 9.1 Uso normal

Disco persistentemente gravável.

### 9.2 Desenvolvimento e testes

Continuam usando a infraestrutura atual de rails/snapshots, incluindo `--testing`, `--interactive` e `--capture`.

### 9.3 Recovery

Snapshots passam a ser ferramentas de:

- backup;
- rollback;
- testes controlados;
- atualização de baixo risco;
- recuperação de instalação.

Não são o mecanismo obrigatório de persistência diária.

## 10. Layout do appliance

Código do produto:

```text
/opt/reims/
├── releases/
│   ├── <git-sha-A>/
│   └── <git-sha-B>/
├── current -> releases/<git-sha-atual>
└── previous -> releases/<git-sha-anterior>
```

Estado persistente do usuário:

```text
/var/lib/reims/
├── state.json
├── update-state.json
└── vms/
    └── <vm-id>/
```

Logs:

```text
/var/log/reims/
└── boot-YYYYMMDD-HHMMSS/
    ├── manifest.txt
    ├── lifecycle.log
    ├── update.log
    ├── qemu.log
    ├── serial.log
    └── vulkan.txt
```

O update do código nunca deve apagar ou substituir `/var/lib/reims`.

## 11. Estrutura proposta no repositório

```text
appliance/
├── VERSION
├── distro/
│   ├── packages.txt
│   ├── build-iso.sh
│   ├── overlay/
│   ├── plymouth/
│   └── installer/
├── systemd/
│   ├── reims-firstboot.service
│   ├── reims-update.service
│   ├── reims-session.service
│   ├── reims-appliance.service
│   └── reims-recovery.service
├── scripts/
│   ├── reims-firstboot
│   ├── reims-update
│   ├── reims-launch
│   ├── reims-supervisor
│   ├── reims-recovery
│   └── reims-version
├── config/
│   └── defaults.toml
└── tests/
    ├── smoke/
    ├── install/
    ├── update/
    └── lifecycle/
```

Essa estrutura pode evoluir, mas os limites entre código do appliance, estado persistente e árvore de desenvolvimento devem ser mantidos.

## 12. Atualizações do fork

A origem principal do Reims OS é:

```text
https://github.com/felipeab10/reims-vgpu
branch: master
```

O appliance verifica a master automaticamente antes de iniciar o macOS, desde que haja conectividade.

A atualização deve ser transacional:

```text
remote SHA == installed SHA
  ├─ sim → inicia macOS
  └─ não
      ↓
    baixa nova release
      ↓
    atualiza submodules
      ↓
    build Reims/QEMU
      ↓
    testes/preflight
      ↓
    sucesso?
      ├─ sim → troca symlink current atomicamente
      └─ não → mantém release conhecida como boa
```

Nunca executar um `git pull && rebuild` destrutivo diretamente sobre a release em produção.

## 13. Atualizações do Linux

Atualização do fork e atualização do sistema base são canais diferentes.

A versão 0.1.0 não deve executar upgrade indiscriminado de kernel, Mesa, NVIDIA, Vulkan, systemd ou compositor a cada boot.

Esses componentes formam uma plataforma validada e versionada. Mudanças nessa plataforma devem gerar uma nova release do Reims OS.

## 14. Versionamento

Arquivo sugerido:

```text
/etc/reims-release
```

Exemplo:

```ini
REIMS_OS_VERSION=0.1.0
BASE_ID=ubuntu
BASE_VERSION=<versão validada>
CHANNEL=stable
REIMS_REPO=felipeab10/reims-vgpu
REIMS_BRANCH=master
REIMS_COMMIT=<sha>
QEMU_COMMIT=<sha>
OSX_KVM_COMMIT=<sha>
KERNEL=<versão>
MESA=<versão>
NVIDIA=<versão>
```

Cada boot deve registrar um manifesto equivalente junto dos logs.

## 15. Tela de atualização

Durante atualização/build, o usuário deve ver uma tela simples, sem console técnico por padrão:

```text
Reims OS

Atualizando componentes...
Por favor, aguarde.
```

O Plymouth é o candidato inicial para a 0.1.0.

Em caso de erro, o updater deve manter a última release conhecida como boa e continuar o boot do macOS sempre que for seguro fazê-lo.

## 16. Ordem de implementação da 0.1.0

A ordem arquitetural é:

1. modo persistente no `boot-x86.sh`;
2. simplificação do `reims-vm-manager.sh`;
3. fullscreen nativo no Reims;
4. supervisor de lifecycle;
5. serviços systemd e auto-boot;
6. updater transacional;
7. tela de boot/update;
8. geração da ISO mínima;
9. testes de instalação e atualização end-to-end;
10. release 0.1.0.

A ISO não deve ser o primeiro passo: primeiro validamos toda a experiência do appliance em um Linux de desenvolvimento conhecido.