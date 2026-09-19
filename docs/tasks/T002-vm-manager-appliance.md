# T002 — Simplificar o VM Manager para fluxo de appliance

Status: `[x]` concluída e validada — runtime Sequoia 15.8, reboots internos, QMP, autoboot e Recovery PASS

Dependência: **T001** deve estar implementada ou disponível para integração.

## Objetivo

Transformar `scripts/reims-vm-manager.sh` no provisionador de uma única instalação macOS principal, escondendo opções internas que não fazem parte da experiência do Reims OS.

## Resultado esperado

No primeiro boot, o usuário deve escolher apenas:

1. macOS Ventura, Sonoma ou Sequoia;
2. quantidade de CPUs;
3. memória RAM;
4. tamanho do disco, mínimo 70 GiB.

Ao terminar a preparação, o macOS deve iniciar automaticamente com `reims-vgpu-pci`, sem perguntar se o usuário deseja ativar Reims.

## Escopo

- limitar a lista de versões a `ventura`, `sonoma` e `sequoia`;
- remover a pergunta de nome da VM;
- gerar um identificador interno aleatório e persistível, por exemplo `reims-<8+ caracteres>`;
- remover a escolha interativa de SMBIOS;
- usar um único SMBIOS interno/configurável e documentado, sem exposição no wizard;
- manter validação de CPU/RAM e margem reservada ao host;
- manter disco mínimo de 70 GiB;
- reaproveitar download do OSX-KVM, chunklist, `dmg2img`, `qemu-img` e geração de identidade/OpenCore existentes;
- iniciar Reims automaticamente após o provisionamento;
- integrar com o modo persistente criado em T001;
- durante a instalação, iniciar o launcher com política de reboot que mantenha o mesmo processo QEMU/janela vivo entre os reboots normais do instalador (equivalente a `QEMU_REBOOT_ACTION=reset`);
- impedir sobrescrita acidental de uma instalação existente;
- gerar um `OpenCore.qcow2` realmente personalizado para a VM, contendo o `EFI/OC/config.plist` gerado para aquela identidade;
- configurar OpenCore para permitir seleção padrão persistente e boot automático do sistema instalado;
- preservar a flexibilidade necessária aos estágios intermediários `Recovery`, `macOS Installer` e Preboot durante a instalação;
- estruturar o provisionamento em etapas observáveis, emitindo progresso/estado consumível pela futura UI sem expor logs técnicos ao usuário.

## Fora de escopo

- fullscreen nativo, tratado em T003;
- schema definitivo de `/var/lib/reims/state.json`, tratado em T004;
- systemd/first boot automático;
- updater;
- ISO;
- suporte Tahoe;
- múltiplas VMs simultâneas.

## Requisitos de implementação

1. O menu principal da 0.1.0 deve ter somente o fluxo `Instalar macOS`.
2. A lista visível deve conter exatamente Ventura, Sonoma e Sequoia.
3. `NAME` não pode mais ser solicitado ao usuário.
4. O identificador interno deve ser gerado automaticamente, ser válido para uso como diretório/rail e ter risco desprezível de colisão.
5. Se houver colisão com diretório/estado existente, gerar outro ID em vez de sobrescrever.
6. O usuário não deve escolher SMBIOS. O modelo interno escolhido deve ficar explícito no código/configuração e registrado nos artefatos da VM.
7. A identidade gerada pelo `osx-serial-generator` deve continuar sendo única por instalação.
8. CPU, RAM e disco devem ser validados antes de download/build pesado.
9. O disco não pode aceitar valor inferior a 70 GiB.
10. Não perguntar `Iniciar com Reims agora?`; o fluxo deve seguir automaticamente.
11. O dispositivo gráfico do fluxo de produto deve ser `reims-vgpu-pci`.
12. O provisionamento não pode modificar a imagem OpenCore compartilhada do projeto.
13. Um erro deve encerrar com mensagem clara e sem deixar uma instalação marcada como pronta.
14. Não remover capacidades de desenvolvimento necessárias aos testes do repositório sem justificar e documentar.
15. Enquanto a instalação estiver em andamento, reboots normais do guest não podem fechar a janela/QEMU nem exigir relançamento manual; o fluxo deve continuar automaticamente no mesmo storage persistente.
16. A política de reboot da fase de instalação não deve ser confundida com a política pós-instalação de T007.
17. O `config.plist` gerado deve ser gravado dentro da partição EFI do `OpenCore.qcow2` dedicado; um plist externo/orfão não satisfaz o requisito.
18. A imagem OpenCore final deve ser validada por inspeção read-only, comprovando pelo menos `EFI/BOOT/BOOTX64.EFI`, `EFI/OC/OpenCore.efi` e `EFI/OC/config.plist`.
19. O config final deve habilitar `Misc.Security.AllowSetDefault=true` e preservar `UEFI.Quirks.RequestBootVarRouting=true` quando disponível na base.
20. Durante `installing`, a configuração não pode forçar permanentemente o volume final e impedir os boots temporários do instalador.
21. Depois que a instalação for marcada `installed`, o próximo boot deve selecionar automaticamente o volume macOS principal sem exigir interação do usuário.
22. O picker/recovery deve continuar acessível por mecanismo de recuperação documentado, mesmo com autoboot normal.
23. Operações longas do manager devem possuir fases identificáveis e emitir estado estruturado suficiente para exibir etapa atual e tempo decorrido.
24. Percentual só deve ser emitido quando houver métrica real. Processos como build sem progresso quantificável devem suportar estado indeterminado.
25. Logs detalhados devem permanecer separados da saída amigável/estruturada de progresso.

