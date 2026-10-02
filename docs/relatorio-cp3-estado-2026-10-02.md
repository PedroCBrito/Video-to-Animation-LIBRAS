# Relatório do CP3 — implementação neste chat e estado em 2026-10-02

> Registro histórico anterior ao aceite final. O estado vigente está no [guia CP3](cp3.md), com o protótipo das duas mãos aprovado. A [limpeza anterior ao CP4](repository-cleanup.md) removeu os intermediários locais antigos e preservou relatórios em `output/cp3-history/`; os caminhos de cenas e previews abaixo descrevem aquele ensaio e podem não existir mais.

## 1. Resultado e alcance deste relatório

O CP3 **ainda não recebeu aceite global**. O chat avançou de um inventário do avatar e um mapa parcial para uma execução real pela CLI de **CP1 → CP2 → transferência → preview → bake → reabertura independente**. Essa execução terminou em **`review`**, porque a qualidade visual das mãos ainda não foi aprovada. Há uma animação de diagnóstico reabrível na área de trabalho; nenhuma entrega real aprovada foi publicada por essa execução.

Este documento consolida o histórico disponível do chat, o código atual e os artefatos encontrados no projeto em 2026-10-02. Distingue implementação, teste controlado, execução real e aceite. Na preparação deste relatório foram realizadas leituras e conferências de arquivos/hashes; não foi retomada a implementação nem executado novamente o processamento do vídeo.

Base de aceite: [poc-3-retargeting.md](step-planning/poc-3-retargeting.md). O estado inicial descrito nesse plano está desatualizado: ele ainda declara CP3.2–CP3.6 não iniciados. O [progresso dos checkpoints](step-planning/progresso.md) também conserva o estado anterior. Ambos foram preservados nesta tarefa para manter o histórico; este relatório descreve o estado posterior.

As alterações continuam na árvore de trabalho, com arquivos modificados e novos arquivos ainda não rastreados pelo Git. Não há um commit único que delimite todo o trabalho deste chat. Parte do inventário, da CLI e das integrações já existia nas retomadas; a atribuição abaixo considera os registros da conversa e as evidências, não apenas o `git diff` atual.

## 2. Onde a execução parou

### 2.1 Último processamento integrado confirmado

Comando usado durante o chat:

```powershell
python scripts/validate_cp3.py --stage export --depth --output-dir output/cp3-depth
```

Conclusão persistida em **2026-10-01 às 20:27:11, horário de São Paulo** (`2026-10-01T23:27:11.759551+00:00` no relatório).

Relatório: [retarget-0898f72c1f1f4292bd932e9cd8e0d6df.json](../output/cp3-depth/reports/retarget-0898f72c1f1f4292bd932e9cd8e0d6df.json).

| Etapa do serviço | Resultado persistido |
|---|---|
| Entrada | Um vídeo válido: `Abacaxi_Articulador1.mp4` |
| Preparação | `prepared` |
| Sessão FreeMoCap | `session_ready` |
| Verificação CP1 | `pass` |
| Extração CP2 | `completed` |
| Retargeting CP3 | `review` |
| Publicação | `published_path: null` |

O `state.json` está em `completed`, com 100% de progresso. Isso significa **execução encerrada**, não aceite da animação. O resultado de qualidade está no relatório por entrada e em `metadata.json`. O código prevê retorno 2 quando o retargeting não termina com todas as entradas em `completed`.

`--until-stage export` é, atualmente, um **alias da execução `retarget`**. Não existe uma etapa `export` independente no serviço: a função de retargeting também executa preview, bake, reabertura e tenta publicar, sujeita às verificações. Por isso o relatório final tem `stage: retarget`.

### 2.2 Última ação iniciada, sem conclusão recuperada

Após o processamento acima, foram acrescentadas opções de ensaio pela GUI e de regressão com FFmpeg ao script de validação. O último comando iniciado foi:

```powershell
python scripts/validate_cp3.py --tests
```

A chamada estava em execução quando o registro anterior terminou. Na retomada para este relatório, a célula de execução já não estava disponível, e o script não grava um relatório permanente dos testes. **Não é possível declarar o resultado dessa regressão com mídia real.**

O ensaio real pela GUI estava preparado no script, mas não há `gui-validation.json` nos diretórios examinados nem resultado confirmado no chat. A GUI tem cobertura por testes de contrato; a execução real por esse ponto de entrada permanece pendente.

### 2.3 Código atual versus código da última execução

Depois do último processamento confirmado, o hash de referência do mapa com profundidade foi atualizado e foram acrescentadas/reforçadas verificações no código. O mapa atual não tem o mesmo hash do mapa usado na entrega de diagnóstico:

| Referência | SHA-256 |
|---|---|
| `rig-map-depth.yaml` usado na execução integrada | `bbea3e7c92f01d8ea1aa1369750e27b7540ef26f4e3a64edaf18f4b7069cf074` |
| `config/rig-map-depth.yaml` atual | `b38b72346412e11b642402cd990b3acbceb7b4345f2ccc49f10fd19802d03bd0` |

