from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agent_videonote.core.config import RuntimeConfig
from agent_videonote.core.errors import ExternalToolError
from agent_videonote.media.types import MediaInfo, MediaStream


class FFmpegBackend:
    def __init__(self, config: RuntimeConfig):
        self.config = config

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise ExternalToolError(f"external tool not found: {args[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise ExternalToolError(f"external tool failed: {detail}") from exc

    def probe(self, source: str | Path) -> MediaInfo:
        source_path = Path(source).expanduser().resolve(strict=True)
        result = self._run([
            self.config.ffprobe_bin,
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(source_path),
        ])
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ExternalToolError("ffprobe returned invalid JSON") from exc

        streams: list[MediaStream] = []
        for item in payload.get("streams", []):
            streams.append(MediaStream(
                index=int(item.get("index", 0)),
                kind=str(item.get("codec_type", "unknown")),
                codec=item.get("codec_name"),
                width=item.get("width"),
                height=item.get("height"),
                sample_rate=_to_int(item.get("sample_rate")),
                channels=item.get("channels"),
                frame_rate=item.get("avg_frame_rate"),
                metadata={"tags": item.get("tags", {})},
            ))

        format_data = payload.get("format", {})
        return MediaInfo(
            path=str(source_path),
            duration=_to_float(format_data.get("duration")),
            format_name=format_data.get("format_name"),
            streams=tuple(streams),
        )

    def extract_audio(self, source: str | Path, output: str | Path) -> Path:
        output_path = _prepare_output(output)
        self._run([
            self.config.ffmpeg_bin,
            "-hide_banner", "-loglevel", "error",
            "-i", str(Path(source).expanduser().resolve(strict=True)),
            "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le",
            "-y", str(output_path),
        ])
        return output_path

    def cut_audio(
        self,
        source: str | Path,
        output: str | Path,
        *,
        start: float,
        duration: float,
        speed: float = 1.0,
    ) -> Path:
        if start < 0 or duration <= 0:
            raise ValueError("invalid audio range")
        if not 0.5 <= speed <= 2.0:
            raise ValueError("speed must be between 0.5 and 2.0")

        output_path = _prepare_output(output)
        args = [
            self.config.ffmpeg_bin,
            "-hide_banner", "-loglevel", "error",
            "-ss", f"{start:.3f}",
            "-t", f"{duration:.3f}",
            "-i", str(Path(source).expanduser().resolve(strict=True)),
            "-vn", "-ac", "1", "-ar", "16000",
        ]
        if speed != 1.0:
            args.extend(["-filter:a", f"atempo={speed:.4f}"])
        args.extend(["-c:a", "pcm_s16le", "-y", str(output_path)])
        self._run(args)
        return output_path

    def extract_frame(self, source: str | Path, output: str | Path, *, second: float) -> Path:
        if second < 0:
            raise ValueError("second must be >= 0")
        output_path = _prepare_output(output)
        self._run([
            self.config.ffmpeg_bin,
            "-hide_banner", "-loglevel", "error",
            "-ss", f"{second:.3f}",
            "-i", str(Path(source).expanduser().resolve(strict=True)),
            "-frames:v", "1",
            "-q:v", "2",
            "-y", str(output_path),
        ])
        return output_path


def _prepare_output(output: str | Path) -> Path:
    path = Path(output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _to_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
