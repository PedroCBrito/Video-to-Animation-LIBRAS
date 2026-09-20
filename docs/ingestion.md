# Uso da ingestão — CP1.0 a CP1.6

Implementado e verificado em Python 3.12 no Windows. O inventário usa apenas a biblioteca padrão; a inspeção requer FFprobe e FFmpeg. A tela verifica previamente FFmpeg, FFprobe, o pacote Python do FreeMoCap e Blender, mas as etapas atuais ainda não executam FreeMoCap ou Blender.

A organização do código separa o serviço de aplicação (`src/application/`), utilitários compartilhados (`src/common/`), etapas de preparação/sessão/verificação e adaptadores externos futuros (`src/integrations/`).

## Tela simples (CP1.6)

Para o uso cotidiano, execute:

```powershell
python gui.py
```

A tela permite selecionar um vídeo ou uma pasta, escolher a pasta de saída, iniciar o fluxo CP1 completo e acompanhar a etapa atual pela barra de progresso. O processamento ocorre em segundo plano para manter a janela responsiva. O botão de cancelamento encerra o fluxo entre etapas seguras, preservando os artefatos publicados; iniciar novamente na mesma saída permite reutilizar preparações e sessões compatíveis.

### Preflight antes do processamento

Antes de habilitar o processamento, a tela verifica quatro dependências obrigatórias:

- **FFmpeg:** preparação e decodificação da mídia;
- **FFprobe:** leitura de streams, timestamps e metadados;
- **FreeMoCap:** pacote Python que será usado pela extração do CP2;
- **Blender:** integração e exportação do esqueleto nos próximos checkpoints.

Cada item aparece como `OK` ou `FALTA`, com uma explicação. O botão **Iniciar processamento** fica bloqueado enquanto houver alguma dependência ausente. O botão **Baixar** de cada linha abre a página oficial da ferramenta; a tela não instala programas automaticamente. FFmpeg e FFprobe podem ser encontrados no `PATH` ou pelos caminhos `FFMPEG_BIN` e `FFPROBE_BIN`. Para Blender, a tela verifica `PATH`, `BLENDER_BIN`, instalações comuns do Windows em qualquer unidade disponível e também oferece **Localizar** para selecionar manualmente `blender.exe`. Depois da instalação, use **Atualizar verificações**.

O modo simples usa o perfil CP1 padrão e os caminhos detectados no preflight. A tela mostra o relatório final e pode abrir a pasta de saída. Como FreeMoCap e Blender ainda pertencem aos próximos checkpoints, a tela atualmente prepara, organiza e verifica os artefatos técnicos; ela ainda não gera uma animação 3D final.

Durante a execução, a seção **Etapas** mostra cada fase como aguardando, em andamento, concluída, concluída com pendências, cancelada ou falha. O status do vídeo atual e o motivo retornado pelo serviço aparecem na mensagem de progresso. Ao terminar com problemas, a tela lista as primeiras falhas/pendências e mantém o relatório completo para diagnóstico.

## Inventário (CP1.1)

```powershell
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage inventory
```

Percorre subpastas em ordem estável, cria um ID SHA-256 do caminho relativo POSIX e calcula separadamente SHA-256 do conteúdo dos vídeos suportados. Não deduplica arquivos com nomes ou conteúdos iguais. A pasta de saída aninhada é excluída; saída igual à entrada ou ancestral dela é rejeitada. Links de arquivos não são seguidos; links/junctions de diretórios são registrados e não percorridos.

Extensões suportadas: `.mp4`, `.mov`, `.avi`, `.mkv`, sem distinção entre maiúsculas e minúsculas. Todos os arquivos regulares descobertos aparecem no relatório, inclusive extensões não suportadas e arquivos vazios. Pastas inacessíveis aparecem em `discovery_errors`; o relatório não afirma ter listado seu conteúdo.

`ready` significa apenas candidato à inspeção, não vídeo validado. Rótulos não são inferidos do nome do arquivo.

## Inspeção (CP1.2)

Com os executáveis no PATH:

```powershell
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage inspect
python cli.py --video "./dataset/videos/sinal.mp4" --output-dir "./output" --until-stage inspect
```

Com caminhos explícitos (substitua pelos caminhos da instalação):

```powershell
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage inspect --ffprobe "C:/ffmpeg/bin/ffprobe.exe" --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe" --probe-timeout 120
```

O timeout é por invocação de ferramenta, não pelo lote inteiro. Falta de executável ou configuração inválida interrompe antes do inventário caro; erro em um vídeo não impede a inspeção dos seguintes.

A inspeção registra:

- Contêiner, streams, codec, formato de pixels, resolução e proporção de pixels.
- FPS médio e nominal como strings racionais; duração do stream e do contêiner separadas.
- Contagem declarada e contagem de frames realmente decodificados.
- Timestamps em ticks e time base; origem de cada timestamp (PTS ou best effort).
- Cadência estimada por diferenças entre timestamps de todos os frames: `cfr`, `vfr` ou `unknown`.
- Rotação declarada e metadados FFprobe originais. Espelhamento fica desconhecido; não é inferido da imagem.
- Versões e caminhos das ferramentas, tempos e resultado da validação.