## Critérios de aceitação

### Estático

- `bash -n scripts/reims-vm-manager.sh` passa;
- não existem prompts interativos para nome, SMBIOS ou confirmação de Reims;
- Tahoe e versões pré-Ventura não aparecem no menu de produto;
- o mínimo de 70 GiB continua validado.

### Provisionamento controlado

Executar com diretórios temporários/dedicados sempre que possível e provar que:

1. um ID interno foi gerado automaticamente;
2. o diretório da VM usa esse ID;
3. identidade OpenCore foi gerada;
4. disco recebeu o tamanho solicitado;
5. versão selecionada corresponde ao artefato baixado/preparado;
6. ao final o launcher é chamado automaticamente com `reims-vgpu-pci` e modo persistente;
7. uma segunda execução não sobrescreve silenciosamente a primeira instalação;
8. um reboot do instalador mantém o mesmo QEMU/sessão ativo e continua usando os mesmos discos persistentes, sem intervenção manual do usuário;
9. a inspeção read-only do `OpenCore.qcow2` comprova que o `config.plist` personalizado está realmente dentro da imagem;
10. após instalação concluída, rebootar a VM sem interação no picker inicia o volume macOS instalado automaticamente;
11. Recovery/picker continua acessível pelo mecanismo de recuperação escolhido.

### Segurança

- nenhuma VM/snapshot/golden existente deve ser alterada durante a validação;
- nenhum broad `pkill`;
- nenhum `qemu-img commit` destrutivo;
- downloads e arquivos intermediários devem permanecer isolados na VM criada.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- arquivos alterados;
- modelo SMBIOS interno adotado e justificativa;
- exemplo do ID gerado;
- comandos de validação;
- saída resumida dos testes;
- prova de que o launcher final usa `reims-vgpu-pci` e persistência;
- confirmação de que uma instalação existente não foi sobrescrita.

## Implementação parcial em validação

Branch local:

```text
feat/t002-vm-manager-appliance
```

HEAD reportado mais recente:

```text
4efae714
```

Commits reportados:

```text
df4a3397 feat(appliance): simplify VM manager flow [T002]
c4bcd075 fix(appliance): stage OpenCore builder per VM
ff2cb676 fix(appliance): stage OpenCore sources outside builder workdir
81183c22 fix(appliance): copy staged OpenCore EFI into image
4efae714 fix(appliance): complete T002 controlled validation
```

Arquivos alterados:

```text
scripts/reims-vm-manager.sh
tests/t002-vm-manager.sh
```

Resultados já reportados:

```text
STATIC_TESTS=PASS
CONTROLLED_TESTS=PASS
INSTALLER_LAYOUT=PASS
OVERWRITE_PROTECTION=PASS
LAUNCHER_TEST=PASS
OPENCORE_IMAGE_TEST=PENDING
RUNTIME_INSTALL_REBOOT=PENDING_RUNTIME_VALIDATION
RUNTIME_AUTOBOOT=PENDING_RUNTIME_VALIDATION
RUNTIME_RECOVERY=PENDING_RUNTIME_VALIDATION
```

O fluxo reportado já contém wizard reduzido, ID automático, storage persistente, launch com `--persistent --device reims-vgpu-pci` e `QEMU_REBOOT_ACTION=reset`.

