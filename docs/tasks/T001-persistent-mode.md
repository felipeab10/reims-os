# T001 — Implementar modo persistente no launcher

Status: `[x]` concluída e validada

## Objetivo

Adicionar ao fluxo x86 um modo de uso diário que grave diretamente os discos persistentes da VM, sem clone descartável e sem promoção obrigatória de snapshot no shutdown.

## Motivação

Os modos atuais (`--testing`, `--interactive`, `--capture`) foram projetados para desenvolvimento e snapshots imutáveis. O appliance precisa comportar-se como uma máquina normal: alterações feitas no macOS devem permanecer após reboot e shutdown.

## Escopo

Adicionar uma nova classe de boot, conceitualmente:

```bash
vm/boot-x86.sh --persistent
```

Quando usada:

- `macos.qcow2` deve ser aberto diretamente read/write;
- `OpenCore.qcow2` deve ser persistente;
- `OVMF_VARS.fd` deve ser persistente;
- não criar clone temporário para ser descartado;
- não promover snapshot ao final;
- manter QMP e logs;
- preservar os modos existentes sem regressão.

## Fora de escopo

- supervisor de lifecycle do host;
- fullscreen;
- updater;
- ISO;
- mudanças na semântica dos modos existentes.

## Requisitos de implementação

1. Atualizar `usage()` e documentação inline do `vm/boot-x86.sh`.
2. Resolver de forma explícita os paths persistentes usados pelo modo.
3. Evitar qualquer chamada a `discard_clone` no caminho persistente.
4. Não alterar snapshots históricos.
5. Não escrever diretamente em um snapshot marcado como imutável.
6. O modo deve falhar cedo se os arquivos persistentes necessários não existirem.
7. O shutdown limpo do QEMU deve deixar os arquivos intactos e reutilizáveis.
8. QMP e serial/logs devem continuar disponíveis.

## Critérios de aceitação

### Estático

- `bash -n vm/boot-x86.sh` passa.
- Help mostra `--persistent`.
- Modos existentes continuam aceitos.

### Funcional

Em uma VM de teste dedicada:

1. boot em `--persistent`;
2. criar um marcador dentro do guest;
3. shutdown limpo;
4. iniciar novamente em `--persistent`;
5. marcador continua presente.

Repetir com reboot.

### Segurança

- snapshots existentes não são modificados;
- golden/control existentes não são alterados;
- nenhum `qemu-img commit` destrutivo;
- nenhum broad `pkill`.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- arquivos alterados;
- comandos de teste;
- resultados;
- paths dos discos usados no teste;
- confirmação de persistência após shutdown e reboot.

## Implementação em revisão

Branch:

```text
feat/t001-persistent-mode
```

Commit inicial:

```text
311435ce873666f01284cd36b94ad182b58b819a
```

Commit de correção da revisão:

```text
bb171c33dbee75ab01453173afae9422552a2343
```

Arquivo de código alterado:

```text
vm/boot-x86.sh
```

### Revisão 1 — CHANGES_REQUESTED

Foram encontrados quatro pontos:

- estado duplicado `BOOT_CLASS` x `IS_PERSISTENT`;
- combinação `--persistent --snapshot LABEL` ambígua;
- ausência de validação de writability;
- necessidade de preservar o par `OVMF_CODE.fd`/`OVMF_VARS.fd`.

### Revisão 2 — APPROVED_PENDING_RUNTIME_VALIDATION

O commit `bb171c33dbee75ab01453173afae9422552a2343` corrige os pontos da revisão anterior:

- `BOOT_CLASS` passou a ser a única fonte de verdade;
- o comportamento persistent é derivado de `BOOT_CLASS=persistent`;
- combinações de classes preservam a semântica de “última classe vence”;
- `--persistent --snapshot LABEL` é rejeitado com erro;
- `--list-snapshots` é resolvido antes do caminho persistent e continua saindo sem boot;
- `PERSISTENT_DIR`, `macos.qcow2`, `OpenCore.qcow2` e `OVMF_VARS.fd` são validados como graváveis;
- `PERSISTENT_DIR/OVMF_CODE.fd` é usado quando presente e não há override explícito de `OVMF_CODE`;
- o caminho persistent continua sem `discard_clone` e sem `promote_to_snapshot`.

