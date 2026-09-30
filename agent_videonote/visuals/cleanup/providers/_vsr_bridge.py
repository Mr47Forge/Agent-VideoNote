"""Run selected VSR inpainting backends inside the Agent-VideoNote Python environment."""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path
from types import SimpleNamespace


def _value(value):
    return SimpleNamespace(value=value)


def _bootstrap(root: Path) -> None:
    if not root.is_dir():
        raise FileNotFoundError(f"VSR root not found: {root}")
    sys.path.insert(0, str(root))

    # VSR's inpainting modules import backend.config only to read a few numeric
    # options. Importing its real config would drag GUI/qfluentwidgets/Paddle
    # into our runtime, so provide the minimal compatible surface instead.
    fake = types.ModuleType("backend.config")
    fake.config = SimpleNamespace(
        sttnNeighborStride=_value(5),
        sttnReferenceLength=_value(10),
        propainterMaxLoadNum=_value(40),
        subtitleAreaDeviationPixel=_value(10),
    )
    sys.modules["backend.config"] = fake


def _device():
    import torch

    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _load_frames(paths: list[Path]):
    import cv2

    frames = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in paths]
    if any(frame is None for frame in frames):
        raise ValueError("one or more input frames are unreadable")
    return frames


def _load_mask(path: Path):
    import cv2

    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError("mask is unreadable")
    return mask


def _lama(args) -> None:
    _bootstrap(args.vsr_root)
    from PIL import Image
    from backend.inpaint.lama_inpaint import LamaInpaint

    runner = LamaInpaint(device=_device(), model_path=str(args.model))
    image = Image.open(args.image).convert("RGB")
    mask = Image.open(args.mask).convert("L")
    result = runner.inpaint(image, mask)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result).save(args.output)


def _sttn(args) -> None:
    _bootstrap(args.vsr_root)
    import cv2
    from backend.inpaint.sttn_det_inpaint import STTNDetInpaint

    frames = _load_frames(args.frame)
    mask = _load_mask(args.mask)
    runner = STTNDetInpaint(_device(), str(args.model))
    repaired = runner(frames, mask)
    index = min(len(repaired) - 1, max(0, args.target_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), repaired[index]):
        raise RuntimeError("failed to write STTN output")


def _propainter(args) -> None:
    _bootstrap(args.vsr_root)
    import cv2
    from backend.inpaint.propainter_inpaint import PropainterInpaint

    frames = _load_frames(args.frame)
    mask = _load_mask(args.mask)
    runner = PropainterInpaint(
        _device(),
        str(args.model_dir),
        sub_video_length=args.subvideo_length,
        use_fp16=args.fp16,
    )
    runner.neighbor_length = args.neighbor_length
    runner.ref_stride = args.ref_stride
    runner.raft_iter = args.raft_iter
    repaired = runner(frames, mask)
    index = min(len(repaired) - 1, max(0, args.target_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), repaired[index]):
        raise RuntimeError("failed to write ProPainter output")


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

    propainter = sub.add_parser("propainter")
    propainter.add_argument("--vsr-root", type=Path, required=True)
    propainter.add_argument("--model-dir", type=Path, required=True)
    propainter.add_argument("--mask", type=Path, required=True)
    propainter.add_argument("--output", type=Path, required=True)
    propainter.add_argument("--target-index", type=int, required=True)
    propainter.add_argument("--frame", type=Path, action="append", required=True)
    propainter.add_argument("--subvideo-length", type=int, default=40)
    propainter.add_argument("--neighbor-length", type=int, default=8)
    propainter.add_argument("--ref-stride", type=int, default=10)
    propainter.add_argument("--raft-iter", type=int, default=20)
    propainter.add_argument("--fp16", action="store_true")

    args = parser.parse_args()
    if args.backend == "lama":
        _lama(args)
    elif args.backend == "sttn":
        _sttn(args)
    else:
        _propainter(args)


if __name__ == "__main__":
    main()
