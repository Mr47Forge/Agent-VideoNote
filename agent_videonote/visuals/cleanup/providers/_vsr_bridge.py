"""Run selected VSR inpainting backends inside the Agent-VideoNote Python environment."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
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


def _composite_masked(original, generated, mask):
    """Keep every pixel outside the explicit user mask from the true target frame."""
    import numpy as np

    if original.shape != generated.shape or original.shape[:2] != mask.shape[:2]:
        raise ValueError("inpaint output and explicit mask must match target frame dimensions")
    return np.where(mask[:, :, None] > 0, generated, original)


def _gpu_snapshot() -> dict[str, float | bool | None]:
    import torch

    if not torch.cuda.is_available():
        return {"cuda_used": False, "free_mib": None, "allocated_mib": None,
                "peak_allocated_mib": None}
    mib = 1024 * 1024
    return {
        "cuda_used": True,
        "free_mib": round(torch.cuda.mem_get_info()[0] / mib, 1),
        "allocated_mib": round(torch.cuda.memory_allocated() / mib, 1),
        "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / mib, 1),
    }


def _emit_metrics(backend: str, start: float, loaded: float,
                  inferred: float, before: dict[str, float | bool | None],
                  after_load: dict[str, float | bool | None]) -> None:
    import torch

    peak = _gpu_snapshot()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    released = _gpu_snapshot()
    payload = {
        "backend": backend,
        "load_seconds": round(loaded - start, 3),
        "inference_seconds": round(inferred - loaded, 3),
        "gpu_free_mib_before": before["free_mib"],
        "gpu_allocated_mib_after_load": after_load["allocated_mib"],
        "gpu_peak_allocated_mib": peak["peak_allocated_mib"],
        "gpu_allocated_mib_after_release": released["allocated_mib"],
        "gpu_free_mib_after": released["free_mib"],
        "cuda_used": before["cuda_used"],
    }
    print("AGENT_VIDEONOTE_METRICS=" + json.dumps(payload), file=sys.stderr)


def _lama(args) -> None:
    _bootstrap(args.vsr_root)
    from PIL import Image
    from backend.inpaint.lama_inpaint import LamaInpaint

    before = _gpu_snapshot()
    if before["cuda_used"]:
        import torch
        torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    runner = LamaInpaint(device=_device(), model_path=str(args.model))
    loaded = time.perf_counter()
    after_load = _gpu_snapshot()
    image = Image.open(args.image).convert("RGB")
    mask = Image.open(args.mask).convert("L")
    result = runner.inpaint(image, mask)
    inferred = time.perf_counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    import numpy as np
    protected = _composite_masked(np.asarray(image), result, np.asarray(mask))
    Image.fromarray(protected).save(args.output)
    del runner
    _emit_metrics("lama", start, loaded, inferred, before, after_load)


def _sttn(args) -> None:
    _bootstrap(args.vsr_root)
    import cv2
    from backend.inpaint.sttn_det_inpaint import STTNDetInpaint

    frames = _load_frames(args.frame)
    mask = _load_mask(args.mask)
    before = _gpu_snapshot()
    if before["cuda_used"]:
        import torch
        torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    runner = STTNDetInpaint(_device(), str(args.model))
    loaded = time.perf_counter()
    after_load = _gpu_snapshot()
    repaired = runner(frames, mask)
    inferred = time.perf_counter()
    index = min(len(repaired) - 1, max(0, args.target_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    protected = _composite_masked(frames[index], repaired[index], mask)
    if not cv2.imwrite(str(args.output), protected):
        raise RuntimeError("failed to write STTN output")
    del runner
    _emit_metrics("sttn", start, loaded, inferred, before, after_load)


def _propainter(args) -> None:
    _bootstrap(args.vsr_root)
    import cv2
    from backend.inpaint.propainter_inpaint import PropainterInpaint

    frames = _load_frames(args.frame)
    mask = _load_mask(args.mask)
    before = _gpu_snapshot()
    if before["cuda_used"]:
        import torch
        torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    runner = PropainterInpaint(
        _device(),
        str(args.model_dir),
        sub_video_length=args.subvideo_length,
        use_fp16=args.fp16,
    )
    runner.neighbor_length = args.neighbor_length
    runner.ref_stride = args.ref_stride
    runner.raft_iter = args.raft_iter
    loaded = time.perf_counter()
    after_load = _gpu_snapshot()
    repaired = runner(frames, mask)
    inferred = time.perf_counter()
    index = min(len(repaired) - 1, max(0, args.target_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    protected = _composite_masked(frames[index], repaired[index], mask)
    if not cv2.imwrite(str(args.output), protected):
        raise RuntimeError("failed to write ProPainter output")
    del runner
    _emit_metrics("propainter", start, loaded, inferred, before, after_load)


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