Seleciona o stream de vídeo marcado como padrão, ou o de menor índice, excluindo capa anexada. Múltiplos streams de vídeo geram aviso para revisão. FFprobe lê os frames e FFmpeg decodifica integralmente o stream selecionado para saída nula, com interrupção em erros. Áudio e qualidade visual/linguística não são validados.

Cadência usa tolerância de um tick ou 0,1% do intervalo mediano, o que for maior, para não confundir quantização temporal com VFR. É uma medida técnica do arquivo, não garantia sobre a captura. Timestamps ausentes/não crescentes e contagens inconsistentes geram revisão. Dados indisponíveis ficam `null`; não são inventados. O relatório conserva uma lista por frame, portanto seu tamanho cresce com a duração.

Os originais não são convertidos, copiados para sessão ou alterados. Hash após inspeção verifica se o conteúdo mudou durante a leitura.

## Preparação (CP1.3)

Prepara somente entradas com status `valid` na inspeção. Entradas `review` e `invalid` permanecem no relatório com preparação `not_run`; não são promovidas silenciosamente a resultados utilizáveis.

```powershell
python cli.py --video "./dataset/videos/sinal.mp4" --output-dir "./output" --until-stage prepare --ffprobe "C:/ffmpeg/bin/ffprobe.exe" --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe"
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage prepare --profile "./config/profiles/cp1-media-default.yaml" --ffprobe "C:/ffmpeg/bin/ffprobe.exe" --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe"
```

O perfil padrão provisório produz `output/work/<clip-id>/<run-id>/prepared/video.mp4` em MP4/H.264/yuv420p, remove áudio, aplica autorrotação e preserva a cadência da fonte. Para exigir CFR, use um perfil YAML com `fps_mode: cfr` e `target_fps`, por exemplo `30/1`. A fonte nunca é sobrescrita.

Cada clipe preparado recebe `preparation.json` com fonte relativa e hash, perfil e fingerprint, ferramenta, caminhos, hash do derivado, tempo e resultado da validação pós-FFmpeg. A execução publica também `output/reports/prepare-<batch-id>.json`. O comando retorna 0 somente quando todas as entradas inspecionadas foram preparadas; ocorrências de revisão, inválidas ou falhas retornam 2.

## Sessão FreeMoCap (CP1.4)

O comando `session` executa as etapas anteriores e materializa cada preparação válida em uma sessão mínima:

```powershell
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage session --profile "./config/profiles/cp1-media-default.yaml" --ffprobe "C:/ffmpeg/bin/ffprobe.exe" --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe"
```

Cada sessão fica em `output/work/<clip-id>/<run-id>/freemocap/`, com exatamente um arquivo em `synchronized_videos/camera_01.mp4` e um `session.json`. O manifesto registra o hash do preparado, o contrato `freemocap_recording_v1`, o método de materialização (`hardlink` ou `copy`) e a verificação da descoberta. O CP1.4 não executa FreeMoCap; CP2 fará essa integração.

O comando retorna 0 somente quando todos os vídeos inspecionados têm preparação e sessão verificadas. Entradas em revisão, inválidas ou com falhas individuais mantêm evidências no relatório e resultam em código 2.

## Verificação integrada (CP1.5)

O comando `verify` executa `inventory`, `inspect`, `prepare` e `session`, depois revalida os artefatos gerados:

```powershell
python cli.py --video "./raw_data/Abacaxi_Articulador1.mp4" --output-dir "./output/cp1-real" --until-stage verify --profile "./config/profiles/cp1-media-default.yaml" --ffprobe "C:/ffmpeg/bin/ffprobe.exe" --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe"
```

Por clipe, a verificação confere hashes, existência e layout da sessão, decodificação do preparado e do vídeo que o FreeMoCap encontrará, contagem de frames e duração. O resultado fica em `verification.json`; o relatório consolidado fica em `output/reports/verify-<batch-id>.json`.

O status `pass` significa aprovação técnica dessas verificações. `review` indica divergência ou aviso que precisa de análise; `fail` indica quebra estrutural ou arquivo não decodificável. A etapa não valida qualidade visual, entendimento em LIBRAS ou qualidade linguística. A amostra local `raw_data/Abacaxi_Articulador1.mp4` passou tecnicamente; a proveniência e a cobertura da coleção completa do V-LIBRASIL ainda precisam ser confirmadas.

## Metadados opcionais

`--metadata-json` aceita um arquivo JSON UTF-8 com chaves que são caminhos relativos à pasta de entrada (ou à pasta do arquivo em `--video`). Exemplo de contrato, não adaptação automática do dataset:

```json
{
  "schema_version": "1.0",
  "clips": {
    "interprete_a/sinal.mp4": {
      "dataset_id": "exemplo-001",
      "gloss": "OLÁ",
      "signer": "interprete_a",
      "repetition": 1
    }
  }
}
```

```powershell
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage inventory --metadata-json "./dataset/metadata.json"
```

