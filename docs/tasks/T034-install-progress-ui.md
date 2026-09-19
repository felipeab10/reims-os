# T034 — UI de progresso da instalação

Status: `[ ]` não iniciada

Dependências: **T002** deve fornecer eventos/estado de progresso; integração final ocorre junto do first-boot/UI do appliance.

## Objetivo

Apresentar ao usuário uma instalação profissional e contínua, ocultando logs técnicos sem deixar a máquina aparentemente parada durante download, preparação, build ou geração de imagens.

## Experiência desejada

Exemplo conceitual:

```text
Reims OS

Preparando o macOS Sequoia

████████████████░░░░░░░░  68%

Preparando a mídia de instalação

Tempo decorrido: 14:32
```

A tela pode também exibir as etapas concluídas e a etapa atual.

## Requisitos

1. Mostrar etapa atual em linguagem amigável.
2. Mostrar barra de progresso geral quando houver base real para cálculo.
3. Mostrar progresso específico de operações mensuráveis, como download e conversão, quando disponível.
4. Mostrar tempo decorrido continuamente.
5. Operações sem percentual confiável devem usar indicador indeterminado, nunca percentual inventado.
6. Não exibir stdout/stderr técnico no fluxo normal.
7. Logs técnicos completos devem continuar sendo gravados para diagnóstico.
8. Falha deve trocar a tela para estado de erro amigável, preservando log técnico.
9. A UI não pode inferir progresso parseando texto arbitrário de comandos externos; deve consumir eventos estruturados do provisionador.
10. A instalação deve continuar funcional mesmo sem a camada visual, permitindo testes automatizados/headless.

## Fases mínimas

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

## Modelo de evento

Contrato conceitual:

```json
{
  "phase": "convert",
  "label": "Preparando a mídia de instalação",
  "state": "running",
  "current": 7340032000,
  "total": 10737418240,
  "percent": 68,
  "started_at": "2026-09-18T18:00:00Z",
  "elapsed_seconds": 872
}
```

Campos de progresso numérico podem ser omitidos em fases indeterminadas.

## Critérios de aceitação

- usuário consegue perceber que o sistema continua trabalhando durante toda a preparação;
- tempo decorrido é atualizado;
- download mostra progresso real;
- pelo menos uma fase sem percentual usa modo indeterminado;
- nenhum log técnico aparece no caminho normal;
- erro controlado apresenta mensagem amigável e mantém evidência técnica;
- testes conseguem alimentar eventos fake para validar a UI sem executar uma instalação real.

## Fora de escopo

- esconder picker do OpenCore, T033;
- Plymouth de boot/update, T018/T019;
- alterar comportamento interno do reims-vgpu;
- estimativas falsas de tempo restante.

## Histórico

Task criada após a validação inicial do fluxo T002 para garantir feedback visual durante operações longas de instalação.
