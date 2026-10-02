# CP3 — Protótipo das duas mãos

Atualizado em 2026-10-02. Escopo autorizado pelo usuário: receber um vídeo e gerar uma animação das duas mãos no rig original de `animation.blend`, com preview, bake, reabertura e revisão. Há geometria corporal estática; o avatar não possui rig de tronco/braços nem controle dedicado de palma/punho. A avaliação linguística e o CP3 corporal completo não estão aprovados por este protótipo.

## Estado e etapas de implementação

| Etapa | Implementação e validação antes de avançar |
|---|---|
| E1 — Ambiente | Configuração compartilhada, versão do backend conferida, UTF-8 e caches em processos filhos. 106 testes passaram, sem skips. |
| E2 — Transferência | Pontos das mãos do CP2, escala explícita, movimento global e articulação dos 38 ossos. 14 testes específicos; ensaios reais de 172 frames com bake/reabertura aprovados tecnicamente. Inspeção visual parcial registrada, sem aceite global. |
| E3 — Operação e entrega | Cache verificado, revisão sem repetir captura, pacote atômico e saída interna separada. 120 testes passaram, sem skips, incluindo FFmpeg/FFprobe reais. Aprovação/publicação testadas com fixtures controladas. |
| E4 — CLI/GUI | Fluxo completo por padrão, preview compacto, ações de revisão e caminhos de ferramentas compartilhados. Regressão final: 129 testes, 0 falhas, 0 erros, 0 skips. Ensaio real e repetições pela GUI/CLI no E: concluídos; aprovação registrada e publicada. |

**Protótipo fechado:** em 2026-10-02 o usuário respondeu “Aceitar os movimentos das duas mãos para o protótipo” à solicitação de inspeção do preview completo (frames 0–171, ambas as mãos). Esse aceite foi registrado pela CLI, vinculado aos hashes, e o mesmo pacote foi promovido para `animations/`, sem recaptura ou rebake. Não houve avaliação linguística nem aprovação de corpo completo, lote heterogêneo ou calibração geral.

O [relatório anterior](relatorio-cp3-estado-2026-10-02.md) foi preservado como histórico. O detalhamento local está em `docs/step-planning/poc-3-retargeting.md`, ignorado pelo Git; este guia registra as decisões compartilhadas.

## Executar com um vídeo

Ambiente exercitado: Python 3.12.3, FreeMoCap 1.8.2, Blender 5.2.2 LTS, add-on AJC 2026.4.1039, FFmpeg/FFprobe 9.0.1. `requirements.txt` registra versões diretas Python; não é lock transitivo. Não foi validada a instalação em outra máquina nem a migração para outro Blender/FreeMoCap.

Com esse ambiente e as ferramentas disponíveis, execute na raiz do projeto:

```powershell
.venv/Scripts/python.exe cli.py --video "Abacaxi_Articulador1.mp4" --output-dir "E:/Video-to-Animation-LIBRAS-CP3/result"
.venv/Scripts/python.exe gui.py
```

Na GUI, selecione o vídeo e a saída e clique em iniciar. Ao terminar, use **Abrir resultado**, **Ver preview** e **Revisar animação**. O Blender executa em segundo plano, sem operação manual por vídeo. A verificação do personagem continua disponível separadamente.

O fluxo compartilhado executa CP1 → CP2 → CP3. Defaults: avatar `animation.blend`, mapa `config/rig-map-depth.yaml`, perfil `config/profiles/cp2-hands-depth.yaml` e backend de FreeMoCap 1.8.2 com profundidade local das mãos. Os caminhos do esqueleto e da pose são obtidos automaticamente da sessão verificada. `--until-stage verify` mantém o uso parcial do CP1; `--until-stage extract` exige configuração explícita, conforme o [guia de ingestão](ingestion.md). `export` é alias da entrega `.blend`, sem FBX/GLB.