A T002 não pode ser aprovada ainda. Antes da validação runtime é obrigatório gerar uma imagem OpenCore descartável e comprovar, por inspeção read-only, que a imagem final contém `EFI/BOOT/BOOTX64.EFI`, `EFI/OC/OpenCore.efi` e o `EFI/OC/config.plist` personalizado com os campos exigidos.

Também deve ser reconciliado o path efetivo da mídia de instalação: o layout reportado lista `<vm>/<version>.img`, enquanto a chamada de launch reportada usa `<vm>/installer/<version>.img`. O código e os testes devem usar um contrato único.

### Builder OpenCore — diagnóstico complementar

A validação controlada chegou a `guestfish 1.60.1` e `libguestfs-test-tool=PASS`, portanto o bloqueio não deve ser atribuído genericamente ao libguestfs.

Foi identificado no upstream `osx-serial-generator` que o fluxo nativo de criação de bootdisk usado por `generate-unique-machine-values.sh` chama `opencore-image-ng.sh` quando `--create-bootdisks`/`--output-bootdisk` é usado. Esse builder usa um diretório temporário próprio e espera, ao lado do script, a árvore `EFI` e `resources/OcBinaryData/Resources`, além de `startup.nsh` no diretório de execução.

A variante `opencore-image-ng-linux.sh` usa contrato `.fish` diferente e está introduzindo complexidade adicional no staging atual. Antes de adicionar novos workarounds, T002 deve validar o uso do builder padrão `opencore-image-ng.sh` (ou o fluxo nativo `--output-bootdisk`) em staging privado por VM, mantendo a imagem compartilhada intacta.

O objetivo continua sendo gerar uma imagem dedicada e então executar `qemu-img check` + inspeção read-only de `EFI/BOOT/BOOTX64.EFI`, `EFI/OC/OpenCore.efi` e `EFI/OC/config.plist`.

## OpenCore dedicado — validação controlada PASS

Implementação reportada em:

```text
branch: feat/t002-vm-manager-appliance
HEAD: 04d34e53
commit: 04d34e53 fix(appliance): finalize per-VM OpenCore image build
```

Builder selecionado:

```text
third_party/osx-serial-generator/generate-specific-bootdisk.sh
→ third_party/osx-serial-generator/opencore-image-ng.sh
```

Fixture exclusiva:

```text
<t002-fixtures>/opencore
```

Resultados reportados:

```text
OPENCORE_BUILD=PASS
QEMU_IMG_INFO=PASS
QEMU_IMG_CHECK=PASS
OPENCORE_BOOTX64=PASS
OPENCORE_EFI=PASS
OPENCORE_CONFIG=PASS
CONFIG_IMAGE_MATCH=PASS
SHOW_PICKER=PASS
PICKER_MODE=PASS
TIMEOUT=PASS
ALLOW_SET_DEFAULT=PASS
REQUEST_BOOT_VAR_ROUTING=PASS
IDENTITY_IN_IMAGE=PASS
SHARED_OPENCORE_UNCHANGED=PASS
INSTALLER_LAYOUT=PASS
OVERWRITE_PROTECTION=PASS
LAUNCHER_TEST=PASS
STATIC_TESTS=PASS
CONTROLLED_TESTS=PASS
```

A inspeção final foi read-only via `guestfish --ro`, com descoberta de partições/filesystems e extração do `EFI/OC/config.plist`. O plist extraído foi semanticamente equivalente ao plist gerado e, nessa execução, também byte-identical.

A pendência estática remanescente é pequena: a fase `build_opencore` já emite `running` e `completed`, porém `failed` ainda não é garantido em todos os caminhos de erro do builder. Antes do runtime completo, fechar esse contrato e garantir que stdout/stderr técnico do builder possa ser capturado em log separado da saída amigável.

Pendências runtime continuam:

```text
RUNTIME_INSTALL_REBOOT=PENDING_RUNTIME_VALIDATION
RUNTIME_AUTOBOOT=PENDING_RUNTIME_VALIDATION
RUNTIME_RECOVERY=PENDING_RUNTIME_VALIDATION
```

## Contrato de progresso — READY_FOR_RUNTIME

Implementação reportada em:

```text
branch: feat/t002-vm-manager-appliance
HEAD: d9791ee4
commit: d9791ee4 feat(appliance): complete provisioning progress contract [T002]
```

Resultados:

```text
PROGRESS_OPENCORE_RUNNING=PASS
PROGRESS_OPENCORE_COMPLETED=PASS
PROGRESS_OPENCORE_FAILED=PASS
PROGRESS_OPENCORE_SUCCESS=PASS
PROGRESS_OPENCORE_FAILURE=PASS
TECHNICAL_LOG_CAPTURE=PASS
FRIENDLY_ERROR=PASS
STATIC_TESTS=PASS
CONTROLLED_TESTS=PASS
OPENCORE_NON_REGRESSION=PASS
```

A fase `build_opencore` permanece corretamente indeterminada, sem percentual artificial. O output técnico do builder é capturado em `<vm>/run/provision.log`, enquanto a saída amigável é separada.

Com isso, as pendências estáticas/controladas da T002 estão fechadas. Restam apenas os critérios runtime:

```text
RUNTIME_INSTALL_REBOOT=PENDING_RUNTIME_VALIDATION
RUNTIME_AUTOBOOT=PENDING_RUNTIME_VALIDATION
RUNTIME_RECOVERY=PENDING_RUNTIME_VALIDATION
```

## Runtime T002 — bloqueio de ambiente

A primeira tentativa de validação runtime não iniciou o provisionamento.

Estado reportado:

```text
branch: feat/t002-vm-manager-appliance
HEAD: d9791ee4fb56f15139a02d003c3f5f16474de0de
RUNTIME_INSTALL_REBOOT=NOT_RUN
RUNTIME_AUTOBOOT=NOT_RUN
RUNTIME_RECOVERY=NOT_RUN
SNAPSHOT_SAFETY=PASS
FAILURE_CLASSIFICATION=ENVIRONMENT
```

Pré-condições do host:

```text
DISPLAY=:1
WAYLAND_DISPLAY=wayland-1
/dev/kvm=available
filesystem: 23G livres, 94% utilizado
```

Nenhuma nova fixture/runtime foi criada e as fixtures T001/T002 existentes permaneceram intactas.

A criação de um disco virtual de 70 GiB em qcow2 não exige necessariamente 70 GiB físicos livres no momento da criação, pois a imagem pode ser sparse. Porém o fluxo completo mantém artefatos de installer e produz gravações significativas no qcow2 durante a instalação; com apenas ~23 GiB livres a validação completa foi considerada insegura.

Antes de repetir o runtime, fazer auditoria read-only de uso de disco, liberar espaço suficiente ou disponibilizar mídia/caching seguro fora da fixture T001. Não apagar nem reutilizar destrutivamente evidências T001/T002.

## Storage preflight runtime

A auditoria read-only do host encontrou:

```text
filesystem=/home (btrfs)
free=22.5 GiB
T001 fixture≈37 GiB
T002 OpenCore fixture≈175 MiB
Sequoia.img≈3.0 GiB
T001 macos.qcow2: 80 GiB virtual / ≈32.3 GiB atual
recommended_free≈48 GiB
deficit≈25.5 GiB
```

A maior oportunidade aparente está em `<legacy-worktree>/vm/disks/run/*.img`, com quatro imagens reportadas em ≈39.8 GiB cada. Essas imagens são classificadas como evidência/dados de projeto e não devem ser removidas sem provar que são clones de execução descartáveis e que nenhum processo/rail/snapshot depende delas.

Como `/home` é Btrfs, decisões de limpeza não devem usar apenas `du`: antes de remover uma imagem grande é necessário medir extents compartilhados/exclusivos com `btrfs filesystem du`. O teste de reflink reportado em `/tmp` não comprova suporte ou ausência de reflink no filesystem `/home`; qualquer teste deve ser feito em um diretório temporário descartável dentro de `/home`.

A próxima ação é uma validação segura dos arquivos em `vm/disks/run`, sem remover nada automaticamente. Uma única imagem realmente exclusiva e descartável pode ser suficiente para eliminar o déficit de runtime.

## Runtime T002 — falha de chunklist em stdout sem TTY

A retomada runtime chegou ao fluxo real de download do Sequoia e falhou na verificação chunklist antes de conversão/criação de discos.

Resultado reportado:

```text
VM_ID=reims-564a0707b2fc464d
STORAGE_PREFLIGHT=PASS
WIZARD_UI=PASS
VM_ID_GENERATION=PASS
QEMU_BIN=PASS
FAILURE_CLASSIFICATION=CODE_BUG

Image verification failed. ([Errno 25] Inappropriate ioctl for device)
```

A inspeção do `fetch-macOS-v2.py` upstream mostra assimetria relevante: o caminho de download protege `os.get_terminal_size()` com fallback para 80 colunas quando stdout não é TTY, enquanto `verify_image()` chama `os.get_terminal_size()` diretamente, sem `try/except`. Em execução headless/redirecionada isso pode gerar `ENOTTY` (`Errno 25`) antes da validação dos chunks.

