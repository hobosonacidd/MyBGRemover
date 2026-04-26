import os
import sys
import argparse
from pathlib import Path

import torch

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "src"))

import modnet_onnx  # noqa: E402


def load_checkpoint_safely(ckpt_path: str):
    state_dict = torch.load(ckpt_path, map_location="cpu")

    if isinstance(state_dict, dict):
        if "state_dict" in state_dict:
            state_dict = state_dict["state_dict"]

    cleaned = {}
    for key, value in state_dict.items():
        if key.startswith("module."):
            cleaned[key[len("module."):]] = value
        else:
            cleaned[key] = value

    return cleaned


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt-path", type=str, required=True)
    parser.add_argument("--output-path", type=str, required=True)
    args = parser.parse_args()

    if not os.path.exists(args.ckpt_path):
        print(f"Cannot find checkpoint path: {args.ckpt_path}")
        raise SystemExit(1)

    model = modnet_onnx.MODNet(backbone_pretrained=False)
    state_dict = load_checkpoint_safely(args.ckpt_path)
    model.load_state_dict(state_dict, strict=True)
    model.eval()

    dummy_input = torch.randn(1, 3, 512, 512, dtype=torch.float32)

    with torch.no_grad():
        torch.onnx.export(
            model,
            dummy_input,
            args.output_path,
            export_params=True,
            opset_version=11,
            do_constant_folding=True,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={
                "input": {0: "batch_size", 2: "height", 3: "width"},
                "output": {0: "batch_size", 2: "height", 3: "width"},
            },
        )

    print(f"Saved ONNX model to: {args.output_path}")
