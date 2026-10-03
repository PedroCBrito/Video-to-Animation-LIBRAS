# Evidências do protótipo CP3

Snapshots preservados em 2026-10-02 durante a revisão anterior ao commit. Os JSONs foram copiados sem alterar seu conteúdo; caminhos absolutos e datas descrevem o ambiente do ensaio, não uma instalação portátil.

- `e1-tests.json`, `e3-tests.json`, `e4-tests.json` e `e4-tests.txt`: regressões anteriores; E4 contém 129 testes sem falhas, erros ou skips.
- `e4-gui-validation.json`, `e4-reuse-cli.json`, `e4-reuse-gui.json`: registros dos ensaios E4.
- `inspection-reference.json`: decisão de inspeção visual da referência.
- `accepted-metadata.json`, `visual-review.json`, `bake-check.json` e `reopen-check.json`: metadata, aceite e verificações da animação publicada.
- `accepted-gui-validation.json`, `accepted-reuse-cli.json`, `accepted-reuse-gui.json`: execução e reuso da saída final no E:.
- `avatar-hands-front.png`, `avatar-hands-back.png`: vistas usadas na identificação anatômica das mãos do avatar.
- `cleanup-tests.json` e `cleanup-tests.txt`: regressão após a limpeza do repositório.
- `review-tests.json`, `review-tests.txt`, `review-integrity.json`, `review-reopen-check.json`, `review-preview.json`: validação posterior ao commit, incluindo a proteção de promoção contra entradas alteradas e a reabertura da animação real.

A revisão conferiu os hashes de `animation.blend` e `preview.mp4` do pacote aprovado contra a metadata. O pacote e sua área interna permanecem em `E:/Video-to-Animation-LIBRAS-CP3/current/`. Esta pasta contém evidências; não contém a animação nem o cache necessário para reprocessar.

O aceite cobre o protótipo das duas mãos. Não constitui validação linguística, corporal completa ou de lote heterogêneo. Consulte o [guia do CP3](../../cp3.md) e o [registro da limpeza](../../repository-cleanup.md).
