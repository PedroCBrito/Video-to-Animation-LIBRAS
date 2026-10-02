# Video-to-Animation LIBRAS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![FreeMoCap: pip](https://img.shields.io/badge/FreeMoCap-pip%20package-brightgreen.svg)](https://freemocap.org/)
[![Blender: 3.6+ / 5.2+](https://img.shields.io/badge/Blender-3.6%2B%20%7C%205.2%2B-orange.svg)](https://www.blender.org/)

[Português](README_PT.md)

An offline batch pipeline that turns a folder of videos of people signing in Brazilian Sign Language (LIBRAS) into animations applied to a 3D character. **V-LIBRASIL** is the reference dataset, **FreeMoCap** extracts motion, and **Blender** handles the source skeleton, retargeting, baking and export.

The goal is to automate an existing manual workflow, with each video processed as an independent job and every output traceable to its source.

## Initial scope

- Local input folder, including subfolders; one signer and recording per video.
- Torso, arms, wrists and fingers of both hands; head motion where supported.
- One reference character and a reusable rig mapping, configured once.
- Initial output: a `.blend` file with the character and baked Action, a preview and quality metadata for each technically accepted video.
- Sequential processing, isolated failures and resumable jobs.
- Detailed facial animation is a later enhancement. The MVP will explicitly report that facial animation is not validated.

The current CP3 prototype uses the supplied `animation.blend` and animates both hands and fingers. The body remains static because this avatar has no torso/arm rig. Full body and facial animation remain later work.

This project transfers motion from already-signed videos. Speech/text translation and automatic sentence composition are outside the MVP.

## Proposed workflow

```text
Video folder
  → inventory and FFmpeg preparation
  → FreeMoCap tracking and post-processing
  → extraction quality checks
  → Blender source skeleton
  → character retargeting and bake
  → animation validation and export
  → output folder and batch report
```

Use the existing FreeMoCap-to-Blender integration before considering a custom motion solver. Independent videos of the same sign are separate jobs, not synchronized camera views.

Monocular depth is estimated. Technical checks identify extraction problems; they do not certify LIBRAS intelligibility. Visual comparison and evaluation of a sample by fluent signers complement those checks. [FreeMoCap single-camera guide](https://docs.freemocap.org/documentation/single-camera-recording.html).

## Current status

CP1, CP2 and the CP3 hands prototype run through a shared CLI/Tkinter service. A real reference video produced a baked animation and synchronized preview, passed independent Blender reopening checks, and received the user's visual acceptance for both hands. Repeated CLI/GUI executions reuse the same artifacts. The prototype is closed for this scope; full body and LIBRAS linguistic validation remain separate. See the [CP3 guide and validation record](docs/cp3.md).

With the configured Python environment, FFmpeg/FFprobe and Blender available:

```powershell
python cli.py --video "./Abacaxi_Articulador1.mp4" --output-dir "E:/Video-to-Animation-LIBRAS-CP3/result"
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage inventory
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage inspect
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --until-stage verify --profile "./config/profiles/cp1-media-default.yaml"
python gui.py
```

For daily use, run `python gui.py`, select a video and output folder, then start. The CLI defaults to the complete hands prototype. Each result contains `animation.blend`, `preview.mp4` and `metadata.json`; intermediates and diagnostics stay under the output's `.pipeline/`. Inspect the preview and register a review through the GUI or CLI before promotion from `review/` to `animations/`. Repeated compatible runs verify and reuse completed artifacts. Advanced batch recovery belongs to CP5.

Processing can also stop at an earlier checkpoint:

```powershell
python cli.py --video "./video.mp4" --output-dir "./output" --until-stage verify
```

The CLI accepts `--input-dir` or `--video`. Stages are `inventory`, `inspect`, `prepare`, `session`, `verify`, `extract` and `retarget`. `export` currently aliases the CP3 `.blend` delivery; FBX/GLB and `--resume` are not implemented. Explicit `--until-stage extract` requires its extraction profile and backend contract. See the [ingestion guide](docs/ingestion.md) for partial stages.

```powershell
python cli.py --help
python cli.py --video "./video.mp4" --output-dir "./output" --until-stage verify
```

## Tools and environment

| Component | Responsibility |
|---|---|
| Python | Inventory, orchestration, configuration, reports and resume. |
| FFprobe / FFmpeg | Media inspection, decoding and preparation. |
| FreeMoCap | Motion extraction and configured post-processing. |
| MediaPipe / SkellyTracker | Tracking through the selected FreeMoCap integration. |
| SkellyForge / NumPy / SciPy | Post-processing and data analysis; SkellyForge is not the triangulation engine. |
| Blender and FreeMoCap integration | Source skeleton, retargeting, bake and export. |

The tested CP3 environment uses Python 3.12.3, FreeMoCap 1.8.2, Blender 5.2.2 LTS and AJC add-on 2026.4.1039. Direct Python integration versions are recorded in `requirements.txt`; this is not a transitive lock or a promise of compatibility with other versions.

`requirements.txt` pins the direct Python dependencies exercised in CP3. It is not a transitive environment lock. Blender, add-on and model compatibility must be verified for the selected combination. FreeMoCap migration is an explicit decision. [Official releases](https://github.com/freemocap/freemocap/releases).

Candidate Windows development setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

FFmpeg/FFprobe and Blender are external executables. Configure their paths once using environment variables or the shared local tools file described in the CP3 guide.

## Input, output and quality

Input is a local copy obtained from [V-LIBRASIL / UFPE](https://libras.cin.ufpe.br/) or another compatible collection. Inventory the actual files instead of assuming a specific count, FPS or directory layout. Preserve IDs, glosses and signer metadata when provided; filenames alone are not trusted labels.

Current CP3 output layout:

```text
output/
  animations/<clip-id>/<run-id>/animation.blend
  animations/<clip-id>/<run-id>/preview.mp4
  animations/<clip-id>/<run-id>/metadata.json
  review/<clip-id>/<run-id>/
  .pipeline/work/<clip-id>/<run-id>/
  .pipeline/reports/
  .pipeline/runtime/
  .pipeline/state.json
```

Uncertain outputs are separated for review; failures retain logs and reasons. Metadata explicitly records the lack of facial animation, including technically accepted outputs.

The initial deliverable is `.blend`. FBX and GLB come after validation in the selected consumer. A file containing an animated character and an animation-only clip are distinct delivery contracts.

## Development checkpoints

1. **CP0:** record the manual extraction baseline through the animated source skeleton.
2. **CP1:** inventory the folder and prepare compatible videos.
   CP1.0–CP1.6 implemented and tested; 3D animation generation remains in later checkpoints.
3. **CP2:** automate FreeMoCap and source skeleton generation.
4. **CP3:** supplied hands rig retargeted, baked and accepted for the prototype. Full body requires a suitable avatar.
5. **CP4:** calibrate processing profiles and quality checks.
6. **CP5:** add batch processing, failure isolation and resume.
7. **CP6:** validate delivery, consumer compatibility and performance.
8. **CP7, enhancement:** add facial animation.

See the [development plan](docs/planning.md) for acceptance criteria. Local checkpoint notes live in Git-ignored `docs/step-planning/`; shared decisions live in `docs/planning.md`.
