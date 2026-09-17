# Video-to-Animation LIBRAS

[Português](README.md) · [Development plan (Portuguese)](docs/planning.md)

An offline batch pipeline that turns a folder of videos of people signing in Brazilian Sign Language (LIBRAS) into animations applied to a 3D character. **V-LIBRASIL** is the reference dataset, **FreeMoCap** extracts motion, and **Blender** handles the source skeleton, retargeting, baking and export.

The goal is to automate an existing manual workflow, with each video processed as an independent job and every output traceable to its source.

## Initial scope

- Local input folder, including subfolders; one signer and recording per video.
- Torso, arms, wrists and fingers of both hands; head motion where supported.
- One reference character and a reusable rig mapping, configured once.
- Initial output: a `.blend` file with the character and baked Action, a preview and quality metadata for each technically accepted video.
- Sequential processing, isolated failures and resumable jobs.
- Detailed facial animation is a later enhancement. The MVP will explicitly report that facial animation is not validated.

The user's reference animation is undergoing improvements. The character, target rig and reference animation remain undecided; extraction through the source skeleton can proceed independently. Retargeting will be validated once that material is defined.

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

This repository is at the planning and integration stage. The existing code provides a single-video CLI and initial modules. It currently checks the input path/extension and copies the file. Batch processing, normalization, corrected backend integration, quality assessment, character mapping and validated final exports remain to be implemented. The wrapper does not yet apply the processing configuration it receives.

The following is a **proposed interface, not implemented**:

```powershell
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --avatar "./assets/avatar.blend" --rig-map "./config/rig-map.yaml" --profile "./config/profiles/libras.yaml"
python cli.py --input-dir "./dataset/videos" --output-dir "./output" --avatar "./assets/avatar.blend" --rig-map "./config/rig-map.yaml" --profile "./config/profiles/libras.yaml" --resume
```

The current CLI only accepts `--video`/`-v`, `--output-dir`/`-o` and `--config`/`-c`. It is experimental and does not guarantee a complete conversion:

```powershell
python cli.py --help
python cli.py --video "./video.mp4" --output-dir "./output"
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

The inspected local reference is FreeMoCap **1.8.2**, whose package metadata specifies Python `>=3.10,<3.13`. Python **3.12** is the initial candidate. CP0 will establish the extraction environment from the manual workflow; character integration is validated in CP3.

The current `requirements.txt` uses open version ranges and is not a reproducible environment lock. Blender, add-on and model compatibility must be verified for the selected combination. FreeMoCap releases distinguish the 1.x and 2.x lines; migration is an explicit decision. [Official releases](https://github.com/freemocap/freemocap/releases).

Candidate Windows development setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

FFmpeg/ffprobe and Blender are external executables. Their versions and paths will be checked for the requested stages. [config/config.yaml](config/config.yaml) is provisional.

## Input, output and quality

Input is a local copy obtained from [V-LIBRASIL / UFPE](https://libras.cin.ufpe.br/) or another compatible collection. Inventory the actual files instead of assuming a specific count, FPS or directory layout. Preserve IDs, glosses and signer metadata when provided; filenames alone are not trusted labels.

Proposed output layout:

```text
output/
  animations/<clip-id>/<run-id>/animation.blend
  animations/<clip-id>/<run-id>/preview.mp4
  animations/<clip-id>/<run-id>/metadata.json
  review/<clip-id>/<run-id>/
  work/<clip-id>/<run-id>/
  reports/batch-<batch-id>.json
```

Uncertain outputs are separated for review; failures retain logs and reasons. Metadata explicitly records the lack of facial animation, including technically accepted outputs.

The initial deliverable is `.blend`. FBX and GLB come after validation in the selected consumer. A file containing an animated character and an animation-only clip are distinct delivery contracts.

## Development checkpoints

1. **CP0:** record the manual extraction baseline through the animated source skeleton.
2. **CP1:** inventory the folder and prepare compatible videos.
3. **CP2:** automate FreeMoCap and source skeleton generation.
4. **CP3:** configure the target rig, retarget and bake once the character is defined.
5. **CP4:** calibrate processing profiles and quality checks.
6. **CP5:** add batch processing, failure isolation and resume.
7. **CP6:** validate delivery, consumer compatibility and performance.
8. **CP7, enhancement:** add facial animation.

See the [development plan](docs/planning.md) for acceptance criteria. Local checkpoint notes live in Git-ignored `docs/step-planning/`; shared decisions live in `docs/planning.md`.

## License

Repository code is covered by the [MIT license](LICENSE). Datasets, models, dependencies and characters retain their respective licenses and terms.