A alteração final desse YAML corrigiu `reference_source_sha256` para a referência real com profundidade. Os parâmetros de transferência não foram alterados nessa última edição. Mesmo assim, **a execução anterior não comprova uma execução integrada da árvore final com esse novo hash**. Os manifestos anteriores devem continuar sendo lidos como evidência das versões que registram.

## 3. Estado de cada passo do plano

| Passo | Implementação e validação realizadas | Estado de aceite |
|---|---|---|
| **CP3.0 — Inventário** | Avatar aberto em Blender real; rig, malhas vinculadas, hierarquia, repouso, Actions e dependências inventariados. Serviço disponível na CLI e no worker da tela. Hash do original preservado. | **Concluído para identificar o rig das mãos.** GUI visual não homologada. |
| **CP3.1 — Mapa** | Referência anatômica independente, rejeição de lados/dedos trocados, contratos de calibração, cobertura persistida e confirmação dos nomes contra esqueleto CP2 real. Mapas para captura achatada e com profundidade. | **Estrutura e contrato validados; calibração visual ainda parcial.** Não equivale a aprovar todas as poses e contatos. |
| **CP3.2 — Ligação CP2→CP3** | Saída obtida automaticamente da sessão; checagem de identidades, manifestos e hashes; cópia do avatar; rejeição de CP2 em revisão/falha. Testes negativos e fluxo real pela CLI. | **Validado no fluxo real pela CLI.** Verificações finais adicionadas precisam da regressão integrada final. |
| **CP3.3 — Transferência** | Blender em segundo plano aplicou movimento ao rig existente e gerou `retargeted.blend`. 38 ossos, 172 frames, transforms finitos, FPS ajustado e preservação das curvas das 22 Actions. | **Validação técnica realizada.** Qualidade e posições das mãos continuam dependentes de CP3.4. |
| **CP3.4 — Comparação visual** | Renders comparados com frames do vídeo; perda de profundidade identificada; captura com profundidade e orientação pelo plano da palma testadas; preview sincronizado de 172 frames gerado. | **Em revisão, sem aceite.** Persistem diferenças de contato e posição da mão de apoio; inspeção por mão/intervalo incompleta. |
| **CP3.5 — Bake** | Nova Action com canais gravados; cena reaberta em processos separados sem carregar a origem CP2; todas as matrizes dos frames comparadas; resultado idêntico nas verificações persistidas. | **Teste técnico de diagnóstico aprovado.** O movimento visual que foi gravado ainda não recebeu aceite. |
| **CP3.6 — Publicação/CLI/GUI** | CLI e worker GUI ligados ao mesmo serviço; metadata e preview; publicação por renomeação de diretório; testes de bloqueio em revisão/falha/cancelamento. CLI real terminou em revisão. | **Implementação parcial no aceite:** faltam GUI real, regressão final confirmada e publicação real de um caso visualmente aprovado. |

O pedido era validar cada passo antes de avançar. Houve validações intermediárias, mas **CP3.4 não passou no aceite visual**. O bake e a integração posteriores foram exercitados como diagnóstico e testes de infraestrutura, com publicação bloqueada. Isso não deve ser registrado como conclusão sequencial de todos os aceites do plano.

## 4. Entradas, ambiente e limites do avatar

| Item | Valor confirmado/registrado |
|---|---|
| Avatar original | `animation.blend`, 42.457.900 bytes |
| SHA-256 do avatar | `0725cf76324fea57d62872351986ca044ba58ae2376f045bde5f927bb34f33d4` |
| Vídeo de ensaio | `Abacaxi_Articulador1.mp4`, 4.742.515 bytes |
| SHA-256 do vídeo | `7880b246d7f0f415b9ccc911aed546990f8455fbe130f8dc1ee2484601bea53e` |
| Vídeo preparado na execução inicial | SHA-256 `2aba4379b6f1b42fb2d23008fc7089676d70f0dd804b98ca67a7971d8e065c55` |
| Sequência | 172 frames, `30000/1001` FPS, aproximadamente 5,739067 segundos |
| Blender | `D:\blender.exe`, 5.2.2 LTS, Python interno 3.13 |
| Python da aplicação | Ambiente `.venv`, Python 3.12 |
| FreeMoCap | 1.8.2 |
| Add-on de exportação | `ajc27_freemocap_blender_addon`, versão registrada 2026.04.1039 |
| FFmpeg/FFprobe | Instalados via WinGet; execução real exigiu acesso fora da pasta do projeto |

O rig de destino é `Armature`, com **38 ossos, 19 por mão**, cinco cadeias em cada lado, 22 Actions originais e sem constraints de pose ou bibliotecas externas vinculadas no inventário inicial. A cena original estava em 24 FPS, frames 1–60. Não há controle dedicado de palma/punho; o movimento global da mão é representado por suas cinco raízes.

**Correção de precisão documental:** o inventário registra **11 objetos de malha** no arquivo, mas somente `Mao direita` e `mao esquerda` estão vinculados à armature. Os renders mostram partes estáticas do personagem. Portanto, a descrição antiga de que o arquivo “contém somente as mãos” deve ser entendida como limite do **rig animável examinado**, não como ausência de toda geometria corporal. Não há rig completo utilizável para animar tronco/braços nesse protótipo; o corpo visível permanece estático.

