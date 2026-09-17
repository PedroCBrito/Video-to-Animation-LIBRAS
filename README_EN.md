# Video-to-Animation LIBRAS: Open Source 3D Accessibility

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![FreeMoCap: pip](https://img.shields.io/badge/FreeMoCap-pip%20package-brightgreen.svg)](https://freemocap.org/)
[![Blender: 3.6+ / 5.2+](https://img.shields.io/badge/Blender-3.6%2B%20%7C%205.2%2B-orange.svg)](https://www.blender.org/)

**Video-to-Animation LIBRAS** is an **Open Source** initiative aimed at **making LIBRAS (Brazilian Sign Language) accessible to everyone**. By combining computer vision, markerless motion capture, and 3D computer graphics, this project enables converting 2D videos of people signing into ready-to-use 3D animations for virtual avatars.

---

## Purpose and Social Impact

The deaf community in Brazil faces daily accessibility barriers in communication and digital content consumption. Creating 3D animations for LIBRAS traditionally requires expensive motion capture equipment (such as sensory suits and dedicated studios) or painstaking manual work by 3D animators.

**Our mission is to democratize this process:**
- **Digital Inclusion:** Allow anyone to create signing 3D avatars from videos recorded using standard cameras or smartphones.
- **LIBRAS for Everyone:** Facilitate large-scale translation and content generation in LIBRAS for education, websites, customer service systems, and apps.
- **Free Technology & Open Source:** The entire architecture, pipeline, and scripts are fully open to the global community of developers, researchers, and accessibility advocates.

---

## Technologies and Tools Used

| Tool / Library | Function in the Project |
| :--- | :--- |
| **Python 3.12+** | Core language for modular orchestration of the entire pipeline. |
| **FreeMoCap (via pip)** | Markerless motion capture engine integrated as a native Python library. |
| **MediaPipe / SkellyTracker** | Computer vision algorithms for tracking 2D body, hand, and facial keypoints. |
| **SkellyForge** | 3D spatial triangulation, Butterworth temporal filtering, and extremity lock algorithms (*Foot & Hand Locking*). |
| **Blender (Headless)** | 3D engine invoked via command line for armature retargeting, character rigging, and animation export. |
| **FFmpeg** | Processing, preparation, trimming, and validation of video files. |
| **PyYAML** | Centralized configuration management for paths and parameters. |

---

## Summary of the Pipeline Architecture

```text
[ 2D LIBRAS Video (.mp4) ]
             │
             ▼
[ 1. Ingestion & Validation (video_processor.py) ]
             │
             ▼
[ 2. 2D Tracking & 3D Reconstruction (freemocap_wrapper.py) ]
  ├── Pose, body joint, and hand detection
  ├── Triangulation of X, Y, Z spatial coordinates
  └── Butterworth filter smoothing + Foot/Hand Locking
             │
             ▼
[ 3. Headless Automation in Blender (blender_exporter.py) ]
  ├── Importing 3D points and anatomical skeleton
  ├── Automatic retargeting to the 3D Avatar
  └── Asset export (.fbx, .gltf, .blend, .mp4)
             │
             ▼
[ Final 3D LIBRAS Avatar Animation ]
```

---

## How to Start and Run the Project

### 1. System Prerequisites
Ensure the following software is installed on your operating system:
- **Python 3.12 or higher**
- **Blender 3.6 LTS or higher (e.g., Blender 4.x / 5.2+)**
- **FFmpeg**

> *Tip:* On Windows, you can quickly install Blender and FFmpeg via WinGet:
> ```powershell
> winget install BlenderFoundation.Blender
> winget install Gyan.FFmpeg
> ```

### 2. Virtual Environment Setup & Installation
Create a dedicated virtual environment with Python 3.12+:

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configuration
Check the `config/config.yaml` file to ensure the path for the Blender executable is correct on your system:

```yaml
blender:
  executable: "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
  fallback_paths:
    - "C:/Program Files/Blender Foundation/Blender 4.3/blender.exe"
    - "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
    - "C:/Program Files/Blender Foundation/Blender 3.6/blender.exe"
```

### 4. Running the Conversion
To convert a sign language video into a 3D animation, run the CLI command:

```bash
python cli.py --video "path/to/libras_video.mp4" --output-dir "./output"
```

#### Available CLI Arguments:
- `--video` / `-v`: **(Required)** Path to the input video file (`.mp4`, `.mov`, `.avi`, `.mkv`).
- `--output-dir` / `-o`: Output directory for saving the animation (Default: `./output`).
- `--config` / `-c`: Path to a custom `.yaml` configuration file (Optional).

To view full CLI help:
```bash
python cli.py --help
```

---

## Contribution and Open Source

This project is **Open Source** under the **MIT License**. We welcome participation from anyone interested in advancing digital accessibility!

### How you can contribute:
- **Testing with new LIBRAS videos:** Providing feedback on manual and body sign precision.
- **Improving Blender Retargeting:** Creating compatible new 3D avatar character rigs.
- **Code enhancements:** Improving 3D tracking performance or extending CLI features.

Feel free to open **Issues**, submit **Pull Requests**, or share suggestions for improvement.

---

<p align="center">
  Developed to promote accessibility and inclusion for the deaf community through open technology.
</p>
