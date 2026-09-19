# Reims VM Manager

`scripts/reims-vm-manager.sh` é o provisionador atual usado como base para o fluxo do appliance.

## Estado atual

O script faz preflight do host, lista versões do OSX-KVM, coleta nome/CPU/RAM/disco, valida o chunklist Apple, prepara DMG/IMG/QCOW2, gera uma identidade com `osx-serial-generator` e inicia QEMU/Reims.

Há uma diferença importante entre a intenção original e o código atual: o script gera `serial/config-auto.plist` e altera nele:

```text
Misc.Boot.ShowPicker=true
Misc.Boot.PickerMode=Builtin
Misc.Boot.Timeout=5
```

porém em seguida copia `$OSX_KVM/OpenCore/OpenCore.qcow2` para a VM. No fluxo atual não há uma etapa explícita que monte essa cópia e grave o `config-auto.plist` em `EFI/OC/config.plist`.

Portanto, até T002 corrigir e validar esse fluxo, não devemos assumir que o plist gerado externamente é o plist realmente usado pelo OpenCore da VM.

## Contrato para o appliance

T002 deve tornar o OpenCore realmente específico por VM:

1. gerar a identidade única;
2. gerar o `config.plist` final;
3. copiar/criar o `OpenCore.qcow2` dedicado;
4. montar/modificar somente essa cópia;
5. gravar o config final em `EFI/OC/config.plist`;
6. desmontar/flush;
7. reabrir a imagem read-only e validar o conteúdo efetivo.

O config final deve permitir que OpenCore enumere os volumes APFS, preserve os estágios necessários do instalador e, após a instalação concluída, faça autoboot do volume macOS instalado.

Configurações relevantes incluem:

```text
Misc.Boot.ShowPicker
Misc.Boot.Timeout
Misc.Boot.PickerMode
Misc.Security.AllowSetDefault
Misc.Security.ScanPolicy
UEFI.Quirks.RequestBootVarRouting
```

O OpenCore usa a seleção padrão persistida/Startup Disk para determinar a entrada padrão; o timeout apenas inicia automaticamente essa entrada. Portanto, `ShowPicker + Timeout` isoladamente não garante que o volume instalado seja o padrão.

Durante `installing`, não devemos fixar cedo demais o volume final, porque o instalador usa entradas transitórias como `macOS Installer`/Preboot.

Após `installed`, o requisito de produto é:

```text
boot
→ OpenCore
→ volume macOS instalado reconhecido
→ volume padrão persistente
→ timeout
→ macOS inicia sem intervenção
```

O picker/Recovery deve continuar acessível para recuperação.

## Referência

```bash
./scripts/reims-vm-manager.sh
```
