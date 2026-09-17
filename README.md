# Video-to-Animation LIBRAS: Acessibilidade 3D Open Source

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![FreeMoCap: pip](https://img.shields.io/badge/FreeMoCap-pip%20package-brightgreen.svg)](https://freemocap.org/)
[![Blender: 3.6+ / 5.2+](https://img.shields.io/badge/Blender-3.6%2B%20%7C%205.2%2B-orange.svg)](https://www.blender.org/)

[Read this README in English](README_EN.md)

O **Video-to-Animation LIBRAS** é uma iniciativa **Open Source (Código Aberto)** focada em **viabilizar a Língua Brasileira de Sinais (LIBRAS) para todos**. Através da combinação de visão computacional, captura de movimento sem marcadores (*markerless motion capture*) e computação gráfica 3D, o projeto permite converter vídeos 2D de pessoas sinalizando em animações 3D prontas para serem aplicadas em avatares virtuais.

---

## Propósito e Impacto Social

A comunidade surda no Brasil enfrenta barreiras diárias de acessibilidade na comunicação e no consumo de conteúdos digitais. A criação de animações 3D para LIBRAS tradicionalmente exige equipamentos caros de captura de movimento (como trajes sensoriais e estúdios dedicados) ou um trabalho manual exaustivo de animadores 3D.

**Nossa missão é democratizar esse processo:**
- **Inclusão Digital:** Permitir que qualquer pessoa crie avatares 3D sinalizadores a partir de vídeos gravados por câmeras comuns ou celulares.
- **LIBRAS para Todos:** Facilitar a tradução e geração de conteúdo em LIBRAS em escala para educação, sites, sistemas de atendimento e aplicativos.
- **Tecnologia Livre & Código Aberto:** Toda a arquitetura, pipeline e scripts são totalmente abertos para a comunidade global de desenvolvedores, pesquisadores e ativistas de acessibilidade.

---

## Tecnologias e Ferramentas Utilizadas

| Ferramenta / Biblioteca | Função no Projeto |
| :--- | :--- |
| **Python 3.12+** | Linguagem base para orquestração modular de todo o pipeline. |
| **FreeMoCap (via pip)** | Motor de captura de movimento *markerless* integrado como biblioteca Python nativa. |
| **MediaPipe / SkellyTracker** | Algoritmos de visão computacional para rastreamento de articulações do corpo, mãos e expressão facial em 2D. |
| **SkellyForge** | Algoritmos de triangulação espacial 3D, filtro temporal de Butterworth e travamento de extremidades (*Foot & Hand Locking*). |
| **Blender (Headless)** | Motor 3D invocado via linha de comando para retargeting de armadura, rig de personagem e exportação de animações. |
| **FFmpeg** | Manipulação, preparação, corte e validação dos arquivos de vídeo. |
| **PyYAML** | Gerenciamento centralizado de configurações e caminhos de executáveis. |

---

## Arquitetura Resumida do Pipeline

```text
[ Vídeo 2D de LIBRAS (.mp4) ]
             │
             ▼
[ 1. Ingestão & Validação (video_processor.py) ]
             │
             ▼
[ 2. Rastreamento 2D & Reconstrução 3D (freemocap_wrapper.py) ]
  ├── Detecção de poses e articulações corporais/mãos
  ├── Triangulação de coordenadas X, Y, Z
  └── Suavização por filtro Butterworth + Foot/Hand Locking
             │
             ▼
[ 3. Automação Headless no Blender (blender_exporter.py) ]
  ├── Importação de pontos e esqueleto anatômico
  ├── Retargeting automático para o Avatar 3D
  └── Exportação dos assets (.fbx, .gltf, .blend, .mp4)
             │
             ▼
[ Animação 3D Final do Avatar em LIBRAS ]
```

---

## Como Iniciar e Executar o Projeto

### 1. Pré-requisitos do Sistema
Certifique-se de ter os seguintes programas instalados:
- **Python 3.12 ou superior**
- **Blender 3.6 LTS ou superior (ex: Blender 4.x / 5.2+)**
- **FFmpeg**

> *Dica:* No Windows, você pode instalar o Blender e o FFmpeg rapidamente via WinGet:
> ```powershell
> winget install BlenderFoundation.Blender
> winget install Gyan.FFmpeg
> ```

### 2. Criação do Ambiente Virtual e Instalação
Recomenda-se criar um ambiente virtual dedicado com Python 3.12+:

```bash
# Cria e ativa o ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# Atualiza o pip e instala as dependências
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configuração
Verifique o arquivo `config/config.yaml` para garantir que o caminho do executável do Blender está correto no seu sistema:

```yaml
blender:
  executable: "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
  fallback_paths:
    - "C:/Program Files/Blender Foundation/Blender 4.3/blender.exe"
    - "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
    - "C:/Program Files/Blender Foundation/Blender 3.6/blender.exe"
```

### 4. Executando a Conversão
Para converter um vídeo de sinais em uma animação 3D, basta executar o comando na CLI:

```bash
python cli.py --video "caminho/para/video_libras.mp4" --output-dir "./output"
```

#### Argumentos disponíveis na CLI:
- `--video` / `-v`: **(Obrigatório)** Caminho para o vídeo de entrada (`.mp4`, `.mov`, `.avi`, `.mkv`).
- `--output-dir` / `-o`: Diretório de saída para salvar a animação (Padrão: `./output`).
- `--config` / `-c`: Caminho para um arquivo de configuração `.yaml` personalizado (Opcional).

Para ver a ajuda completa da CLI:
```bash
python cli.py --help
```

---

## Contribuição e Open Source

Este é um projeto **Open Source** licenciado sob a **MIT License**. Incentivamos a participação de todos os interessados em acelerar a acessibilidade digital!

### Como você pode contribuir:
- **Testando com novos vídeos em LIBRAS:** Enviando feedback sobre a precisão de sinais manuais e corporais.
- **Aprimorando o Retargeting no Blender:** Criando novos modelos de avatares 3D compatíveis.
- **Desenvolvendo melhorias de código:** Aumentando a performance de rastreamento 3D ou expandindo a CLI.

Sinta-se à vontade para abrir **Issues**, enviar **Pull Requests** ou compartilhar sugestões de melhoria.

---

<p align="center">
  Desenvolvido para promover a acessibilidade e a inclusão da comunidade surda através da tecnologia livre.
</p>
