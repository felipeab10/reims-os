# T033 — Polimento de boot nativo OpenCore

Status: `[ ]` não iniciada

Dependências: fluxo principal validado, incluindo persistência, T002/T003, lifecycle, update/rollback e matriz Ventura/Sonoma/Sequoia.

## Objetivo

Fazer o boot normal do Reims OS se aproximar da experiência de um Mac nativo, sem comprometer diagnóstico ou recovery.

Esta task é deliberadamente tardia. Ela só deve ser iniciada quando o comportamento funcional estiver validado.

## Resultado esperado

No uso normal pós-instalação:

```text
Power on
  ↓
boot discreto do host
  ↓
OpenCore sem picker visível
  ↓
chime de inicialização, quando suportado/validado
  ↓
macOS
```

O usuário não deve perceber menus técnicos ou etapas do hypervisor no caminho normal.

## Escopo

- ocultar o picker do OpenCore no boot normal;
- manter autoboot do volume macOS instalado;
- avaliar/configurar chime de inicialização via OpenCore;
- reduzir elementos visuais técnicos entre firmware/OpenCore/macOS;
- preservar um mecanismo explícito de recovery para exibir o picker;
- documentar como entrar no picker/Recovery quando o modo normal estiver oculto;
- validar que ocultar o picker não altera a seleção persistente do volume do sistema.

## Fora de escopo

- corrigir persistência;
- corrigir instalação;
- corrigir detecção do volume padrão;
- corrigir lifecycle;
- corrigir fullscreen;
- esconder erros ainda não resolvidos;
- remover logs/observabilidade usados pelo recovery.

## Princípios

1. Nenhuma configuração de aparência pode mascarar uma falha funcional.
2. O picker só deve ser ocultado depois que o autoboot estiver comprovadamente estável.
3. Recovery deve permanecer acessível mesmo com o picker oculto.
4. O chime é polimento; falha de áudio não pode impedir o boot.
5. Deve existir uma forma simples de reativar modo diagnóstico/verbose.
6. Mudanças são feitas no `OpenCore.qcow2` dedicado da VM, nunca na imagem compartilhada do projeto.

## Pontos a validar no OpenCore

A implementação deve estudar a versão de OpenCore efetivamente usada e configurar somente opções suportadas por ela.

Itens esperados para investigação:

- `Misc.Boot.ShowPicker`;
- `Misc.Boot.Timeout`;
- comportamento do picker oculto e hotkeys;
- acesso a Recovery;
- suporte a boot chime/áudio do OpenCore;
- `UEFI.Audio` e opções relacionadas na versão utilizada;
- preservação da seleção padrão/Startup Disk.

Não copiar configurações de versões diferentes do OpenCore sem validar o schema usado pela imagem atual.

## Critérios de aceitação

### Boot normal

1. host liga;
2. nenhum picker técnico fica visível no caminho normal;
3. macOS instalado inicia automaticamente;
4. nenhuma tecla/intervenção é necessária.

### Recovery

1. mecanismo documentado permite tornar o picker acessível;
2. Recovery continua selecionável;
3. falha do volume padrão não deixa o usuário sem caminho de recuperação.

### Áudio

Se o chime for habilitado:

- tocar de forma consistente no hardware suportado;
- não introduzir atraso ou bloqueio de boot;
- ausência de backend de áudio deve degradar sem impedir inicialização.

### Não regressão

- Ventura continua bootando;
- Sonoma continua bootando;
- Sequoia continua bootando;
- seleção padrão persistente continua funcional;
- updater/recovery continuam funcionais;
- logs continuam disponíveis em modo diagnóstico.

## Evidência para concluir

Registrar:

- versão exata do OpenCore;
- diff efetivo do `config.plist`;
- vídeo/screenshots ou logs de boot normal;
- prova de acesso ao recovery;
- resultado do chime em hardware validado;
- teste nas três versões suportadas;
- confirmação de que nenhuma funcionalidade foi escondida antes de estar validada.

## Histórico

Task criada como polimento final, deliberadamente adiada até a plataforma principal estar validada.
