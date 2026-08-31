"""Embedded training template for agent-generated models.

The coding agent swaps ONLY the smp.XXX(...) model constructor line.
Everything else — data loading, training loop, metrics, predictions,
JSON output — is fixed and tested to work with ANY smp model.
"""

AGENT_TRAIN_TEMPLATE = r'''#!/usr/bin/env python3
"""Agent-generated training script for binary segmentation."""

import argparse
import json
import os
import glob
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from PIL import Image

import segmentation_models_pytorch as smp

# ========================= MODEL =========================
def create_model():
    model = smp.UnetPlusPlus(encoder_name="resnet50", encoder_weights="imagenet", in_channels=3, classes=1)
    return model


# ========================= DATASET =========================
IMG_SIZE = 512


def yolo_polygon_to_mask(txt_path, h, w):
    """Convert YOLO polygon .txt to binary mask."""
    try:
        import cv2
    except ImportError:
        mask = np.zeros((h, w), dtype=np.float32)
        return mask
    mask = np.zeros((h, w), dtype=np.float32)
    if not os.path.exists(txt_path) or os.path.getsize(txt_path) == 0:
        return mask
    with open(txt_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 6:
                continue
            coords = [float(x) for x in parts[1:]]
            pts = np.array(
                [(coords[i] * w, coords[i + 1] * h) for i in range(0, len(coords) - 1, 2)],
                dtype=np.int32,
            )
            if len(pts) >= 3:
                cv2.fillPoly(mask, [pts], 1.0)
    return mask


def find_pairs(images_dir, masks_dir):
    """Find image-mask pairs. Tries edge (_mask.png), object (.txt), same-name."""
    images = sorted(glob.glob(os.path.join(images_dir, "*")))
    images = [p for p in images if p.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff"))]
    pairs = []
    for img_path in images:
        stem = os.path.splitext(os.path.basename(img_path))[0]
        for candidate in [
            os.path.join(masks_dir, f"{stem}_mask.png"),
            os.path.join(masks_dir, f"{stem}.txt"),
            os.path.join(masks_dir, f"{stem}.png"),
            os.path.join(masks_dir, f"{stem}.jpg"),
        ]:
            if os.path.exists(candidate):
                pairs.append((img_path, candidate))
                break
    return pairs


class SegDataset(Dataset):
    def __init__(self, pairs, img_size=IMG_SIZE, augment=False):
        self.pairs = pairs
        self.img_size = img_size
        self.augment = augment

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        img_path, mask_path = self.pairs[idx]

        img = Image.open(img_path).convert("RGB").resize((self.img_size, self.img_size))
        img_np = np.array(img, dtype=np.float32) / 255.0

        if mask_path.endswith(".txt"):
            mask_np = yolo_polygon_to_mask(mask_path, self.img_size, self.img_size)
        else:
            mask = Image.open(mask_path).convert("L").resize((self.img_size, self.img_size))
            mask_np = np.array(mask, dtype=np.float32)
            if mask_np.max() > 1:
                mask_np = mask_np / 255.0

        mask_np = (mask_np > 0.5).astype(np.float32)

        if self.augment and np.random.random() > 0.5:
            img_np = img_np[:, ::-1, :].copy()
            mask_np = mask_np[:, ::-1].copy()

        img_t = torch.from_numpy(img_np).permute(2, 0, 1)  # (3, H, W)
        mask_t = torch.from_numpy(mask_np).unsqueeze(0)  # (1, H, W)
        return img_t, mask_t


# ========================= METRICS =========================
def compute_metrics(preds_logits, targets):
    """Binary segmentation metrics from raw logits and binary targets.

    Args:
        preds_logits: (N, 1, H, W) raw logits (before sigmoid)
        targets: (N, 1, H, W) binary ground truth
    """
    with torch.no_grad():
        probs = torch.sigmoid(preds_logits)
        pred_bin = (probs > 0.5).float()
        tgt = (targets > 0.5).float()

        tp = (pred_bin * tgt).sum().item()
        fp = (pred_bin * (1 - tgt)).sum().item()
        fn = ((1 - pred_bin) * tgt).sum().item()
        tn = ((1 - pred_bin) * (1 - tgt)).sum().item()

        total = tp + fp + fn + tn
        pixel_accuracy = (tp + tn) / max(total, 1)
        precision = tp / max(tp + fp, 1e-7)
        recall = tp / max(tp + fn, 1e-7)
        f1 = 2 * precision * recall / max(precision + recall, 1e-7)
        iou = tp / max(tp + fp + fn, 1e-7)
        dice = 2 * tp / max(2 * tp + fp + fn, 1e-7)

    return {
        "pixel_accuracy": round(pixel_accuracy, 4),
        "mean_iou": round(iou, 4),
        "dice_score": round(dice, 4),
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }


# ========================= SAVE PREDICTIONS =========================
def save_predictions(model, val_pairs, output_dir, device, max_preds=20):
    """Save prediction overlay images for validation samples."""
    model.eval()
    pred_dir = os.path.join(output_dir, "predictions")
    os.makedirs(pred_dir, exist_ok=True)
    saved = []

    with torch.no_grad():
        for i, (img_path, _) in enumerate(val_pairs[:max_preds]):
            try:
                orig = Image.open(img_path).convert("RGB")
                orig_w, orig_h = orig.size

                inp = orig.resize((IMG_SIZE, IMG_SIZE))
                inp_t = torch.from_numpy(np.array(inp, dtype=np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0).to(device)

                logits = model(inp_t)
                prob = torch.sigmoid(logits).squeeze().cpu().numpy()
                mask_bin = (prob > 0.5).astype(np.uint8) * 255
                mask_resized = np.array(Image.fromarray(mask_bin).resize((orig_w, orig_h)))

                overlay = np.array(orig).copy()
                green = mask_resized > 127
                overlay[green, 0] = np.clip(overlay[green, 0] * 0.4, 0, 255).astype(np.uint8)
                overlay[green, 1] = np.clip(overlay[green, 1] * 0.4 + 153, 0, 255).astype(np.uint8)
                overlay[green, 2] = np.clip(overlay[green, 2] * 0.4, 0, 255).astype(np.uint8)

                out_name = f"pred_{i:04d}_{os.path.basename(img_path)}"
                Image.fromarray(overlay).save(os.path.join(pred_dir, out_name))
                saved.append(out_name)
            except Exception as e:
                print(f"Warning: prediction {i} failed: {e}")

    return saved


# ========================= TRAIN =========================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=str, default="")
    parser.add_argument("--images-dir", type=str, required=True)
    parser.add_argument("--masks-dir", type=str, required=True)
    parser.add_argument("--output-dir", type=str, required=True)
    parser.add_argument("--job-id", type=str, default="")
    parser.add_argument("--split", type=float, default=0.9)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--lr", type=float, default=0.0001)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, "predictions"), exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Data
    pairs = find_pairs(args.images_dir, args.masks_dir)
    if not pairs:
        raise RuntimeError(
            f"No image-mask pairs found. images={len(os.listdir(args.images_dir))}, masks={len(os.listdir(args.masks_dir))}. "
            f"Expected: stem_mask.png, stem.txt, or stem.png in masks dir."
        )
    print(f"Found {len(pairs)} image-mask pairs")

    n_train = max(1, int(len(pairs) * args.split))
    train_pairs = pairs[:n_train]
    val_pairs = pairs[n_train:] if n_train < len(pairs) else pairs[-1:]
    print(f"Train: {len(train_pairs)}, Val: {len(val_pairs)}")

    train_ds = SegDataset(train_pairs, augment=True)
    val_ds = SegDataset(val_pairs, augment=False)
    train_loader = DataLoader(train_ds, batch_size=min(4, len(train_pairs)), shuffle=True, num_workers=0, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=min(4, len(val_pairs)), shuffle=False, num_workers=0)

    # Model
    model = create_model().to(device)
    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    dice_loss = smp.losses.DiceLoss(mode="binary", from_logits=True)
    bce_loss = smp.losses.SoftBCEWithLogitsLoss()

    def criterion(pred, target):
        return dice_loss(pred, target) + bce_loss(pred, target)

    # Training loop
    best_val_loss = float("inf")
    best_epoch = 0
    epoch_history = []
    all_train_metrics = {}
    all_val_metrics = {}

    for epoch in range(args.epochs):
        # --- Train ---
        model.train()
        train_loss_total = 0.0
        train_preds = []
        train_tgts = []

        for images, masks in train_loader:
            images, masks = images.to(device), masks.to(device)
            logits = model(images)
            loss = criterion(logits, masks)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss_total += loss.item() * images.size(0)
            train_preds.append(logits.detach().cpu())
            train_tgts.append(masks.detach().cpu())

        train_loss = train_loss_total / len(train_pairs)
        t_metrics = compute_metrics(torch.cat(train_preds), torch.cat(train_tgts))

        # --- Val ---
        model.eval()
        val_loss_total = 0.0
        val_preds = []
        val_tgts = []

        with torch.no_grad():
            for images, masks in val_loader:
                images, masks = images.to(device), masks.to(device)
                logits = model(images)
                loss = criterion(logits, masks)
                val_loss_total += loss.item() * images.size(0)
                val_preds.append(logits.cpu())
                val_tgts.append(masks.cpu())

        val_loss = val_loss_total / len(val_pairs)
        v_metrics = compute_metrics(torch.cat(val_preds), torch.cat(val_tgts))

        epoch_history.append({
            "epoch": epoch + 1,
            "train_loss": round(train_loss, 4),
            "val_loss": round(val_loss, 4),
        })

        print(
            f"Epoch {epoch + 1}/{args.epochs} | "
            f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | "
            f"Val IoU: {v_metrics['mean_iou']:.4f} | Val Dice: {v_metrics['dice_score']:.4f} | "
            f"Val F1: {v_metrics['f1']:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch = epoch + 1
            all_train_metrics = t_metrics
            all_val_metrics = v_metrics
            torch.save(
                {"model": model.state_dict(), "epoch": best_epoch},
                os.path.join(args.output_dir, "best.pt"),
            )

    # Ensure checkpoint exists even if no improvement after epoch 1
    ckpt_path = os.path.join(args.output_dir, "best.pt")
    if not os.path.exists(ckpt_path):
        torch.save(
            {"model": model.state_dict(), "epoch": args.epochs},
            ckpt_path,
        )
        best_epoch = args.epochs
        all_train_metrics = t_metrics
        all_val_metrics = v_metrics

    # Save predictions
    pred_names = save_predictions(model, val_pairs, args.output_dir, device)

    # Save metrics.json
    results = {
        "mean_iou": all_val_metrics.get("mean_iou", 0),
        "dice_score": all_val_metrics.get("dice_score", 0),
        "pixel_accuracy": all_val_metrics.get("pixel_accuracy", 0),
        "f1": all_val_metrics.get("f1", 0),
        "precision": all_val_metrics.get("precision", 0),
        "recall": all_val_metrics.get("recall", 0),
        "epochs_trained": args.epochs,
        "best_epoch": best_epoch,
        "train_samples": len(train_pairs),
        "val_samples": len(val_pairs),
        "loss_type": "Dice + BCE",
        "train_metrics": all_train_metrics,
        "val_metrics": all_val_metrics,
        "epoch_history": epoch_history,
        "predictions": pred_names,
    }

    with open(os.path.join(args.output_dir, "metrics.json"), "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nTraining complete. Best epoch: {best_epoch}/{args.epochs}")
    print(f"Val: IoU={all_val_metrics.get('mean_iou', 0):.4f} Dice={all_val_metrics.get('dice_score', 0):.4f} F1={all_val_metrics.get('f1', 0):.4f}")
    print(f"Checkpoint saved to {ckpt_path}")


if __name__ == "__main__":
    main()
'''