Antes de alterar o produto, a versão pinada local deve ser inspecionada e a hipótese reproduzida contra os `.dmg/.chunklist` já baixados na fixture runtime. A correção do Reims OS não deve depender de stdout ser um terminal interativo e não deve modificar silenciosamente o submodule upstream.

A fixture parcial deve ser preservada para reuso da mídia no diagnóstico, evitando novo download enquanto a integridade não tiver sido determinada.

## Chunklist non-TTY — corrigido

Correção reportada em:

```text
branch: feat/t002-vm-manager-appliance
HEAD: bf360327
commit: bf360327 fix(appliance): support macOS verification without TTY [T002]
```

Root cause confirmado na versão pinada de `fetch-macOS-v2.py`: `verify_image()` chamava `os.get_terminal_size()` sem fallback em stdout não-TTY, produzindo `OSError: [Errno 25] Inappropriate ioctl for device`.

A solução mantém o submodule upstream intacto e adiciona o adapter Reims-owned:

```text
scripts/reims-fetch-macos.py
```

Resultados:

```text
LOCAL_NONTTY_BUG_CONFIRMED=yes
UPSTREAM_SUBMODULE_UNCHANGED=PASS
NONTTY_REPRODUCTION=PASS
CHUNKLIST_VERIFY_NONTTY=PASS
CHUNKLIST_VERIFY_TTY=PASS
NONTTY_VERIFY_REGRESSION=PASS
EARLY_PROVISION_LOG=PASS
FETCH_MEDIA_PROGRESS=PASS
STATIC_TESTS=PASS
CONTROLLED_TESTS=PASS
OPENCORE_NON_REGRESSION=PASS
```

A mídia Sequoia já baixada na fixture parcial foi verificada integralmente com sucesso após a correção, sem redownload.

A fixture parcial `reims-564a0707b2fc464d` permanece como evidência do bug original e não deve ser continuada como instalação válida. A próxima validação runtime deve criar um novo VM ID e um novo diretório de VM.

## Runtime T002 — QMP socket path longo

A segunda tentativa runtime limpa chegou até o launcher e falhou antes do QEMU iniciar por comprimento excessivo do pathname Unix usado pelo QMP.

Estado reportado:

```text
VM_ID=reims-57f0fd6b61a74542
FETCH_MEDIA_RUNTIME=PASS
CHUNKLIST_RUNTIME=PASS
RUNTIME_OPENCORE_SANITY=PASS
QEMU_BIN=PASS
QMP=FAIL
FAILURE_CLASSIFICATION=REIMS_RUNTIME
```

Path rejeitado pelo QEMU:

```text
<t002-fixtures>/runtime-sequoia-retry-2/vms/reims-57f0fd6b61a74542/run/qmp-20260918-182038.sock
```

Esse pathname possui 127 caracteres, excedendo o limite aceito pelo socket Unix do QEMU (`< 108` bytes no pathname).

O launcher atual deriva `QMP_SOCK` diretamente de `RUN_DIR`. A correção deve desacoplar o socket QMP efêmero dos logs persistentes: serial/provision/logs continuam em `RUN_DIR`, enquanto o socket deve morar em um runtime dir curto e seguro, preferencialmente `$XDG_RUNTIME_DIR` com fallback controlado para `/tmp`.

A solução deve preservar compatibilidade com paths curtos existentes, limpar somente o próprio socket/runtime dir e fornecer um caminho explícito/descobrível para consumidores QMP. Não reduzir artificialmente o VM ID nem depender do tamanho do workspace como workaround.

A fixture completa de `runtime-sequoia-retry-2` deve ser preservada para reteste após a correção, evitando novo download/provisionamento se os artefatos permanecerem íntegros.

## Runtime T002 — instalação e autoboot PASS; Recovery pendente

A correção de QMP curto foi implementada e a mesma VM provisionada foi utilizada para concluir a instalação.

Estado reportado:

```text
branch: feat/t002-vm-manager-appliance
HEAD: 521a2390
commit: 521a2390 fix(vm): use short runtime path for QMP socket [T002]
VM_ID=reims-57f0fd6b61a74542
QMP_FIX=PASS
QMP_DISCOVERY=PASS
QMP=PASS
SERIAL=PASS
RUNTIME_INSTALL_REBOOT=PASS
PID_CONTINUITY=PASS
DESKTOP_REACHED=yes
MACOS_VERSION=15.8
SSH=PASS
RUNTIME_AUTOBOOT=PASS
AUTOBOOT_MANUAL_INPUT=no
POST_INSTALL_INSTALL_MEDIA_ATTACHED=no
SNAPSHOT_SAFETY=PASS
RUNTIME_RECOVERY=PENDING
```

