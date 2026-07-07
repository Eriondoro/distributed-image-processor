import math
from src.image_processor import get_image_dimensions


def find_grid_dimensions(n_parts):
    best_rows, best_cols = 1, n_parts
    best_diff = n_parts

    for rows in range(1, n_parts + 1):
        if n_parts % rows == 0:
            cols = n_parts // rows
            if cols >= rows:
                diff = cols - rows
                if diff < best_diff:
                    best_diff = diff
                    best_rows, best_cols = rows, cols

    return best_rows, best_cols


def partition_image_coords(image_bytes, n_parts, mode):
    w, h = get_image_dimensions(image_bytes)
    if w == 0 or h == 0:
        return []

    if mode == "1d_horizontal":
        return _split_1d_horizontal(n_parts, w, h)
    elif mode == "1d_vertical":
        return _split_1d_vertical(n_parts, w, h)
    elif mode == "2d_grid":
        if n_parts % 2 != 0:
            return _split_1d_horizontal(n_parts, w, h)
        rows, cols = find_grid_dimensions(n_parts)
        return _split_2d_grid(n_parts, w, h, rows, cols)
    else:
        return _split_1d_horizontal(n_parts, w, h)


def _split_1d_horizontal(n_parts, w, h):
    partitions = []
    part_height = h // n_parts
    for i in range(n_parts):
        y_start = i * part_height
        y_end = h if i == n_parts - 1 else (i + 1) * part_height
        partitions.append({
            "task_id": f"part_{i:04d}",
            "offset_x": 0,
            "offset_y": y_start,
            "width": w,
            "height": y_end - y_start,
            "part_index": i,
        })
    return partitions


def _split_1d_vertical(n_parts, w, h):
    partitions = []
    part_width = w // n_parts
    for i in range(n_parts):
        x_start = i * part_width
        x_end = w if i == n_parts - 1 else (i + 1) * part_width
        partitions.append({
            "task_id": f"part_{i:04d}",
            "offset_x": x_start,
            "offset_y": 0,
            "width": x_end - x_start,
            "height": h,
            "part_index": i,
        })
    return partitions


def _split_2d_grid(n_parts, w, h, rows, cols):
    partitions = []
    cell_w = w // cols
    cell_h = h // rows

    idx = 0
    for r in range(rows):
        for c in range(cols):
            x_start = c * cell_w
            y_start = r * cell_h
            x_end = w if c == cols - 1 else (c + 1) * cell_w
            y_end = h if r == rows - 1 else (r + 1) * cell_h
            partitions.append({
                "task_id": f"part_{idx:04d}",
                "offset_x": x_start,
                "offset_y": y_start,
                "width": x_end - x_start,
                "height": y_end - y_start,
                "part_index": idx,
            })
            idx += 1
    return partitions
