# Documentação do projeto

## Referências

- [Planejamento vigente](planning.md): escopo, arquitetura, contratos e checkpoints CP0–CP7. Esta é a referência compartilhada para implementação.
- [README do projeto](../README.md) e [versão em inglês](../README_EN.md): apresentação e distinção entre recursos existentes e propostos.

## Acompanhamento local

`docs/step-planning/` é ignorado pelo Git. Seus documentos existem no ambiente local e não acompanham um clone do repositório:

- `step-planning/progresso.md`: situação e pendências dos checkpoints.
- `step-planning/poc-1-video-ingestion.md`: detalhamento vigente do CP1; o nome do arquivo foi mantido para preservar referências.
- `step-planning/revisao-planejamento.md`: parecer consolidado e achados técnicos da revisão.

Decisões necessárias para outros desenvolvedores devem constar em `planning.md` ou em outra página compartilhada desta pasta. Atualizar o acompanhamento local quando houver implementação e registrar as verificações realmente executadas.

## Escopo confirmado

Pasta de vídeos → FreeMoCap → esqueleto animado → retargeting no Blender → pasta de animações. V-LIBRASIL é o dataset de referência; corpo e mãos são a prioridade, e rosto fica para CP7.

Personagem, rig e animação de referência permanecem indefinidos por solicitação do usuário. CP0–CP2 podem avançar até o esqueleto de origem; CP3 depende desse material. Todos os checkpoints de implementação permanecem não iniciados.
