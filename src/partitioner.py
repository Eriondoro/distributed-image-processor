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
        if n_parts < 4:
            return _split_1d_horizontal(n_parts, w, h)
        rows, cols = find_grid_dimensions(n_parts)
        if rows < 2 or cols < 2:
            return _split_1d_horizontal(n_parts, w, h)
        return _split_2d_grid(n_parts, w, h, rows, cols)
    else:
        return _split_1d_horizontal(n_parts, w, h)


def _split_1d_horizontal(n_parts, w, h):
    base = h // n_parts
    remainder = h % n_parts
    partitions = []
    y = 0
    for i in range(n_parts):
        part_h = base + (1 if i < remainder else 0)
        partitions.append({
            "task_id": f"part_{i:04d}",
            "offset_x": 0,
            "offset_y": y,
            "width": w,
            "height": part_h,
            "part_index": i,
        })
        y += part_h
    return partitions


def _split_1d_vertical(n_parts, w, h):
    base = w // n_parts
    remainder = w % n_parts
    partitions = []
    x = 0
    for i in range(n_parts):
        part_w = base + (1 if i < remainder else 0)
        partitions.append({
            "task_id": f"part_{i:04d}",
            "offset_x": x,
            "offset_y": 0,
            "width": part_w,
            "height": h,
            "part_index": i,
        })
        x += part_w
    return partitions


def _split_2d_grid(n_parts, w, h, rows, cols):
    base_w = w // cols
    rem_w = w % cols
    base_h = h // rows
    rem_h = h % rows

    col_widths = [base_w + (1 if c < rem_w else 0) for c in range(cols)]
    row_heights = [base_h + (1 if r < rem_h else 0) for r in range(rows)]

    col_positions = [0]
    for cw in col_widths:
        col_positions.append(col_positions[-1] + cw)

    row_positions = [0]
    for rh in row_heights:
        row_positions.append(row_positions[-1] + rh)

    partitions = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            partitions.append({
                "task_id": f"part_{idx:04d}",
                "offset_x": col_positions[c],
                "offset_y": row_positions[r],
                "width": col_widths[c],
                "height": row_heights[r],
                "part_index": idx,
            })
            idx += 1
    return partitions
