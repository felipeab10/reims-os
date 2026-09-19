# Requisitos — Reims OS 0.1.0

> Documento vivo. Este arquivo define o contrato funcional e técnico da versão 0.1.0.

## 1. Escopo suportado

A versão 0.1.0 deve suportar somente:

- macOS Ventura 13;
- macOS Sonoma 14;
- macOS Sequoia 15.

Ficam fora do escopo da 0.1.0:

- macOS Tahoe;
- versões anteriores ao Ventura;
- múltiplas VMs simultâneas;
- passthrough de GPU física;
- apresentação direta por DRM/KMS sem compositor;
- instalador Linux próprio.

## 2. Base Linux

- Base inicial: Ubuntu LTS em instalação mínima.
- O usuário instala o Linux usando o instalador normal da distribuição base.
- Após o primeiro reboot, o Reims OS assume o fluxo.
- O Linux não deve expor um desktop tradicional no uso normal.
- O host deve manter apenas os componentes necessários para KVM/QEMU/Reims, rede, áudio, Vulkan, compositor mínimo, atualização e recuperação.

## 3. Primeiro boot

Se `/var/lib/reims/state.json` não existir ou indicar sistema não configurado, iniciar automaticamente o wizard de instalação.

O wizard deve solicitar somente:

- versão do macOS: Ventura, Sonoma ou Sequoia;
- número de CPUs;
- memória RAM;
- tamanho do disco, mínimo 70 GiB.

O wizard não deve solicitar:

- nome da VM;
- SMBIOS;
- serial;
- rail;
- snapshot;
- backend gráfico;
- OpenCore;
- OVMF;
- confirmação para iniciar Reims.

O nome interno da VM deve ser gerado automaticamente e persistido.

## 4. Instalação do macOS

O fluxo deve reaproveitar o `scripts/reims-vm-manager.sh` e a integração já existente com OSX-KVM.

Deve:

- baixar a versão selecionada;
- validar o chunklist Apple;
- preparar a mídia;
- criar disco virtual;
- gerar identidade OpenCore única;
- criar OpenCore próprio;
- criar OVMF_VARS persistente;
- iniciar automaticamente com `reims-vgpu-pci`;
- entrar em fullscreen automaticamente;
- durante a instalação, permitir que OpenCore encontre as entradas temporárias do instalador e continue os reboots sem intervenção;
- após a instalação estar utilizável, iniciar automaticamente o volume macOS instalado como entrada padrão do OpenCore, sem exigir seleção manual a cada boot;
- manter uma forma de acessar o picker/Recovery para recuperação, mesmo quando o boot normal for automático.

### 4.1 Progresso de instalação

O provisionamento não deve expor logs técnicos, output de build, `guestfish`, `dmg2img`, `qemu-img`, Cargo ou detalhes internos ao usuário final.

Durante operações demoradas, a interface deve exibir progresso claro, no mínimo:

- etapa atual em linguagem amigável;
- barra de progresso quando houver métrica real;
- tempo decorrido desde o início da instalação;
- indicação de atividade quando a etapa não tiver percentual confiável;
- erro resumido e acionável em caso de falha.

Exemplo:

```text
Preparando o macOS

Baixando o instalador              100%
Validando arquivos                 100%
Preparando mídia                    72%
Configurando máquina virtual        40%

Progresso geral                     58%
Tempo decorrido                  12:47
```

Percentuais não devem ser inventados. Etapas sem progresso mensurável devem usar estado indeterminado e continuar mostrando o tempo decorrido.

O backend do provisionamento deve emitir estado/progresso estruturado para que a UI possa renderizar essa experiência sem depender de parsing frágil de stdout.

### 4.2 Contrato OpenCore

Cada VM deve possuir seu próprio `OpenCore.qcow2` e seu próprio `config.plist` efetivamente instalado dentro da partição EFI dessa imagem.

Não basta gerar um `config.plist` fora do qcow2: a validação deve montar/inspecionar a imagem final e comprovar que `EFI/OC/config.plist` contém a identidade e as opções esperadas.

O contrato mínimo para a 0.1.0 inclui:

- enumeração das partições APFS/macOS pelo OpenCore;
- `Misc -> Security -> AllowSetDefault = true`;
- `UEFI -> Quirks -> RequestBootVarRouting = true` quando suportado pela configuração base utilizada;
- política de scan que permita localizar os volumes macOS necessários;
- timeout de boot automático;
- durante `installing`, não fixar prematuramente o volume final de modo a impedir os estágios `macOS Installer`/Preboot;
- após `installed`, o volume principal macOS deve ser a seleção padrão persistente.

O objetivo de produto é:

