# Documentação do projeto

## Referências

- [Planejamento vigente](planning.md): escopo, arquitetura, contratos e checkpoints CP0–CP7. Esta é a referência compartilhada para implementação.
- [Uso da ingestão](ingestion.md): comandos e tela Tkinter de CP1.0–CP1.6, preparação, sessões, relatórios, metadados e testes.
- [Protótipo CP3](cp3.md): vídeo até animação das duas mãos, CLI/GUI, organização da saída, revisão e validações reais.
- [Revisão do CP3 e entrada no CP4](cp3-review-2026-10-03.md): critérios, correção do serviço de revisão e validação posterior ao commit.
- [Revisão antes do CP4](repository-cleanup.md): limpeza dos ensaios antigos, arquivos preservados e evidências compartilhadas.
- [Estado anterior do CP3](relatorio-cp3-estado-2026-10-02.md): diagnóstico preservado anterior à implementação desta retomada.
- [README do projeto](../README.md) e [versão em português](../README_PT.md): apresentação e distinção entre recursos existentes e propostos.

## Acompanhamento local

`docs/step-planning/` é ignorado pelo Git. Seus documentos existem no ambiente local e não acompanham um clone do repositório:

- `step-planning/progresso.md`: situação e pendências dos checkpoints.

Decisões necessárias para outros desenvolvedores devem constar em `planning.md` ou em outra página compartilhada desta pasta. Atualizar o acompanhamento local quando houver implementação e registrar as verificações realmente executadas.

## Escopo confirmado

Pasta de vídeos → FreeMoCap → esqueleto animado → retargeting no Blender → pasta de animações. V-LIBRASIL é o dataset de referência; corpo e mãos são a prioridade, e rosto fica para CP7.

O `animation.blend` fornecido é o destino do protótipo CP3 autorizado: ambas as mãos e dedos animados, corpo estático. CP1→CP2→CP3 foi exercitado com vídeo real, bake, reabertura e reuso CLI/GUI. A referência recebeu aceite visual explícito do usuário, registrado e publicado. O protótipo está fechado; rig corporal, calibração geral, lote avançado e avaliação linguística permanecem separados.