O esqueleto CP2 real identificado é `freemocap_rig`, com 63 ossos. Sua cena contém elementos auxiliares e animação da captura. O destino continua sendo o rig original do avatar; o esqueleto CP2 não o substitui.

Os hashes atuais do avatar e do vídeo foram conferidos novamente para este relatório e correspondem aos valores acima. Não houve alteração desses dois arquivos originais.

## 5. O que foi feito durante o chat

### 5.1 Inventário e primeira revisão

Os registros anteriores de 2026-09-25 documentam CP3.0 e um CP3.1 parcial: inventário real, vistas frontal/posterior, mapa inicial e exposição do inventário na CLI/GUI. Na revisão registrada em 2026-09-30, o código ainda não tinha transferência, preview, bake ou publicação.

Essa revisão reproduziu três problemas no preflight: trocar lados do destino passava na validação; trocar indicador e médio também passava; configurações inválidas de calibração/backend eram aceitas. Além disso, o resultado do mapa era mostrado na CLI/tela sem um relatório próprio persistido.

### 5.2 Correções do mapa e da rastreabilidade

Foi criada [avatar-hands-reference.json](../config/avatar-hands-reference.json), uma referência anatômica separada do mapa sob teste, vinculada ao hash do avatar e às vistas de inspeção. Ela fixa malhas, lados e cadeias dos cinco dedos.

[rig_map.py](../src/animation/rig_map.py) passou a comparar o mapa com essa referência, conferir duplicações, hierarquia, grupos das malhas, backend e valores permitidos de calibração. Acrescentou relatório `rig-map-<avatar-sha>-<map-sha>.json`, com cobertura por mão/dedo e pendências explícitas. A CLI e o worker de inspeção da GUI passaram a persistir esse relatório.

Os nomes de origem foram posteriormente confirmados em um `source_skeleton.blend` real. O polegar de destino usa três segmentos; o mapa usa os três segmentos correspondentes após o carpal da origem. A abordagem não depende de nomes semelhantes para inferir a anatomia do avatar.

### 5.3 Execução real do CP2 necessária ao CP3

Foram executadas extrações reais com FreeMoCap. Primeiro houve uma sessão exploratória em caminho curto, `output/cp3-real/freemocap`, e depois o fluxo normal da CLI, em `output/cp3-full`. A sessão curta contornou um problema de comprimento de caminho do Windows e permitiu confirmar os arquivos reais produzidos pelo backend.

Foi criado um wrapper de exportação Blender para o add-on instalado. O wrapper resolveu incompatibilidade entre os ambientes Python e corrigiu FPS/intervalo da cena exportada a partir do manifesto do vídeo preparado.

O backend produz arrays `.npy`, enquanto o módulo de evidências procurava arquivos JSON. Foi implementada a normalização específica desses arrays para gerar evidências de corpo e duas mãos, conferir dimensões e finitude e preservar a validade dos pontos brutos mesmo quando o pós-processamento interpola lacunas.

O worker FreeMoCap também foi corrigido para extrair `applied_parameters` do envelope do perfil efetivo antes de chamar a função do backend. A primeira execução integrada falhava por enviar campos desse envelope como parâmetros da função.

### 5.4 Ligação automática e cópia de trabalho

[retarget_stage.py](../src/animation/retarget_stage.py) verifica que a extração está `completed`, a sessão está pronta e os manifestos de extração, sessão, evidência e esqueleto correspondem ao relatório. Confere hashes, `clip_id`, `run_id` e o nome esperado do esqueleto. CP2 em revisão não chega ao callback de transferência.

[retargeting.py](../src/animation/retargeting.py) inventaria ambos os rigs, valida o mapa, confere vídeo/origem/avatar e prepara uma cópia do avatar. O manifesto `retarget-input.json` vincula entradas, mapa, referência anatômica, scripts, versões e parâmetros. O diretório do ensaio é identificado por um fingerprint de compatibilidade. A versão de algoritmo atual é `cp3-hands-2`.

O campo transitório `reused` foi desconsiderado na comparação do manifesto de extração para permitir retomada compatível, mantendo as outras verificações de identidade e conteúdo.

### 5.5 Transferência e correções visuais

[retarget_hands.py](../scripts/blender/retarget_hands.py) avalia o movimento da origem em todos os frames, abre a cópia do avatar e grava uma nova Action. Preserva comprimentos do rig de destino, usa escala mediana das cadeias não polegares e posiciona as mãos em relação ao ponto médio inicial. As curvas das Actions originais são comparadas por digest antes/depois e preservadas na cópia.

A primeira abordagem orientava cada segmento pela direção capturada, mantendo o roll de repouso. A inspeção revelou perda de orientação/contato. A abordagem foi ajustada para obter uma base do plano da palma e aplicar a articulação por osso sobre essa orientação global. A continuidade do sinal dos quaternions é mantida; poses degeneradas e transforms não finitos causam erro.