Os campos são preservados sem interpretação linguística. Caminhos absolutos, `..`, barras invertidas, chaves duplicadas e valores não finitos são rejeitados. Entradas de metadados sem arquivo correspondente ficam em `unmatched_metadata`. O próprio sidecar, se descoberto dentro da entrada, aparece como `skipped`.

## Relatórios e códigos de saída

Cada execução publica `output/reports/<stage>-<batch-id>.json`, incluindo `inventory`, `inspect`, `prepare`, `session` e `verify`. Os arquivos anteriores não são sobrescritos. A publicação usa arquivo temporário no mesmo diretório e hard link atômico; o sistema de arquivos de saída deve suportar hard links (validado em NTFS). Não há fallback para publicação parcial em sistemas incompatíveis.

| Estado da entrada | Significado |
|---|---|
| `ready` | Inventariada; conteúdo de vídeo ainda não validado. |
| `valid` | Inspeção e decodificação do stream selecionado concluídas sem os avisos verificados. |
| `review` | Decodificação concluída, mas há incerteza de metadados/timestamps/seleção. |
| `invalid` | Vazio, ilegível, corrompido, sem vídeo, timeout ou fonte alterada. |
| `unsupported` | Extensão fora do contrato. |
| `skipped` | Arquivo de metadados explicitamente fornecido. |

Código 0: pelo menos um candidato válido para a etapa e nenhuma ocorrência pendente. Código 2: inspeção/inventário concluído com ocorrências, metadados sem correspondência, ou nenhum candidato válido. Código 1: erro global de caminhos, configuração, ferramentas ou publicação. Argumentos inválidos da CLI usam o código 2 do argparse.

Esses estados pertencem à ingestão e não substituem `pass/review/fail` da qualidade de animação futura. A CLI exige `--until-stage` e executa o serviço compartilhado; `prepare`, `session` e `verify` são as etapas de CP1.3–CP1.5, e `extract` integra o CP2 com perfil FreeMoCap, evidências e esqueleto de origem. A tela atual executa o fluxo simples de CP1.6; ela já reconhece o status da etapa `extract`, enquanto a configuração avançada do backend permanece explícita na CLI. `retarget`, `export`, `--resume`, `--avatar` e `--rig-map` continuam propostos.

## Verificação executada

1. CP1.0: cinco testes de caminhos, publicação de relatório e CLI sem pacotes externos passaram antes do CP1.1.
2. CP1.1: 12 testes acumulados passaram antes do CP1.2, incluindo IDs, exclusão da saída, Unicode, metadados e arquivo ilegível.
3. CP1.2: 23 testes acumulados passaram, sem skips, com FFmpeg/FFprobe 9.0.1. Incluem MP4/MOV/AVI/MKV, VFR, rotação, entrada corrompida/truncada, arquivo somente de áudio e CLI em lote sem pacotes externos.
4. CP1.3: 31 testes acumulados passaram, sem skips. Os oito novos testes cobrem perfil, preparação, manifesto, pós-validação, CLI e reutilização/adulteração do derivado.
5. CP1.4: 36 testes acumulados passaram, sem skips. Os cinco novos testes cobrem sessão mínima, layout único, manifesto, reutilização/adulteração, falha isolada e CLI.
6. CP1.5: 40 testes acumulados passaram, sem skips. Os quatro novos testes cobrem FPS racional, verificação técnica, preservação de revisão e CLI completa.
7. Refatoração estrutural: 42 testes passaram, incluindo os novos testes dos utilitários comuns e a execução da CLI pela camada de aplicação compartilhada.
8. CP1.6: 49 testes foram executados; 40 passaram e 9 integrações foram ignoradas sem FFmpeg/FFprobe acessíveis, incluindo construção da tela, preflight de dependências, validação de seleção, eventos de progresso/status, estado persistido e cancelamento controlado.
9. CP2.4: métricas, classificação técnica e overlays SVG vinculados ao `run_id`, com quatro testes controlados.
10. CP2.5: adaptador Blender com processo controlado, publicação atômica, hashes, logs e falhas explícitas, com quatro testes controlados.
11. CP2.6: etapa `extract` no serviço, composição configurável na CLI, estados por sessão e suporte de status na tela, com testes de serviço/CLI/UI e regressão final de 78 testes; 69 passaram e 9 integrações de mídia foram ignoradas sem FFmpeg/FFprobe acessíveis.

```powershell
python -m unittest discover -s tests -v
```

Se as ferramentas não estiverem no PATH, configure antes `FFMPEG_BIN` e `FFPROBE_BIN` com os executáveis completos. Essas variáveis são usadas pelos testes; a CLI usa PATH ou as opções `--ffmpeg`/`--ffprobe`. Sem ferramentas, quatro testes de integração são ignorados, o que não equivale à validação integral.

Os testes geram e removem apenas suas próprias mídias sintéticas temporárias. A amostra local `raw_data/Abacaxi_Articulador1.mp4` também foi processada pelo fluxo completo e aprovada tecnicamente. Normalização adicional, execução do FreeMoCap e avaliação visual/linguística continuam pendentes.
