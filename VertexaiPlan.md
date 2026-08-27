# Agent-Generated Training Pipeline — Simple Plan

## Core Idea

The Research Agent already generates a report recommending an architecture. The next step is simple:

**Agent writes a training script → uploads to GCS → user clicks "Train" → VM runs it (same as existing finetune flow)**

No Vertex AI needed. No new infrastructure. We reuse everything we already have.

---

## Flow

```
Research Report (already done)
        ↓
User clicks "Generate Training Code"
        ↓
Backend calls Gemini with:
  - The research report
  - architecture.json (model context)
  - A code generation prompt
        ↓
Gemini generates a standalone training script (Python)
        ↓
Backend uploads script to GCS: gs://terafac-datasets/agent-scripts/{user_id}/{job_name}/train.py
        ↓
Backend registers as a new model entry with finetune_script pointing to GCS
        ↓
User proceeds to normal finetune flow (upload data → train)
        ↓
VM downloads script from GCS + runs it (same SSH flow as existing models)
```

---

## What Needs to Change

### Backend (1 new endpoint)

**`POST /research/generate-code`**

Input: `{ report: string, job_name: string }`

1. Calls Gemini with the report + a code-gen prompt:
   - "Based on this research report, generate a standalone PyTorch training script"
   - "Script must accept: --model-path, --images-dir, --masks-dir, --output-dir, --job-id, --split"
   - "Script must output: best.pt checkpoint + metrics.json + predictions/ folder"
   - "Use only pip-installable libraries (segmentation-models-pytorch, transformers, timm, albumentations)"
   - "Include the full model architecture inline (no external imports)"
2. Uploads generated script to GCS
3. Registers in `user_models` table with `finetune_script` pointing to GCS path
4. Returns: `{ model_name, script_path }`

### Frontend (1 button after report)

After research report shows:
- Button: **"Generate Training Code"**
- On success: toast "Training script generated! Select it from the model list to start fine-tuning"
- The new model appears in the finetune model dropdown

### VM (maybe pip install)

The generated script may need libraries not in the venv. Two options:

**Option A (simple):** Add a pip install step in the SSH bash script before running:
```bash
$VENV -m pip install segmentation-models-pytorch transformers timm mmseg albumentations --quiet
```

**Option B (pre-install):** SSH to VM once and install all common libs:
```bash
pip install segmentation-models-pytorch transformers timm albumentations opencv-python scikit-image
```

Option B is better — do it once, no per-job delay.

---

## Implementation Steps (1 day)

| Step | Time | What |
|------|------|------|
| 1 | 30 min | Pre-install common libs on VM venv |
| 2 | 1 hr | Backend endpoint: call Gemini for code gen + upload to GCS |
| 3 | 30 min | Frontend: "Generate Training Code" button after report |
| 4 | 30 min | Test: generate script → verify it uploads → run finetune |
| 5 | 30 min | Debug & fix any script format issues |
| **Total** | **~3 hrs** | |

---

## Gemini Code Generation Prompt (key part)

```
Based on this research report, generate a complete standalone PyTorch training script.

REQUIREMENTS:
- Accept CLI args: --model-path (pretrained weights or empty for fresh), --images-dir, --masks-dir, --output-dir, --job-id, --split (default 0.9)
- Save best checkpoint as output_dir/best.pt
- Save metrics.json with: mean_iou, dice_score, pixel_accuracy, epochs_trained, train_metrics, val_metrics, epoch_history, predictions list
- Save val prediction overlays in output_dir/predictions/
- Use ONLY pip-installable libraries: torch, torchvision, segmentation-models-pytorch, albumentations, timm, transformers, opencv-python, scikit-image, numpy, PIL
- Include the FULL model architecture inline — no external model files needed
- Handle both object masks (.txt YOLO format) and edge masks (_mask.png binary) based on what's in masks_dir
- GPU training with AMP
- The script must be completely self-contained and runnable as: python train.py --images-dir ... --masks-dir ... --output-dir ... --job-id ...
```

---

## Why This Works

- **No new infrastructure** — uses existing GCS + SSH + VM
- **No new services** — Gemini already integrated
- **Same finetune flow** — user sees it as another model in the dropdown
- **Flexible** — agent can generate ANY architecture (not limited to our 4)
- **Testable** — generated script is just a Python file, can be inspected before running

---

## Risk: Generated Code Might Fail

Mitigation:
- Gemini is good at generating training scripts but may have bugs
- User can download and inspect the script before running
- If training fails, error message shows in the UI (same as any failed job)
- Future: add a "validate script" step that does a dry-run with 1 image
