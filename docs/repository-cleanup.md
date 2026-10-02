# Revisão e limpeza antes do CP4

Executada em 2026-10-02, antes do commit do CP3. A revisão inventariou arquivos, tamanhos e pastas, conferiu referências de código/configuração/documentação, analisou a sintaxe dos módulos Python e verificou a entrega aprovada. Não houve commit nem início do CP4 nesta tarefa.

## Removido

- Execuções locais antigas: `output/cp1-real`, `cp3-depth`, `cp3-full`, `cp3-real`, `cp3-final`, `cp3-validated`, `output/work` e o estado antigo em `output/state.json`. São ensaios exploratórios, resultados em revisão ou a execução interrompida por falta de espaço; a entrega aprovada está no E:.
- Vídeos preparados, arrays, cenas Blender e sequências de preview desses ensaios, depois de preservar seus relatórios e manifestos úteis.
- `raw_data/Abacaxi_Articulador1.mp4`, cópia byte a byte da amostra da raiz, com SHA-256 `7880b246d7f0f415b9ccc911aed546990f8455fbe130f8dc1ee2484601bea53e`.
- Caches Python do projeto, caches de configuração/fontes do validador, sondagem `write-probe.txt`, apontador obsoleto `current-job.txt` e duas pastas vazias com nomes corrompidos contendo apenas `.thumbnails` do Blender.

A primeira limpeza removeu 2.300 arquivos, totalizando 1.556.993.077 bytes (1.484,86 MiB de tamanho lógico). Hard links podem fazer o espaço efetivamente liberado diferir desse total. Caches criados pela regressão final também foram removidos.

## Preservado

| Arquivos | Motivo |
|---|---|
| Código, testes, scripts Blender e de diagnóstico, perfis e mapas | Implementação CP1–CP3 e ferramentas úteis à calibração CP4; não foi identificada uma remoção segura por desuso. |
| `animation.blend` da raiz | Avatar original requerido pelos defaults, com hash conferido contra a referência do CP3. |
| `Abacaxi_Articulador1.mp4` da raiz | Amostra canônica usada nos ensaios. Continua ignorada pelo Git. |
| `.venv/` | Ambiente instalado necessário para desenvolvimento e validação. Continua ignorado pelo Git. |
| `docs/step-planning/` e relatório histórico | Decisões e histórico dos checkpoints. O relatório recebeu aviso de que foi sucedido pelo aceite final. |
| `output/cp3-history/` | 146 relatórios, manifestos e logs copiados e conferidos por SHA-256 antes da remoção dos ensaios; aproximadamente 5,55 MiB antes dos índices. Não é cache executável. |
| `output/cp3-validation/` e `output/reports/` | Testes, comparações, amostras de calibração e vistas anatômicas úteis. |
| [Evidências compartilhadas](evidence/cp3/README.md) | Snapshots pequenos do aceite, bake, reabertura, testes e reuso, que acompanham o commit. |
| Saída aprovada no E: | Pacote publicado e intermediários necessários ao reuso, preservados integralmente. |

O índice local `output/cp3-history/index.json` mapeia caminhos originais para os arquivos históricos preservados e seus hashes. `removed-files.json` registra os arquivos removidos e tamanhos. Referências do relatório antigo a cenas e previews removidos são históricas; relatórios preservados podem ser encontrados acrescentando `output/cp3-history/` antes do caminho relativo à antiga pasta `output/`.

## Correções e verificação

Os READMEs e o guia CP3 mencionavam um `requirements-cp3.txt` inexistente e uma delegação que não existia. Agora apontam para `requirements.txt`, que contém as versões diretas já fixadas. A descrição em português da integração Blender foi atualizada para o estado implementado.

A regressão posterior à limpeza é registrada em [cleanup-tests.json](evidence/cp3/cleanup-tests.json) e [cleanup-tests.txt](evidence/cp3/cleanup-tests.txt). Ela exercita os testes existentes, incluindo mídia real por FFmpeg/FFprobe; não refaz captura nem altera a animação aprovada.

Resultado final: **129 testes, zero falhas, erros ou skips**, em 22,219 segundos. Os 88 arquivos Python passaram na análise de sintaxe, e todos os JSON/YAML de configuração foram lidos. `git diff --check` não encontrou erros de whitespace. Os hashes do avatar e vídeo originais permaneceram iguais aos registrados no CP3.

A primeira regressão teve um erro de comprimento de caminho do Windows ao gravar um relatório temporário de mapa. A execução final usou `--output-dir output/qa` e `--ffmpeg` explícito; o registro da tentativa inicial ficou em `output/cp3-history/cleanup-tests-long-path.*`. Para testes locais, prefira um caminho curto. A limitação de caminhos longos não foi alterada nesta limpeza.

O script auxiliar `scripts/process_existing_session.py` não encontrava `src` quando executado diretamente. Ele passou a incluir a raiz do projeto no caminho de importação, como o validador já fazia; a chamada direta com `--help` foi conferida.