```text
instalação
→ OpenCore pode alternar entre Recovery / macOS Installer / Preboot

instalação concluída
→ OpenCore reconhece o macOS instalado
→ seleção padrão persistida
→ timeout
→ macOS inicia automaticamente
```

## 5. Persistência

O uso diário deve ser persistente sem depender de promoção de snapshot a cada shutdown.

Requisito principal:

- criar um modo persistente no launcher, conceitualmente `--persistent`;
- abrir `macos.qcow2`, `OpenCore.qcow2` e `OVMF_VARS.fd` diretamente em leitura/escrita;
- preservar todas as alterações do guest após reboot ou shutdown.

O sistema atual de snapshots/rails deve continuar disponível para desenvolvimento, testes, recovery e rollback.

## 6. Reims VGPU

- `reims-vgpu-pci` é obrigatório no fluxo principal do produto.
- `REIMS_VGPU_WINDOW=1` deve ser usado no caminho normal.
- deve existir fullscreen nativo e automático;
- o usuário não deve precisar pressionar atalhos ou interagir com o compositor Linux para colocar a VM em tela cheia.

## 7. Lifecycle

Deve existir um supervisor que observe QMP, serial e o processo QEMU.

### Shutdown normal

Quando o macOS desligar normalmente:

- garantir flush/encerramento limpo do QEMU;
- desligar o host Linux.

### Reboot normal

Quando o macOS reiniciar normalmente:

- reiniciar o host Linux.

### Erros

Não desligar/reiniciar automaticamente o host em caso de:

- kernel panic do guest;
- crash do QEMU;
- crash do Reims;
- Vulkan device lost;
- encerramento por sinal externo inesperado;
- erro de atualização/build.

Nesses casos preservar logs e entrar em fluxo de recuperação.

## 8. Atualização do fork

Origem principal:

```text
https://github.com/felipeab10/reims-vgpu
branch: master
```

O sistema deve verificar atualizações automaticamente antes de iniciar o macOS, quando houver rede.

A atualização deve ser transacional:

- buscar novo SHA;
- preparar nova release separada;
- atualizar submodules;
- buildar Reims e QEMU;
- executar testes/preflight;
- só então trocar a release ativa atomicamente;
- manter a release anterior para rollback;
- em falha, continuar usando a última release conhecida como boa.

É proibido atualizar destrutivamente a release em uso com `git pull && rebuild` in-place.

## 9. Atualização do Linux

Atualização do fork e atualização do sistema base são canais diferentes.

Na 0.1.0 não executar upgrade indiscriminado a cada boot de:

- kernel;
- NVIDIA;
- Mesa;
- Vulkan loader;
- systemd;
- compositor;
- toolchain.

Esses componentes devem ser versionados e validados como parte de uma release do Reims OS.

## 10. Tela de boot e atualização

Durante boot e update o usuário deve ver uma experiência simples, por exemplo:

```text
Reims OS

Atualizando componentes...
Por favor, aguarde.
```

A primeira implementação pode usar Plymouth.

## 11. Observabilidade

Cada boot deve registrar pelo menos:

- versão do Reims OS;
- SHA do repositório Reims;
- SHA do QEMU submodule;
- SHA do OSX-KVM usado;
- kernel;
- driver NVIDIA ou Mesa;
- GPU/Vulkan selecionada;
- command line QEMU;
- eventos de lifecycle;
- serial do guest;
- resultado da atualização.

Logs devem ser persistentes em `/var/log/reims/`.

## 12. Estado persistente

O estado da instalação deve ficar fora da árvore Git, por exemplo:

```text
/var/lib/reims/state.json
/var/lib/reims/vms/<vm-id>/
```

Atualizações do código não podem apagar nem sobrescrever esse estado.

## 13. Testabilidade

Toda funcionalidade relevante deve possuir teste controlado quando possível.

A 0.1.0 deve validar, para Ventura/Sonoma/Sequoia:

- installer abre;
- instalação completa;
- reboot durante instalação;
- Setup Assistant;
- persistência após reboot;
- persistência após shutdown;
- fullscreen automático;
- teclado e mouse;
- áudio;
- rede;
- shutdown macOS → host off;
- reboot macOS → host reboot;
- update do Reims;
- update quebrado → rollback;
- uso idle prolongado;
- uso prolongado sem regressão grave.

## 14. Critério de conclusão 0.1.0

A versão 0.1.0 só pode ser considerada pronta quando:

- todos os requisitos obrigatórios deste documento estiverem implementados ou explicitamente marcados como adiados para versão futura;
- as tasks críticas estiverem concluídas;
- a matriz Ventura/Sonoma/Sequoia estiver validada;
- houver rollback de atualização funcional;
- o sistema puder ser instalado do zero e usado sem depender de terminal Linux no fluxo normal.