O ensaio inicial usava profundidade achatada. Foi acrescentado um perfil que expõe `flatten_single_camera_data: false` pelo adaptador específico de FreeMoCap 1.8.2. Na primeira tentativa com profundidade foi reutilizada a conversão de eixos do caso achatado, e o preview mostrou mãos em posição/orientação incorretas. A inspeção do processamento real confirmou a necessidade de um mapa com Z vertical para essa origem. Foi criado `rig-map-depth.yaml`; a correção melhorou o resultado, sem eliminar todas as diferenças visuais.

Foram inspecionadas imagens sincronizadas, incluindo frames 0 e 60, e outras amostras durante os ensaios. O frame inicial ainda apresenta contato/forma das mãos insatisfatórios; a mão de apoio permanece com posição divergente em trechos de mão direita elevada. Isso foi relatado no chat e impediu o aceite visual. **Esses achados ainda não foram detalhados por intervalo em um relatório persistido de inspeção por mão.**

### 5.6 Preview, bake e reabertura

O preview começou com sete amostras e foi ampliado para todos os 172 frames. [preview_retarget.py](../scripts/blender/preview_retarget.py) renderiza o avatar com enquadramento fixo ao longo do clip, mão direita azul e esquerda laranja. [preview.py](../src/animation/preview.py) decodifica frames do vídeo e cria um visualizador HTML local com controle de frame e reprodução sincronizada.

[verify_bake.py](../scripts/blender/verify_bake.py) abre a cena em um novo processo Blender, verifica Action, canais, keyframes, finitude, timing, preservação das Actions e ausência de origem/constraints temporárias. Compara todas as matrizes de pose com as amostras da transferência. Salva `animation.blend` na área de trabalho e, em outro processo, reabre essa cópia para repetir a comparação.

O bake é obtido por **gravação direta dos canais durante a transferência**. Não foi criado um segundo rig no arquivo final nem uma rede temporária de constraints a remover. A verificação de independência confirma que a cena reabre com apenas a armature do avatar, sem carregar a cena CP2.

### 5.7 Serviço, CLI, GUI e publicação

O serviço [ingestion_service.py](../src/application/ingestion_service.py) recebeu `retarget`, callback e progresso. [backends.py](../src/application/backends.py) centraliza a construção dos callbacks usados pela CLI e GUI. A CLI aceita `--avatar`, `--rig-map`, `retarget` e o alias `export`; usa descoberta/configuração de Blender e perfis padrão com profundidade no fluxo CP3.

O worker da GUI foi alterado de `verify` para `retarget`, com o avatar fixo do projeto e `rig-map-depth.yaml`. Foram atualizados textos, etapas e apresentação de pendências. Existe teste controlado que verifica o uso do serviço completo e o repasse do cancelamento.

A publicação exige metadata `completed`, revisão visual `pass` vinculada aos hashes da animação e do vídeo, reabertura `pass`, hash atual do `.blend` e ausência de cancelamento. Prepara um pacote temporário com `.blend`, preview e metadata e o publica por renomeação de diretório. Revisões ficam em `work`.

O caso real continua `review`. Não houve publicação real aprovada, nem ensaio real da GUI confirmado. A infraestrutura posterior ao CP3.4 foi testada como diagnóstico; não recebeu aceite global.

## 6. Problemas encontrados, tratamento e pendências