O socket QMP real passou a usar pathname curto e foi descoberto por `run/qmp.path`:

```text
/run/user/1000/r-q-vP4Rys/qmp.sock
length=35
```

`query-status` confirmou QEMU em execução. Os reboots do instalador ocorreram mantendo o mesmo processo QEMU, sem relançamento manual. A instalação chegou ao desktop do macOS 15.8 e o acesso SSH foi validado.

Após shutdown limpo, a mesma VM foi relançada sem `INSTALL_MEDIA`. Sem qualquer input no picker, o OpenCore iniciou automaticamente o macOS instalado e o SSH voltou a responder. Isso satisfaz o critério de autoboot pós-instalação.

A única pendência funcional restante da T002 é comprovar que Recovery continua acessível pelo picker/caminho de recuperação. A task não deve ser marcada `[x]` antes dessa evidência.

## Recovery final — PASS; sanity pós-Recovery pendente

A validação de Recovery foi concluída com sucesso na VM instalada:

```text
VM_ID=reims-57f0fd6b61a74542
PICKER_VISIBLE=PASS
RECOVERY_DISCOVERABLE=PASS
RECOVERY_ENTRY=Recovery 15.8 (dmg)
RUNTIME_RECOVERY=PASS
QMP=PASS
SERIAL=PASS
SNAPSHOT_SAFETY=PASS
```

Entradas observadas no picker:

```text
1. OSX
2. Recovery 15.8 (dmg)
3. UEFI Shell
```

O Recovery foi acessado diretamente, sem auxiliary action, e a evidência visual mostrou o ambiente macOS Recovery com Restore from Time Machine, Reinstall macOS Sequoia, Safari e Disk Utility.

Pendência única antes da revisão final:

```text
AUTOBOOT_AFTER_RECOVERY=PENDING
SSH_AFTER_RECOVERY=PENDING
```

O próximo passo é somente aguardar/concluir o boot normal após sair do Recovery e confirmar que o macOS instalado continua sendo selecionado automaticamente, sem input no picker, e que o SSH volta a responder.

## Validação final T002 — PASS

A validação runtime final foi concluída na VM:

```text
VM_ID=reims-57f0fd6b61a74542
branch=feat/t002-vm-manager-appliance
HEAD=521a2390ebd7e2b4d54da07286b07c7a060f2d3a
macOS=15.8 (24H23)
```

Critérios finais:

```text
WIZARD_UI=PASS
VM_ID_GENERATION=PASS
FETCH_MEDIA_RUNTIME=PASS
CHUNKLIST_RUNTIME=PASS
EARLY_PROVISION_LOG=PASS
RUNTIME_OPENCORE_SANITY=PASS
QMP_FIX=PASS
QMP_DISCOVERY=PASS
QMP=PASS
SERIAL=PASS
RUNTIME_INSTALL_REBOOT=PASS
PID_CONTINUITY=PASS
DESKTOP_REACHED=yes
SSH=PASS
RUNTIME_AUTOBOOT=PASS
AUTOBOOT_MANUAL_INPUT=no
POST_INSTALL_INSTALL_MEDIA_ATTACHED=no
PICKER_VISIBLE=PASS
RECOVERY_DISCOVERABLE=PASS
RUNTIME_RECOVERY=PASS
AUTOBOOT_AFTER_RECOVERY=PASS
SSH_AFTER_RECOVERY=PASS
SNAPSHOT_SAFETY=PASS
```

Entradas observadas no picker:

```text
1. OSX
2. Recovery 15.8 (dmg)
3. UEFI Shell
```

O Recovery foi acessado diretamente pela entrada `Recovery 15.8 (dmg)`, sem auxiliary action e sem alterar a seleção padrão. Após sair do Recovery, o boot normal voltou ao macOS instalado automaticamente e o SSH respondeu novamente.

A correção do socket QMP curto permaneceu funcional no runtime real, usando `run/qmp.path` para descobrir o socket efetivo sob `/run/user/<uid>/...`.

Com os critérios estáticos, controlados e runtime concluídos, a T002 está aceita.

## Histórico

Nenhuma implementação validada ainda.