Configure as ferramentas uma vez por `BLENDER_BIN`, `FFMPEG_BIN` e `FFPROBE_BIN`, ou por `config/tool-paths.local.json` (ignorado pelo Git):

```json
{
  "BLENDER_BIN": "D:/blender.exe",
  "FFMPEG_BIN": "C:/caminho/ffmpeg.exe",
  "FFPROBE_BIN": "C:/caminho/ffprobe.exe"
}
```

A GUI salva o Blender selecionado nesse arquivo. Ambas as interfaces usam a mesma configuração; variáveis de ambiente têm prioridade e flags explícitas da CLI prevalecem. Um caminho explícito inválido gera erro. Há descoberta pelo PATH e, no Windows, por instalações comuns; isso não substitui a configuração do avatar ou mapa.

## Saída e repetição

```text
<saída>/
  review/<clip-id>/<run-id>/       # resultado tecnicamente verificado, aguardando revisão
    animation.blend
    preview.mp4
    metadata.json
  animations/<clip-id>/<run-id>/  # mesmo pacote após aprovação visual
  .pipeline/
    work/                        # vídeo preparado, captura, pose, esqueleto e job CP3
    reports/                     # relatórios de execução, inventário e mapa
    runtime/                     # configuração/cache dos processos filhos
    state.json                   # estado de execução separado do estado do resultado
    .lock                        # exclusão de escrita simultânea nesta saída
```

O preview MP4 mostra vídeo à esquerda e mãos do avatar à direita, em todos os frames: direita azul, esquerda laranja. Sequências PNG/JPG, viewer por frame e logs permanecem internos. A animação de entrega contém o personagem e a nova Action, preserva as 22 Actions originais e reproduz sem carregar o esqueleto CP2. Vídeo e avatar originais permanecem intactos.

Uma repetição compatível confere hashes e reutiliza captura, esqueleto, animação baked e preview. Mudança de perfil separa a área de captura. Mudanças em avatar, mapa, pose ou scripts do movimento geram outra identidade de job. Cache concluído corrompido ou exportador CP2 incompatível é rejeitado com motivo; não há substituição silenciosa. Esqueletos antigos sem o novo contrato de compatibilidade exigem uma saída nova. Não há migração ou limpeza automática de históricos nesta etapa.

O lock impede dois processos de escrever na mesma saída ao mesmo tempo e é liberado pelo sistema operacional ao fechar o processo. Cancelamento/timeout dos backends interrompe a árvore de processos para impedir filhos gravando depois do término. Falhas e cancelamentos não publicam em `animations/`. A falta de espaço é erro de execução; o ensaio interrompido no C: não recebeu aprovação e foi repetido no E: por solicitação do usuário.

Os intermediários podem ocupar centenas de MB por clipe, mesmo quando o pacote final é pequeno. Eles ficam na saída escolhida, inclusive caches/temporários dos processos filhos. Retomada avançada de lote, política de retenção/limpeza, calibração generalizada e formatos adicionais pertencem a CP4–CP6.

## Revisão sem repetir a captura

Um resultado começa em `review`; ter canais finitos e reabrir no Blender não aprova orientação, contatos ou qualidade dos dedos. Inspecione as duas mãos em todos os frames, principalmente os intervalos registrados em `capture_warnings`. Diferenças de forma/contato e incertezas em transições/oclusões devem ser consideradas no aceite; alertas de captura permanecem na metadata mesmo após aprovação.

Na GUI, informe responsável, observações e decisão. Aprovar exige declarar a inspeção integral das duas mãos. Na CLI, forneça a pasta do pacote e um JSON de inspeção. Exemplo de **formato de uma aprovação, a preencher somente após inspeção real**:

```json
{
  "status": "pass",
  "reviewer": "Nome do responsável",
  "notes": "Conclusão da inspeção de movimento, orientação, dedos e contatos.",
  "intervals": [
    {"hand": "right", "start": 0, "end": 171, "notes": "Observações da mão direita."},
    {"hand": "left", "start": 0, "end": 171, "notes": "Observações da mão esquerda."}
  ]
}
```