| Problema | Tratamento realizado neste chat | Estado |
|---|---|---|
| Preflight aceitava lados/dedos trocados | Referência anatômica independente vinculada ao avatar e testes de mutação | Corrigido e testado |
| Calibração/backend inválidos aceitos | Contratos explícitos de campos/valores; validação de versão | Corrigido e testado no contrato suportado |
| Preflight do mapa sem evidência persistida | Relatório por hashes, usado pela CLI e GUI | Corrigido |
| Saída real `.npy` não reconhecida pelas evidências | Normalização específica e validade bruta por mão | Corrigido; não representa aprovação visual |
| Envelope do perfil enviado inteiro ao FreeMoCap | Worker usa `applied_parameters` | Corrigido; execução real posterior passou |
| Caminho de helper Blender inexistente | Wrapper do projeto para add-on AJC instalado | Corrigido para o ambiente ensaiado |
| NumPy do Python 3.12 carregado no Blender/Python 3.13 | `site-packages` inserido só para importar o add-on e removido antes de sua execução | Exportação real passou |
| `.blend` comprimido rejeitado pelo teste de cabeçalho | Aceitação de cabeçalhos Blender, zstd e gzip, seguida de abertura no Blender | Esqueleto real comprimido inventariado |
| Exportação em 24 FPS e fim 172, divergentes do vídeo | FPS racional e intervalo 0–171 obtidos do manifesto de preparação | Timing corrigido e verificado |
| Arquivos longos do FreeMoCap ultrapassavam limite Windows | Sessão exploratória curta; `clip_id` reduzido de 64 para 32 caracteres hexadecimais | Ensaios funcionaram; caminhos arbitrariamente longos ainda não homologados |
| Redução de `clip_id` muda identificação de execuções antigas | Hash integral do conteúdo continua preservado | Migração/retomada dos IDs antigos não implementada nesta alteração |
| Logs volumosos podiam bloquear subprocessos com pipes cheios | Drenagem periódica por `communicate(timeout=...)`; teste de saída volumosa | Correção presente, parte já existia no estado inicial das retomadas |
| Blender poderia ocultar falha de script no código de saída | Invocações de exportação/CP3 com `--python-exit-code 1` e logs por script | Implementado |
| Logs/cache escritos fora da área permitida | Runtime local e variáveis de processo para FreeMoCap, Ultralytics e Blender | Contornado nos ensaios; não é instalação global |
| Caracteres Unicode dos logs causavam erro de encoding | `PYTHONIOENCODING=utf-8` nos ensaios | Contornado |
| Primeiro uso precisava baixar modelo MediaPipe | Execução autorizada com rede e cache do modelo pesado | Extração posterior funcionou |
| FFmpeg/FFprobe fora do workspace eram bloqueados pelo ambiente | Ensaios reais executados com autorização de acesso externo | Não é falha do algoritmo; regressão final com mídia sem resultado recuperado |
| Git recusava o repositório por propriedade | `safe.directory` aplicado por comando | Sem mudança global de configuração |
| Importação antecipada de YAML quebrou CLI de inventário sem dependências | Importação movida para a função de validação do mapa | Teste específico voltou a passar |
| Comando `unittest tests.<módulo>` falhou porque `tests` não era pacote | Uso de `unittest discover -s tests` | Corrigido no modo de executar os testes |
| Profundidade achatada perdeu orientação/contato | Perfil com profundidade e orientação pelo plano da palma | Melhorou, mas CP3.4 continua em revisão |
| Conversão de eixos achatada aplicada à origem com profundidade | Segundo mapa com Z vertical; verificação de compatibilidade com metadata CP2 | Corrigido no ensaio; checagem final requer nova execução integrada |
| Avisos de thumbnail/clipboard ao salvar no Blender | Conferência do arquivo salvo e reabertura independente | Não impediram o bake; avisos continuam nos logs |
| Status dos documentos ficou atrás da implementação | Este relatório consolida o estado observado | Plano/progresso antigos não foram reescritos nesta tarefa |

## 7. Validações e resultados confirmados

### 7.1 Testes automatizados do chat

| Verificação registrada | Resultado conhecido |
|---|---|
| Revisão inicial de 2026-09-30 | 91 testes contabilizados: 82 passaram, 9 ignorados por ferramentas de mídia não configuradas |
| Mapa após correções | 8 testes específicos passaram |
| Ligação CP2→CP3 | 3 testes passaram, incluindo hash/identidade incorretos e CP2 em revisão |
| Normalização `.npy` | 3 testes passaram: lacuna curta preservada, lacuna longa/extremidade em revisão e NaN não aprovado |
| Adaptador/worker FreeMoCap | 7 testes passaram no registro dessa fase |
| Regressão que detectou dependência YAML | 101 testes contabilizados, uma falha no inventário sem dependências e 9 ignorados; falha corrigida |
| Inventário após correção YAML | 7 testes específicos passaram |
| Última regressão ampla com resultado confirmado | 101 testes contabilizados: 92 passaram, 9 ignorados, nenhuma falha |
| Publicação e contrato GUI acrescentados depois | 3 testes específicos passaram |
| Regressão final com FFmpeg (`--tests`) | Iniciada; conclusão não recuperada |

Os três testes novos de publicação não fazem parte do total anterior de 101. Não há evidência de uma regressão final completa de 104 testes aprovada. As contagens são snapshots de fases diferentes e não devem ser somadas como execuções independentes de todos os casos.

Testes relevantes: [test_rig_map.py](../tests/test_rig_map.py), [test_retarget_stage.py](../tests/test_retarget_stage.py), [test_npy_evidence.py](../tests/test_npy_evidence.py), [test_retarget_publication.py](../tests/test_retarget_publication.py), [test_avatar_inventory.py](../tests/test_avatar_inventory.py) e [test_freemocap_adapter.py](../tests/test_freemocap_adapter.py).

### 7.2 Captura real e lacunas observadas

As extrações reais terminaram com 172 frames e dados processados finitos nas duas mãos. A validade bruta registra:

| Mão | Frames com algum ponto bruto ausente/interpolado | Maior lacuna |
|---|---|---|
| Direita | 20; 133–134 | 2 frames |
| Esquerda | 17; 131–133 | 3 frames |

O contrato de pós-processamento observado permite preencher até 10 frames. As lacunas curtas internas não reprovaram automaticamente a evidência técnica, mas foram preservadas em `hand-validity.json`. Isso não comprova fidelidade de dedos, palma ou contato depois da interpolação.

### 7.3 Bake e reabertura real

Os relatórios `bake-check.json` e `reopen-check.json` da última execução confirmam:

| Critério | Resultado |
|---|---|
| Frames | 172, intervalo 0–171 |
| FPS Blender | 30, `fps_base: 1.0010000467300415` |
| Duração metadata | 5,739066934585571 segundos |
| Ossos de destino | 38 |
| Canais | 380: localização, quaternion e escala por osso |
| Keyframes | 65.360 |
| Maior diferença de transform após reabrir | 0,0, contra as amostras gravadas |
| Actions manuais preservadas | 22, conforme digests de curvas |
| Origem CP2 carregada na verificação | Não |
| Bibliotecas externas vinculadas | Nenhuma |

