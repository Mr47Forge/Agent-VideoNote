"""Bridge executed inside the configured VSR Python environment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap(root: Path) -> None:
    if not root.is_dir():
        raise FileNotFoundError(f"VSR root not found: {root}")
    sys.path.insert(0, str(root))


def _lama(args) -> None:
    _bootstrap(args.vsr_root)
    from PIL import Image
    from backend.inpaint.lama_inpaint import LamaInpaint

    runner = LamaInpaint(model_path=str(args.model))
    image = Image.open(args.image).convert("RGB")
    mask = Image.open(args.mask).convert("L")
    result = runner.inpaint(image, mask)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result).save(args.output)


def _sttn(args) -> None:
    _bootstrap(args.vsr_root)
    import cv2
    import torch
    from backend.inpaint.sttn_det_inpaint import STTNDetInpaint

    frames = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in args.frame]
    if any(frame is None for frame in frames):
        raise ValueError("one or more STTN frames are unreadable")
    mask = cv2.imread(str(args.mask), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError("STTN mask is unreadable")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    runner = STTNDetInpaint(device, str(args.model))
    repaired = runner(frames, mask)
    index = min(len(repaired) - 1, max(0, args.target_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), repaired[index]):
        raise RuntimeError("failed to write STTN output")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="backend", required=True)

    lama = sub.add_parser("lama")
    lama.add_argument("--vsr-root", type=Path, required=True)
    lama.add_argument("--model", type=Path, required=True)
    lama.add_argument("--image", type=Path, required=True)
    lama.add_argument("--mask", type=Path, required=True)
    lama.add_argument("--output", type=Path, required=True)

    sttn = sub.add_parser("sttn")
    sttn.add_argument("--vsr-root", type=Path, required=True)
    sttn.add_argument("--model", type=Path, required=True)
    sttn.add_argument("--mask", type=Path, required=True)
    sttn.add_argument("--output", type=Path, required=True)
    sttn.add_argument("--target-index", type=int, required=True)
    sttn.add_argument("--frame", type=Path, action="append", required=True)

    args = parser.parse_args()
    _lama(args) if args.backend == "lama" else _sttn(args)


if __name__ == "__main__":
    main()