A revisão de código está aprovada. A task ainda não está concluída porque os critérios funcionais de persistência exigem boot real.

## Runtime recovery/preflight

Ambiente preparado em worktree separado:

```text
<runtime-root>
```

Superproject:

```text
bb171c33dbee75ab01453173afae9422552a2343
```

QEMU submodule:

```text
bd88218da09b86ed9c78bf5f9354168812a7ba6b
```

QEMU:

```text
QEMU emulator version 11.0.50
SHA256=e81ab010180f6c0a9d3bb9c45153688b0a49e622314a21a4acbe27ab332d3f32
```

Build oficial executado com sucesso:

```bash
REIMS_VGPU_BACKEND=vulkan \
scripts/qemu-build/qemu-build.sh \
  --target x86_64 \
  --backend vulkan
```

Sanity checks:

- `qemu-system-x86_64 --version` — PASS;
- `-machine help` — PASS;
- `-device help` — PASS;
- `reims-vgpu-pci` — presente;
- `vmware-svga` — presente.

Os submodules em `vendor/qemu/roms/*` ficaram dirty apenas por artefatos do build local; nenhuma alteração de código do superproject foi feita.

### Tentativa runtime 1 — BLOCKED

Fixture dedicada:

```text
<t001-fixtures>/sequoia
```

Persistent storage:

```text
<t001-fixtures>/sequoia/persistent
```

Resultado observado:

- download e conversão do instalador Sequoia concluídos;
- disco qcow2 de 80 GiB criado;
- OpenCore e OVMF dedicados criados;
- boot com `--persistent --device reims-vgpu-pci` iniciado;
- instalador e telas de progresso foram observados;
- aproximadamente 11,7 GiB foram gravados no disco persistente;
- os mesmos paths `macos.qcow2`, `OpenCore.qcow2` e `OVMF_VARS.fd` foram reutilizados entre boots;
- QMP funcionou;
- serial funcionou e registrou handoff para XNU;
- snapshots históricos permaneceram intocados;
- Setup Assistant/desktop ainda não foi alcançado.

A solicitação `system_powerdown` via QMP durante o estado de instalação não encerrou o guest no intervalo observado. O QEMU foi posteriormente parado para não deixar a VM ativa. Por isso não existe evidência suficiente para validar persistência após shutdown ou reboot.

Resultado desta rodada:

```text
INSTALL_RESULT=PARTIAL
SHUTDOWN_PERSISTENCE=NOT_TESTED
REBOOT_PERSISTENCE=NOT_TESTED
STORAGE_REUSED=yes
QMP=PASS
SERIAL=PASS
SNAPSHOT_SAFETY=PASS
```

Evidências principais:

```text
<t001-fixtures>/sequoia/evidence/validation-summary.txt
<t001-fixtures>/sequoia/evidence/baseline.txt
<t001-fixtures>/sequoia/evidence/final-state.txt
<t001-fixtures>/sequoia/evidence/final-sha256.txt
<t001-fixtures>/sequoia/evidence/boot-1-launch.log
<t001-fixtures>/sequoia/evidence/boot-2-launch.log
<t001-fixtures>/sequoia/evidence/boot-3-launch.log
```

### Próxima validação obrigatória

Retomar a MESMA fixture, sem recriar discos/OpenCore/OVMF, até alcançar Setup Assistant e desktop funcional.

Depois:

1. criar marcador no guest;
2. shutdown limpo pelo próprio macOS;
3. boot persistent novamente;
4. confirmar marcador;
5. reboot pelo próprio macOS;
6. confirmar marcador novamente;
7. confirmar reutilização dos mesmos paths persistentes;
8. confirmar que snapshots históricos permaneceram inalterados.