Esses resultados comprovam a integridade/reprodução da Action gerada. Não comprovam que a Action representa corretamente o sinal do vídeo.

## 8. Arquivos de implementação criados ou alterados

### 8.1 Componentes de CP3

| Arquivo | Função/alteração |
|---|---|
| [avatar_inventory.py](../src/animation/avatar_inventory.py) e [inspect_avatar.py](../scripts/blender/inspect_avatar.py) | Inventário seguro do `.blend`; suporte à inspeção de arquivos comprimidos acrescentado |
| [rig_map.py](../src/animation/rig_map.py) | Preflight anatômico/estrutural, contratos e relatório persistido |
| [avatar-hands-reference.json](../config/avatar-hands-reference.json) | Referência anatômica independente para este avatar |
| [rig-map.yaml](../config/rig-map.yaml) | Mapa/calibração do ensaio achatado |
| [rig-map-depth.yaml](../config/rig-map-depth.yaml) | Mapa/calibração para origem com profundidade e Z vertical |
| [retarget_stage.py](../src/animation/retarget_stage.py) | Verificações de origem e execução por entrada |
| [retargeting.py](../src/animation/retargeting.py) | Preparação, execução Blender, metadata, revisão e publicação |
| [retarget_hands.py](../scripts/blender/retarget_hands.py) | Transferência e gravação da nova Action no rig original |
| [preview_retarget.py](../scripts/blender/preview_retarget.py) e [preview.py](../src/animation/preview.py) | Renders e visualizador sincronizado local |
| [verify_bake.py](../scripts/blender/verify_bake.py) | Verificação do bake e reabertura sem origem CP2 |
| [render_hand_reference.py](../scripts/blender/render_hand_reference.py) | Vistas de inspeção anatômica do avatar |
| [sample_source_pose.py](../scripts/blender/sample_source_pose.py) | Amostras de origem para calibração |

### 8.2 Integração e correções necessárias ao ensaio

| Arquivo/grupo | Função/alteração |
|---|---|
| [cli.py](../cli.py), [app.py](../src/ui/app.py), [ingestion_service.py](../src/application/ingestion_service.py), [backends.py](../src/application/backends.py) | Entrada do usuário, callbacks compartilhados, etapa CP3, progresso e resultados |
| [npy_evidence.py](../src/extraction/npy_evidence.py), [evidence.py](../src/extraction/evidence.py) | Evidências dos arrays reais FreeMoCap |
| [freemocap_worker.py](../src/integrations/freemocap_worker.py) | Leitura correta dos parâmetros efetivos |
| [freemocap_backend.py](../src/integrations/freemocap_backend.py) | Adaptador de profundidade monocular da versão 1.8.2 |
| [export_cp2_skeleton.py](../scripts/blender/export_cp2_skeleton.py), [blender.py](../src/integrations/blender.py) | Exportação real, ambientes Python e timing |
| [inventory.py](../src/ingestion/inventory.py) | IDs de clip mais curtos para os caminhos Windows |
| [process.py](../src/integrations/process.py), [dependencies.py](../src/ui/dependencies.py) | Drenagem de subprocessos e descoberta de `blender.exe` na raiz de unidade; parte já presente nas retomadas |
| [process_existing_session.py](../scripts/process_existing_session.py) | Ensaio CP2 sobre sessão CP1 já preparada |
| [validate_cp3.py](../scripts/validate_cp3.py) | Repetição do fluxo real, runtime local e modos CLI/GUI/testes |
| `src/animation/__init__.py` e testes | Exposição dos novos serviços e regressões específicas |

Perfis criados: [cp2-freemocap-1.8.2.yaml](../config/profiles/cp2-freemocap-1.8.2.yaml) e seu [contrato de parâmetros](../config/profiles/cp2-freemocap-1.8.2-supported.json); [cp2-hands-depth.yaml](../config/profiles/cp2-hands-depth.yaml) e seu [contrato de parâmetros](../config/profiles/cp2-hands-depth-supported.json). O primeiro mantém o entrypoint original; o segundo usa o adaptador do projeto para desativar o achatamento.

## 9. Documentos e evidências gerados: o que são

### 9.1 Documentos em Markdown

| Documento | O que representa e como usar |
|---|---|
| [poc-3-retargeting.md](step-planning/poc-3-retargeting.md) | Planejamento específico, passos e critérios de aceite. Inclui os primeiros resultados de CP3.0/CP3.1; estado não atualizado após as execuções recentes. |
| [progresso.md](step-planning/progresso.md) | Histórico geral de checkpoints e primeiros incrementos de CP3. Também conserva pendências antigas. |
| [validacao-cp3.md](../output/cp3-validation/validacao-cp3.md) | **Relatório novo da revisão inicial de 2026-09-30**: três achados no preflight, testes e estado antes da implementação posterior. A frase “nenhum código de implementação foi modificado” vale para aquela revisão, não para todo este chat. |
| Este relatório | **Documento novo de 2026-10-02**, com o estado consolidado posterior, interrupção, problemas, evidências, limites e retomada. |

