"""Small, dependency-free grayscale features used only by visual discovery."""

from __future__ import annotations

import base64
from dataclasses import dataclass


WIDTH = 160
HEIGHT = 90
FRAME_BYTES = WIDTH * HEIGHT
TILE_COLUMNS = 8
TILE_ROWS = 5
TILE_COUNT = TILE_COLUMNS * TILE_ROWS
PREVIEW_WIDTH = 40
PREVIEW_HEIGHT = 30


@dataclass(frozen=True)
class Change:
    global_score: float
    local_score: float
    max_local_score: float
    changed_region_fraction: float
    largest_region: int


def difference(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right)) / (len(left) * 255)


def aligned_difference(left: bytes, right: bytes) -> float:
    """Compare compact previews after a bounded small zoom/pan alignment.

    The central crop avoids treating unchanged blank borders as a match.
    This is only used for plausible candidate pairs, never every sample.
    """
    if len(left) != PREVIEW_WIDTH * PREVIEW_HEIGHT or len(right) != len(left):
        raise ValueError("mismatched visual preview dimensions")
    best = 1.0
    for scale in (0.9, 0.95, 1.0, 1.05, 1.1, 1.15):
        for shift_y in (-1, 0, 1):
            for shift_x in (-1, 0, 1):
                total = count = 0
                for y in range(4, PREVIEW_HEIGHT - 4):
                    yy = round((y - 14.5) * scale + 14.5 + shift_y)
                    if not 0 <= yy < PREVIEW_HEIGHT:
                        continue
                    for x in range(5, PREVIEW_WIDTH - 5):
                        xx = round((x - 19.5) * scale + 19.5 + shift_x)
                        if 0 <= xx < PREVIEW_WIDTH:
                            total += abs(left[y * PREVIEW_WIDTH + x]
                                         - right[yy * PREVIEW_WIDTH + xx])
                            count += 1
                best = min(best, total / (count * 255))
    return best


def change(left: bytes, right: bytes, *, width: int = WIDTH,
           height: int = HEIGHT, active_threshold: float = 0.07) -> Change:
    if len(left) != len(right) or len(left) != width * height:
        raise ValueError("mismatched visual feature dimensions")
    sums = [0] * TILE_COUNT
    counts = [0] * TILE_COUNT
    total = 0
    for y in range(height):
        row = y * width
        tile_row = min(TILE_ROWS - 1, y * TILE_ROWS // height) * TILE_COLUMNS
        for x in range(width):
            delta = abs(left[row + x] - right[row + x])
            tile = tile_row + min(TILE_COLUMNS - 1, x * TILE_COLUMNS // width)
            sums[tile] += delta
            counts[tile] += 1
            total += delta
    scores = [value / (count * 255) for value, count in zip(sums, counts)]
    active = {index for index, score in enumerate(scores) if score >= active_threshold}
    unseen = set(active)
    largest = 0
    while unseen:
        stack = [unseen.pop()]
        size = 0
        while stack:
            index = stack.pop()
            size += 1
            row, column = divmod(index, TILE_COLUMNS)
            neighbors = ((row - 1, column), (row + 1, column),
                         (row, column - 1), (row, column + 1))
            for next_row, next_column in neighbors:
                if 0 <= next_row < TILE_ROWS and 0 <= next_column < TILE_COLUMNS:
                    neighbor = next_row * TILE_COLUMNS + next_column
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        stack.append(neighbor)
        largest = max(largest, size)
    return Change(
        global_score=total / (width * height * 255),
        local_score=sum(sorted(scores, reverse=True)[:3]) / 3,
        max_local_score=max(scores),
        changed_region_fraction=len(active) / TILE_COUNT,
        largest_region=largest,
    )


def preview(pixels: bytes) -> bytes:
    """40x30 block averages, small enough to keep with a candidate checkpoint."""
    if len(pixels) != FRAME_BYTES:
        raise ValueError("invalid grayscale frame dimensions")
    result = bytearray(PREVIEW_WIDTH * PREVIEW_HEIGHT)
    for y in range(PREVIEW_HEIGHT):
        for x in range(PREVIEW_WIDTH):
            total = 0
            for dy in range(3):
                offset = (y * 3 + dy) * WIDTH + x * 4
                total += sum(pixels[offset:offset + 4])
            result[y * PREVIEW_WIDTH + x] = total // 12
    return bytes(result)


def fingerprints(pixels: bytes) -> list[str]:
    """Multi-crop difference hashes tolerate small digital zooms and pans."""
    if len(pixels) != FRAME_BYTES:
        raise ValueError("invalid grayscale frame dimensions")
    result = []
    for margin in (0.0, 0.05, 0.10):
        left = round(WIDTH * margin)
        top = round(HEIGHT * margin)
        crop_width = WIDTH - 2 * left
        crop_height = HEIGHT - 2 * top
        values = []
        for y in range(9):
            center_y = top + round((y + 0.5) * crop_height / 9)
            for x in range(17):
                center_x = left + round((x + 0.5) * crop_width / 17)
                value = 0
                for dy in (-1, 0, 1):
                    row = min(HEIGHT - 1, max(0, center_y + dy)) * WIDTH
                    for dx in (-1, 0, 1):
                        value += pixels[row + min(WIDTH - 1, max(0, center_x + dx))]
                values.append(value)
        bits = 0
        for y in range(9):
            for x in range(16):
                bits = (bits << 1) | int(values[y * 17 + x] > values[y * 17 + x + 1])
        result.append(f"{bits:036x}")
    return result


def hash_distance(left: list[str], right: list[str]) -> float:
    return min((int(a, 16) ^ int(b, 16)).bit_count() / 144
               for a in left for b in right)


def encode(pixels: bytes | None) -> str | None:
    return base64.b64encode(pixels).decode("ascii") if pixels is not None else None


def decode(value: str | None) -> bytes | None:
    return base64.b64decode(value) if value else None