Não usar `system_powerdown` como substituto do shutdown funcional do macOS para o critério de aceitação da T001.

Somente após essa evidência T001 pode mudar para `[x]`.



### Tentativa runtime 2 — CORREÇÃO DE CLASSIFICAÇÃO

A mesma fixture foi reutilizada sem recriar ou regenerar artefatos.

O estado visual inicialmente classificado como `UEFI Interactive Shell` foi corrigido após revisão. Tratava-se do boot verbose do macOS Recovery.

Evidência confirmada:

```text
#[EB|LOG:EXITBS:END]
#[EB.BST.FBS|-]
#[EB|B:BOOT]
#[EB|LOG:HANDOFF TO XNU]
```

Isso comprova que a cadeia firmware/OpenCore chegou ao handoff para o kernel XNU do ambiente de Recovery. Portanto, não há evidência de falha no UEFI/OpenCore nessa rodada.

Resultado corrigido:

```text
INSTALL_RESULT=PARTIAL
DESKTOP_REACHED=no
SHUTDOWN_PERSISTENCE=NOT_TESTED
REBOOT_PERSISTENCE=NOT_TESTED
STORAGE_REUSED=yes
QMP=PASS
SERIAL=PASS
SNAPSHOT_SAFETY=PASS
MANUAL_OPENCORE_BOOT=PASS
INSTALL_MEDIA_AB=PASS
```

Interpretação do A/B de `INSTALL_MEDIA`:

- com a mídia anexada, o OpenCore exibiu/permitiu o caminho de Recovery/installer;
- isso prova que esse caminho de instalação permanece utilizável;
- não prova que a ausência da mídia tenha causado o estado anteriormente observado, porque o screenshot havia sido classificado incorretamente.

A classificação operacional correta para T001 volta a ser: instalação Sequoia ainda incompleta; continuar a mesma fixture até Setup Assistant/desktop.

Evidências adicionais:

```text
<t001-fixtures>/sequoia/evidence/uefi-recovery-diagnosis.txt
<t001-fixtures>/sequoia/evidence/install-media-ab-after-select.png
<t001-fixtures>/sequoia/run/serial-20260918-124748.log
```

Nenhum código, disco persistente, OpenCore, OVMF ou snapshot foi alterado durante o diagnóstico.


## Validação runtime final — PASS

Fixture Sequoia:

```text
<t001-fixtures>/sequoia
```

macOS validado:

```text
macOS 15.8
```

Instalação completada até desktop funcional, com acesso SSH ao guest.

Mídia usada durante a instalação:

```text
<t001-fixtures>/sequoia/work/installer/Sequoia.img
```

Número de boots observados durante a instalação:

```text
5
```

### Storage persistente validado

Os mesmos arquivos foram reutilizados durante todos os boots:

```text
<t001-fixtures>/sequoia/persistent/macos.qcow2
<t001-fixtures>/sequoia/persistent/OpenCore.qcow2
<t001-fixtures>/sequoia/persistent/OVMF_VARS.fd
<t001-fixtures>/sequoia/persistent/OVMF_CODE.fd
```

Nenhum artefato persistente foi recriado entre os testes.

### Marcador de persistência

Criado no guest:

```text
/Users/felipeab10/Desktop/T001-PERSISTENCE-TEST.txt
```

Conteúdo:

```text
T001
uuid=0E9D1169-EF09-4C79-B89A-CB741AB48DAC
created=2026-09-18T18:02:30Z
after_shutdown=2026-09-18T18:07:12Z
```

O mesmo UUID e conteúdo foram confirmados após shutdown e reboot.

### Shutdown persistence

Resultado:

```text
SHUTDOWN_PERSISTENCE=PASS
```

Fluxo validado:

1. marcador criado dentro do macOS;
2. shutdown solicitado pelo próprio macOS;
3. QEMU encerrou;
4. VM foi relançada com os mesmos arquivos persistentes;
5. marcador permaneceu presente com o mesmo UUID.