Não foi encontrado outro relatório Markdown específico de CP3 nas pastas examinadas. `docs/planning.md` é o plano geral existente; não é um novo relatório de execução. Markdown e JSON têm papéis diferentes: os JSON abaixo são evidências/manifestações de execução, não novos planos.

### 9.2 Evidências estruturadas e mídia

| Arquivo/padrão | Conteúdo |
|---|---|
| `reports/avatar-<sha>.json` | Inventário real do avatar ou esqueleto, versão Blender e hash do arquivo |
| `reports/rig-map-<avatar-sha>-<map-sha>.json` | Resultado do preflight e cobertura por lado/dedo |
| `reports/extract-<id>.json` | Resultado do serviço até CP2; existem tentativas failed, review e completed |
| `reports/retarget-<id>.json` | Resultado integrado por vídeo; última execução real em review |
| `freemocap/session.json`, `freemocap.json`, `source_skeleton.json` | Vínculos da sessão, extração e esqueleto CP2 |
| `freemocap/evidence.json` | Métricas/status técnicos associados à extração |
| `freemocap/evidence/pose.json` | Normalização JSON das poses reais `.npy` e hashes de origem |
| `freemocap/evidence/hand-validity.json` | Validade bruta por ponto/frame e intervalos ausentes/interpolados |
| `retarget-input.json` | Contrato do job com mapa completo, entradas, hashes, versões e timing |
| `retarget-result.json` | Action, escala, método, digests das Actions preservadas e matrizes dos frames |
| `bake-check.json`, `reopen-check.json` | Verificações técnicas independentes do movimento gravado |
| `visual-review.json` | Estado da revisão vinculado à animação/vídeo; no caso real, review e `intervals: []` |
| `metadata.json` | Identidade e resultado do pacote de diagnóstico, incluindo `face_animation: false` |
| `preview/frames.json`, `preview/index.html`, PNG/JPG | Frame rate, controle sincronizado e imagens do avatar/vídeo |
| `*.log` | Saídas de execução e diagnóstico de FreeMoCap/Blender |
| `source-samples.json`, `source-depth-samples.json` | Matrizes/posições de origem amostradas para calibrar eixos |
| `video-000.png` etc. | Frames de referência examinados durante o chat |
| `current-job.txt` | Apontador de conveniência de um ensaio manual; **não identifica a execução integrada mais recente** |
| `map.json`, `rig-map.json`, `freemocap-options.json` | Entradas auxiliares serializadas dos ensaios, não substituem os mapas/perfis versionados |
| `gui-validation.json` | Evidência prevista pelo script para ensaio real GUI; **não encontrada** |

As pastas `output/cp3-validation/runtime`, caches do FreeMoCap/Ultralytics e arquivos temporários de sondagem são suporte de execução; não são documentação ou resultado aprovado.

`output/` e `docs/step-planning/` são ignorados pelo `.gitignore` atual. Este novo relatório foi colocado diretamente em `docs/` para não cair na exclusão da documentação local por etapa. A existência de uma evidência no disco não significa que ela esteja versionada.

## 10. Localização das execuções e do último resultado

### 10.1 Histórico de extração

| Relatório | Resultado e função |
|---|---|
| [extract-bccf8739765f45328f02973d5ea9dc11.json](../output/cp3-full/reports/extract-bccf8739765f45328f02973d5ea9dc11.json) | Primeira tentativa integrada, `failed`; fase anterior à correção do envelope de parâmetros |
| [extract-eafb909bc4414c998a8967caffce38fc.json](../output/cp3-full/reports/extract-eafb909bc4414c998a8967caffce38fc.json) | Captura/exportação realizadas, `review`, antes da normalização dos arrays nas evidências |
| [extract-fdb2cfe03ec242cc9951408c6160e68e.json](../output/cp3-full/reports/extract-fdb2cfe03ec242cc9951408c6160e68e.json) | CP2 técnico `completed` com captura achatada |
| [extract-3d7ad3e49df04f409fd019d5a7905fd5.json](../output/cp3-depth/reports/extract-3d7ad3e49df04f409fd019d5a7905fd5.json) | CP2 técnico `completed` com profundidade |
| [retarget-0898f72c1f1f4292bd932e9cd8e0d6df.json](../output/cp3-depth/reports/retarget-0898f72c1f1f4292bd932e9cd8e0d6df.json) | Última execução integrada confirmada; CP3 `review` |

### 10.2 Diretório de diagnóstico mais recente

```text
output/cp3-depth/work/
  clip_6fb4328c422f758c2ba237afe20d3552/
    run_4059cafada6872d871e7eb2d/
      freemocap/                         # origem CP2
      retarget/cc1d507948ade4c9a498/      # último fluxo integrado
```

Arquivos para abrir:

- [Preview sincronizado](../output/cp3-depth/work/clip_6fb4328c422f758c2ba237afe20d3552/run_4059cafada6872d871e7eb2d/retarget/cc1d507948ade4c9a498/preview/index.html).
- [Animação de diagnóstico](../output/cp3-depth/work/clip_6fb4328c422f758c2ba237afe20d3552/run_4059cafada6872d871e7eb2d/retarget/cc1d507948ade4c9a498/animation.blend).
- [Metadata](../output/cp3-depth/work/clip_6fb4328c422f758c2ba237afe20d3552/run_4059cafada6872d871e7eb2d/retarget/cc1d507948ade4c9a498/metadata.json).
- [Verificação de reabertura](../output/cp3-depth/work/clip_6fb4328c422f758c2ba237afe20d3552/run_4059cafada6872d871e7eb2d/retarget/cc1d507948ade4c9a498/reopen-check.json).

Esse preview contém **172 PNGs do avatar e 172 JPGs do vídeo**. O SHA-256 atual da animação corresponde ao registrado em metadata:

```text
e8f9df9e6b3496ec9e8a6bb254c50d77711924f72b844d9a37c66d503e132189
```

A origem CP2 dessa execução está registrada com SHA-256 `7f6c38352fa75ab8985ca855fd783eba8c4a611b22e8eda9ff725727aecac5d0`. A referência de calibração com profundidade, usada no ensaio anterior, tem SHA-256 `d62660f57fce69addeb2626440d3c259c9a17eac363ff684a9e926405f550221`. Referência e execução são artefatos diferentes; não confundir os hashes.

Ensaios anteriores permanecem em `retarget/c4f5ebc3cfd7f8869755` e `retarget/183e0eb03f85a66ebb50`, além do ensaio achatado sob `output/cp3-full`. O apontador `output/cp3-validation/current-job.txt` ainda referencia `183e0eb03f85a66ebb50`. Para identificar a última execução, usar o relatório integrado acima.

## 11. Pendências concretas e ordem de retomada

1. **Concluir CP3.4:** investigar contato/forma da pose inicial e posicionamento da mão de apoio; distinguir erro de captura, escala global e adaptação de repouso. Examinar palma, dedos e polegar por mão ao longo do clip, incluindo os frames com interpolação. A evidência atual tem revisão genérica e intervalos vazios; registrar observações, intervalos e correções antes de aprovar.
2. **Revalidar calibração e árvore final:** repetir o fluxo com o hash atual do mapa e as verificações finais de compatibilidade dos eixos e de mudanças nas entradas. Se o movimento continuar inadequado, manter review. O ensaio anterior continua sendo evidência histórica válida para seus próprios hashes.
3. **Recuperar a regressão final:** repetir os testes com FFmpeg/FFprobe configurados e guardar o resultado em arquivo. Não assumir aprovação da chamada interrompida.
4. **Executar o ensaio real pela GUI:** usar o caminho normal `IngestionApp._start`, confirmar CP1→CP2→CP3 e registrar `gui-validation.json` e relatório. Cobertura por mock do worker não satisfaz esse aceite.
5. **Validar publicação real de um caso aprovado:** somente depois de uma revisão visual pass vinculada aos hashes, gerar a entrega em `output/animations/<clip-id>/<run-id>/`, conferir pacote e reabrir. Até agora houve apenas teste controlado da publicação e bloqueio correto do caso real.
6. **Consolidar documentação e operação:** atualizar plano/progresso depois dos aceites; esclarecer o alias export e a operação de revisão. Não existe, atualmente, uma tela de aprovação visual nem um comando dedicado de revisão/publicação posterior. A revisão pode ser lida de `visual-review.json` apenas quando os hashes correspondem; seu fluxo de uso ainda não foi homologado.
7. **Para o CP3 geral:** disponibilizar e mapear um rig completo para tronco/braços. A conclusão futura do protótipo das mãos não resolve essa dependência. Avaliação linguística por pessoa fluente também não foi realizada; metadata mantém `linguistic_quality_validated: false`.

Comandos preparados no código, **não executados para elaborar este relatório**:

```powershell
# Regressão com ferramentas reais; guardar a saída na retomada.
python scripts/validate_cp3.py --tests

# Fluxo CLI com profundidade e mapa padrão do CP3.
python scripts/validate_cp3.py --stage export --depth --output-dir output/cp3-depth

# Ensaio pela GUI; o script cria uma janela Tk oculta e usa o botão/worker normal.
python scripts/validate_cp3.py --frontend gui --output-dir output/cp3-gui
```

O script de ensaio tem defaults locais (`D:/blender.exe`, vídeo de referência e busca WinGet); não é um instalador portátil. A GUI utiliza o perfil com profundidade por padrão. No modo CLI desse script, solicitar retarget/export sem `--depth` combina a extração achatada com o mapa padrão com profundidade, situação que a verificação de eixos deve rejeitar; para reproduzir o caso achatado, configurar o mapa adequado explicitamente pela CLI principal.

**Estado final deste registro:** transferência e bake reais existem e são tecnicamente reabríveis; qualidade visual continua em revisão; GUI real, regressão final confirmada e entrega real aprovada permanecem pendentes. O CP3 completo não foi concluído.
