"""Seed Firestore model_registry: model_name + architecture JSON only."""
from __future__ import annotations
import os, sys
from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "firebase-service-account.json")

from src.db.firebase import db  # noqa: E402
from src.db.crud import create_doc, query_docs, delete_doc  # noqa: E402

COLLECTION = "model_registry"

MODELS = [
    {
        "model_name": "UNet-ResNet50",
        "architecture": {
            "type": "encoder_decoder",
            "encoder": {
                "model": "ResNet50",
                "input_shape": [512, 512, 3],
                "stem": {
                    "conv1": {"filters": 64, "kernel_size": 7, "stride": 2, "padding": 3},
                    "bn": True,
                    "relu": True,
                    "maxpool": {"kernel_size": 3, "stride": 2, "padding": 1}
                },
                "stages": [
                    {"name": "conv2_x", "blocks": 3, "bottleneck": {"filters": [64, 64, 256], "stride": 1}},
                    {"name": "conv3_x", "blocks": 4, "bottleneck": {"filters": [128, 128, 512], "stride": 2}},
                    {"name": "conv4_x", "blocks": 6, "bottleneck": {"filters": [256, 256, 1024], "stride": 2}},
                    {"name": "conv5_x", "blocks": 3, "bottleneck": {"filters": [512, 512, 2048], "stride": 2}}
                ],
                "block_structure": {
                    "type": "bottleneck",
                    "layers": [
                        {"conv": "1x1", "purpose": "reduce"},
                        {"conv": "3x3", "purpose": "process"},
                        {"conv": "1x1", "purpose": "expand"},
                        {"skip_connection": "identity or projection (1x1 conv) when shape changes"}
                    ]
                },
                "total_layers": 50,
                "total_params": "25.6M"
            },
            "decoder": {
                "type": "unet_upsampling",
                "blocks": [
                    {"up": "transposed_conv2d", "filters": 512, "skip_from": "conv4_x"},
                    {"up": "transposed_conv2d", "filters": 256, "skip_from": "conv3_x"},
                    {"up": "transposed_conv2d", "filters": 128, "skip_from": "conv2_x"},
                    {"up": "transposed_conv2d", "filters": 64, "skip_from": "stem"}
                ],
                "skip_connections": "concatenation",
                "each_block": ["upsample", "concat_skip", "conv3x3_bn_relu", "conv3x3_bn_relu"]
            },
            "head": {
                "conv1x1": {"filters": 1, "activation": "sigmoid"},
                "output_shape": [512, 512, 1]
            },
            "total_params": "32.5M"
        }
    },
    {
        "model_name": "SegFormer-B3",
        "architecture": {
            "type": "hierarchical_transformer",
            "encoder": {
                "model": "MiT-B3",
                "input_shape": [512, 512, 3],
                "patch_embedding": {
                    "stages": [
                        {"patch_size": 7, "stride": 4, "embed_dim": 64},
                        {"patch_size": 3, "stride": 2, "embed_dim": 128},
                        {"patch_size": 3, "stride": 2, "embed_dim": 320},
                        {"patch_size": 3, "stride": 2, "embed_dim": 512}
                    ],
                    "overlap": True
                },
                "transformer_blocks": [
                    {"stage": 1, "blocks": 3, "heads": 1, "embed_dim": 64, "sr_ratio": 8},
                    {"stage": 2, "blocks": 4, "heads": 2, "embed_dim": 128, "sr_ratio": 4},
                    {"stage": 3, "blocks": 18, "heads": 5, "embed_dim": 320, "sr_ratio": 2},
                    {"stage": 4, "blocks": 3, "heads": 8, "embed_dim": 512, "sr_ratio": 1}
                ],
                "attention": {
                    "type": "efficient_self_attention",
                    "sequence_reduction": True
                },
                "ffn": {
                    "type": "Mix-FFN",
                    "depthwise_conv": "3x3"
                },
                "positional_encoding": False,
                "total_params": "45.2M"
            },
            "decoder": {
                "type": "all_mlp_decode_head",
                "steps": [
                    "upsample_all_to_quarter_res",
                    "linear_project_to_256ch",
                    "concatenate",
                    "mlp_fuse",
                    "linear_classify"
                ],
                "unified_channels": 256,
                "total_params": "2.0M"
            },
            "head": {
                "linear_classifier": {"in_channels": 256, "num_classes": 1},
                "output_shape": [512, 512, 1],
                "activation": "sigmoid"
            },
            "total_params": "47.2M"
        }
    }
]


def main():
    print("Seeding model_registry...")
    existing = query_docs(COLLECTION, limit=50)
    for doc in existing:
        delete_doc(COLLECTION, doc["id"])

    for m in MODELS:
        doc_id = create_doc(COLLECTION, m)
        print(f"  {m['model_name']} -> {doc_id}")

    print("Done.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
