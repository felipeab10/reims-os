# T004 — Criar modelo de estado persistente do appliance

Status: `[-]` em validação

Dependências: **T001**, **T002** e decisões consolidadas em `docs/arquitetura.md`.

## Objetivo

Definir e implementar o estado persistente do Reims OS fora da árvore Git, permitindo que instalação, boot, atualização e recovery saibam qual VM existe, em que fase ela está e quais recursos devem ser usados.

## Caminho principal

```text
/var/lib/reims/state.json
```

Arquivos da VM devem ficar em:

```text
/var/lib/reims/vms/<vm-id>/
```

## Escopo

- definir schema versionado de `state.json`;
- persistir `vm_id`, versão do macOS, estado da instalação, CPU, RAM e disco;
- apontar para paths persistentes da VM sem depender da checkout Git;
- representar pelo menos os estados `unconfigured`, `installing`, `installed` e `recovery`;
- tornar a fase de instalação disponível para a política de lifecycle, pois `installing` e `installed` tratam reboot do guest de forma diferente;
- fornecer leitura/escrita atômica do estado;
- impedir que update de código apague estado do usuário;
- permitir evolução futura via campo de versão do schema.

## Fora de escopo

- implementação completa de systemd/first boot;
- updater transacional;
- UI de recovery;
- múltiplas VMs;
- migração de schemas futuros além da infraestrutura mínima necessária.

## Requisitos de implementação

1. O schema deve possuir um campo inteiro `schema`.
2. Deve existir exatamente uma VM principal na 0.1.0.
3. Campos mínimos:
   - `schema`;
   - `configured`;
   - `vm_id`;
   - `macos`;
   - `state`;
   - `cpu`;
   - `ram_gb`;
   - `disk_gb`.
4. O estado deve poder registrar paths ou derivá-los de forma determinística a partir de `/var/lib/reims/vms/<vm-id>`.
5. Escrita deve usar arquivo temporário + rename atômico, ou mecanismo equivalente.
6. Arquivo parcial/corrompido não pode ser interpretado silenciosamente como instalação válida.
7. Valores desconhecidos de `schema` devem falhar com erro explícito em vez de serem reinterpretados.
8. A transição para `installed` só pode ocorrer após o fluxo que define a instalação como utilizável; não marcar `installed` no começo do provisionamento.
9. Falha durante instalação deve manter estado suficiente para diagnóstico/recovery.
10. Deve existir uma ferramenta/helper simples para imprimir/validar o estado sem iniciar a VM.
11. Não armazenar segredos desnecessários no JSON.
12. O estado `installing` deve permitir que o launcher/supervisor reconheça que reboots do guest são internos ao instalador e não devem reiniciar o host.
13. O estado `installed` é pré-condição para aplicar a política de T007 que transforma um reboot normal confirmado do macOS em reboot do host.

## Schema inicial esperado

Exemplo conceitual:

```json
{
  "schema": 1,
  "configured": true,
  "vm_id": "reims-7c91a243",
  "macos": "sonoma",
  "state": "installed",
  "cpu": 8,
  "ram_gb": 16,
  "disk_gb": 120
}
```

A implementação pode acrescentar campos necessários, mas alterações de contrato devem ser documentadas.

## Critérios de aceitação

### Unitário/estático

- criar estado válido e reler sem perda;
- escrita interrompida/simulada não substitui estado anterior válido por JSON parcial;
- schema desconhecido gera erro;
- campos obrigatórios ausentes geram erro;
- transições inválidas são rejeitadas ou explicitamente tratadas.

### Integração

1. provisionamento gera `vm_id` e estado `installing`;
2. paths persistentes ficam fora da checkout;
3. launcher consegue resolver VM e recursos a partir do estado;
4. boot subsequente não precisa perguntar CPU/RAM/disco novamente;
5. update/checkout do código pode ser substituído sem apagar `/var/lib/reims`.

## Evidência para concluir

Registrar nesta task:

- commit/PR;
- schema final;
- arquivos/helper criados;
- testes de leitura/escrita atômica;
- exemplos de transição de estado;
- prova de que paths de VM não ficam dentro da release Git.

## Implementação em validação

- Schema 1 validado em `scripts/reims-state.py`.
- Estado padrão: `REIMS_STATE_ROOT=/var/lib/reims`, com override controlado para testes.
- Estado: `REIMS_STATE_ROOT/state.json`; dados: `REIMS_STATE_ROOT/vms/<vm-id>/`.
- Estados: `unconfigured`, `installing`, `installed`, `recovery`.
- Escrita atômica: arquivo temporário no mesmo diretório, `fsync` do arquivo, `os.replace` e `fsync` do diretório quando suportado.
- Launcher state-driven: `scripts/reims-launch.sh --dry-run`.
- O VM Manager cria `installing` antes do provisionamento; `installed` não é automático.

## Histórico

Implementação T004 em validação; ainda não concluída.