### Reboot persistence

Resultado:

```text
REBOOT_PERSISTENCE=PASS
```

Fluxo validado:

1. marcador recebeu `after_shutdown`;
2. Restart foi solicitado pelo próprio macOS;
3. VM foi relançada usando a mesma fixture;
4. marcador permaneceu presente com conteúdo idêntico.

### Observabilidade

```text
QMP=PASS
SERIAL=PASS
```

Sockets QMP observados incluem:

```text
<t001-fixtures>/sequoia/run/qmp-20260918-140547.sock
<t001-fixtures>/sequoia/run/qmp-20260918-140645.sock
<t001-fixtures>/sequoia/run/qmp-20260918-140743.sock
```

Serial registrou repetidamente:

```text
#[EB|LOG:EXITBS:END]
#[EB|B:BOOT]
#[EB|LOG:HANDOFF TO XNU]
```

### Segurança de snapshots

Resultado:

```text
SNAPSHOT_SAFETY=PASS
```

Foi confirmado que:

- nenhum snapshot foi criado ou promovido;
- `work/rails/t001-sequoia/snapshots` permaneceu vazio;
- nenhum `qemu-img commit` foi executado;
- nenhum artefato persistente foi recriado;
- nenhum código foi alterado durante a validação runtime.

O `OVMF_VARS.fd` manteve SHA-256:

```text
6ed987af3a3c155be71665f510eae3e007eda9b8b94afd59d45e91c4a11565cc
```

### Evidências

```text
<t001-fixtures>/sequoia/evidence/marker-original.txt
<t001-fixtures>/sequoia/evidence/final-persistence-result.txt
<t001-fixtures>/sequoia/evidence/desktop-reached-ssh.txt
<t001-fixtures>/sequoia/evidence/shutdown-test-boot-1.log
<t001-fixtures>/sequoia/evidence/shutdown-test-boot-2.log
<t001-fixtures>/sequoia/evidence/reboot-test-boot-2.log
<t001-fixtures>/sequoia/run/serial-20260918-140547.log
<t001-fixtures>/sequoia/run/serial-20260918-140645.log
<t001-fixtures>/sequoia/run/serial-20260918-140743.log
```

### Resultado de aceitação

Todos os critérios obrigatórios da T001 foram satisfeitos:

```text
STATIC_REVIEW=PASS
RUNTIME_BOOT=PASS
SHUTDOWN_PERSISTENCE=PASS
REBOOT_PERSISTENCE=PASS
STORAGE_REUSED=yes
QMP=PASS
SERIAL=PASS
SNAPSHOT_SAFETY=PASS
```

Implementação validada:

```text
branch: feat/t001-persistent-mode
commit: bb171c33dbee75ab01453173afae9422552a2343
```

A T001 está concluída e liberada como dependência para T002.

## Histórico

- 2026-09-17 — implementação inicial publicada em `311435ce873666f01284cd36b94ad182b58b819a`.
- 2026-09-17 — revisão 1: `CHANGES_REQUESTED`.
- 2026-09-17 — correções publicadas em `bb171c33dbee75ab01453173afae9422552a2343`.
- 2026-09-18 — revisão 2: `APPROVED_PENDING_RUNTIME_VALIDATION`.
- 2026-09-18 — QEMU customizado reconstruído e sanity checks concluídos; ambiente pronto para fixture Sequoia.
- 2026-09-18 — tentativa runtime 1: instalação Sequoia parcial, storage reutilizado, QMP/serial/snapshot safety PASS; validação de shutdown/reboot bloqueada antes do Setup Assistant.
- 2026-09-18 — tentativa runtime 2 inicialmente classificada como UEFI Shell foi corrigida: era macOS Recovery em verbose com handoff para XNU. T001 voltou a `[-]`; instalação deve continuar na mesma fixture.
- 2026-09-18 — instalação Sequoia concluída até desktop; persistência após shutdown e reboot comprovada; QMP/serial/snapshot safety PASS; T001 marcada `[x]`.