```powershell
.venv/Scripts/python.exe cli.py --review-job "E:/Video-to-Animation-LIBRAS-CP3/current/review/clip_6fb4328c422f758c2ba237afe20d3552/cp3_221ff8a4a392ce319bcf" --review-file "inspecao.json"
```

O registro vincula a revisão ao vídeo e à animação atuais. `pass` exige cobertura integral de frames de ambas as mãos e promove o pacote para `animations/`, sem duplicar arquivos, recapturar ou rebakear. `review` ou `fail` mantém o pacote na área de revisão e registra a decisão; a metadata conserva `linguistic_quality_validated: false`. Uma revisão aprovada não pode ser rebaixada por essa operação; mudanças de movimento exigem outra versão de job. Mantenha a área interna disponível para revisar ou reutilizar; o `.blend` já entregue reproduz de forma independente.

Códigos de saída: `0` quando todas as entradas do fluxo solicitado foram aprovadas; `2` quando há revisão/falha por entrada; `1` para erro de configuração/execução da aplicação. Resultado `review` com execução concluída não é crash. Pasta sem vídeos compatíveis não conta como sucesso do CP3.

## Alterações necessárias ao plano original

- **CP3.1/CP3.3:** consumir `evidence/pose.json` normalizado do CP2, vinculado por hash, em vez das posições reconstruídas da armature AJC. No frame 60, a armature deslocava indevidamente o punho esquerdo. Os pontos existentes preservam X horizontal/Z vertical e profundidade local ao punho; não se infere profundidade global entre as mãos pelo corpo monocular. Não foi adicionado estimador ou rig substituto.
- **Calibração do protótipo:** escala pela mediana das cadeias não polegares; os três segmentos do polegar incluem punho→MCP no primeiro segmento. Como não há controle de punho, as cinco raízes de dedos transportam a mão globalmente. Base da palma quase colinear/colapsada retém a última orientação confiável e registra mão/frame/motivo. Limiares atuais: seno abaixo de 0,25 ou largura abaixo de 30% da mediana do clipe. Isso não aprova o intervalo automaticamente.
- **Integração CP1/CP2 exigida por CP3:** namespace por perfil no fluxo completo; evidências idênticas preservam timestamp/hash; exportação do esqueleto CP2 passa a ter reuso verificado por entrada, executável/script e versão do add-on. O ensaio inicial CLI→GUI revelou que reexportar sempre alterava o hash e duplicava jobs. A correção foi validada antes dos ensaios finais de repetição. Comandos parciais continuam disponíveis.
- **Operação CP3.6:** `.pipeline/` concentra intermediários, configuração/cache/temporários de backends ficam na saída, ferramentas e defaults são compartilhados, MP4 compacto acompanha o `.blend`, revisão explícita pode promover o mesmo pacote sem reprocessar, e lock protege escrita concorrente. Originais são conferidos antes da entrega; revisão, cancelamento e falha não concedem aprovação.

## Evidências executadas

Snapshots do aceite, bake/reabertura, testes e reuso estão em [evidence/cp3/](evidence/cp3/README.md) e acompanham o repositório. Os caminhos abaixo registram a localização original dos ensaios. A [limpeza antes do CP4](repository-cleanup.md) preservou relatórios históricos e removeu intermediários locais antigos; a saída aprovada no E: permanece integral.

