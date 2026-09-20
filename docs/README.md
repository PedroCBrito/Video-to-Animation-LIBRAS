# Documentação do projeto

## Referências

- [Planejamento vigente](planning.md): escopo, arquitetura, contratos e checkpoints CP0–CP7. Esta é a referência compartilhada para implementação.
- [Uso da ingestão](ingestion.md): comandos e tela Tkinter de CP1.0–CP1.6, preparação, sessões, relatórios, metadados e testes.
- [README do projeto](../README.md) e [versão em português](../README_PT.md): apresentação e distinção entre recursos existentes e propostos.

## Acompanhamento local

`docs/step-planning/` é ignorado pelo Git. Seus documentos existem no ambiente local e não acompanham um clone do repositório:

- `step-planning/progresso.md`: situação e pendências dos checkpoints.

Decisões necessárias para outros desenvolvedores devem constar em `planning.md` ou em outra página compartilhada desta pasta. Atualizar o acompanhamento local quando houver implementação e registrar as verificações realmente executadas.

## Escopo confirmado

Pasta de vídeos → FreeMoCap → esqueleto animado → retargeting no Blender → pasta de animações. V-LIBRASIL é o dataset de referência; corpo e mãos são a prioridade, e rosto fica para CP7.

Personagem, rig e animação de referência permanecem indefinidos por solicitação do usuário. CP0–CP2 podem avançar até o esqueleto de origem; CP3 depende desse material. CP1.0–CP1.6 e CP2.0–CP2.6 estão implementados em contratos e testes controlados; a execução real de FreeMoCap/Blender permanece pendente.