- E1: `output/cp3-validation/e1-tests.json` — 106 testes, sem falhas/erros/skips.
- E2: comparação por mão em frames 0/1/17/20/30/60/90/120/131/133/134/163/168/169/171; imagens `output/cp3-validation/e2-*.jpg`. Erro máximo de posição média das cinco raízes versus punho CP2 escalado: 5,211171213437282e-7 unidades. Essa inspeção parcial não é o aceite integral.
- E3: `output/cp3-validation/e3-tests.json` — 120 testes; corrupção/ausência de artefatos, revisão obsoleta/incompleta, cancelamento, promoção sem duplicação, lock e preview real.
- E4: `E:/Video-to-Animation-LIBRAS-CP3/tests/.pipeline/e4-tests.json` — 129 testes, sem falhas/erros/skips, 22,578 s. Inclui cancelamento antes/durante preparação CP3; os temporários da regressão ficaram no E:.
- Ensaio real: `E:/Video-to-Animation-LIBRAS-CP3/current/.pipeline/gui-validation.json` e relatórios internos. Tkinter real foi iniciado com janela oculta e acionou `IngestionApp._start`; não houve clique manual no Blender. Isso valida o worker/serviço; não é uma avaliação humana da ergonomia da tela.
- Job real: `cp3_221ff8a4a392ce319bcf`; vídeo `Abacaxi_Articulador1.mp4`, SHA-256 `7880b246d7f0f415b9ccc911aed546990f8455fbe130f8dc1ee2484601bea53e`; avatar original SHA-256 `0725cf76324fea57d62872351986ca044ba58ae2376f045bde5f927bb34f33d4`.
- Bake/reabertura: frames 0–171, aproximadamente 29,97 FPS, 380 curvas, 65.360 keyframes, 22 Actions originais preservadas e diferença máxima de transforms 0.
- Aceite/promoção: `output/cp3-validation/inspection-reference.json`, relatório `.pipeline/reports/review-0a02e62030ff40ecab05a84f5f271565.json` e `metadata.json` publicado (`status: completed`, `visual_review.status: pass`, `linguistic_quality_validated: false`). Pacote em `E:/Video-to-Animation-LIBRAS-CP3/current/animations/clip_6fb4328c422f758c2ba237afe20d3552/cp3_221ff8a4a392ce319bcf/`.
- Repetição CLI após aprovação: `.pipeline/reuse-cli.json` — `pass`, 11,640 s, `pipeline_result: completed`, seis artefatos com hashes/datas inalterados, sem nova captura/exportação/animação. Uma pasta de pacote para o vídeo na saída final.
- Repetição GUI após aprovação: `.pipeline/reuse-gui.json` — `pass`, 11,438 s, mesmos seis artefatos inalterados, `pipeline_result: completed` e mensagem “Animação aprovada e disponível.” no Tkinter. As primeiras repetições também passaram enquanto o resultado estava em revisão (CLI 11,469 s; GUI 11,500 s).
- SHA-256 da animação aprovada: `78826e76ffefd8c992ad7b1b48cf9d43ba57ca547f08fda075e89ccd1b159370`. A promoção e ambas as repetições preservaram esses bytes; o antigo pacote de revisão não permanece duplicado.

Comandos de validação reproduzíveis:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/validate_cp3.py --tests --output-dir E:/Video-to-Animation-LIBRAS-CP3/tests --test-report E:/Video-to-Animation-LIBRAS-CP3/tests/.pipeline/e4-tests.json
.venv/Scripts/python.exe -X utf8 scripts/validate_cp3.py --frontend gui --output-dir E:/Video-to-Animation-LIBRAS-CP3/current
.venv/Scripts/python.exe -X utf8 scripts/validate_cp3.py --basic --check-reuse --output-dir E:/Video-to-Animation-LIBRAS-CP3/current
.venv/Scripts/python.exe -X utf8 scripts/validate_cp3.py --frontend gui --check-reuse --output-dir E:/Video-to-Animation-LIBRAS-CP3/current
```

O validador configura os caminhos locais observados das ferramentas; a execução cotidiana usa sua descoberta/configuração. Ensaios antigos e entradas foram preservados. Não houve validação de lote heterogêneo, instalação limpa, rig corporal, consumidor FBX/GLB ou avaliação linguística.
