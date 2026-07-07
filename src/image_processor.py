import time
import cv2
import numpy as np


def detect_red_objects(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([179, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 50:
            x, y, w, h = cv2.boundingRect(cnt)
            results.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})

    return results


def detect_red_in_chunk(image_bytes, offset_x, offset_y, width, height):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    h, w = img.shape[:2]
    y1 = max(0, offset_y)
    y2 = min(h, offset_y + height)
    x1 = max(0, offset_x)
    x2 = min(w, offset_x + width)

    if y2 <= y1 or x2 <= x1:
        return []

    chunk = img[y1:y2, x1:x2]

    t0 = time.perf_counter()
    objects = detect_red_objects(cv2.imencode(".png", chunk)[1].tobytes())
    elapsed = time.perf_counter() - t0

    for obj in objects:
        obj["x"] += x1
        obj["y"] += y1

    return objects, elapsed


def draw_result(image_bytes, partitions, detections, box_color=(0, 0, 255), box_thickness=2):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    partition_has_red = set()
    for det in detections:
        cx, cy = det["x"] + det["w"] // 2, det["y"] + det["h"] // 2
        for p in partitions:
            x, y, w, h = p["offset_x"], p["offset_y"], p["width"], p["height"]
            if x <= cx <= x + w and y <= cy <= y + h:
                partition_has_red.add(p["task_id"])
                break

    for p in partitions:
        x, y, w, h = p["offset_x"], p["offset_y"], p["width"], p["height"]
        cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), (255, 255, 255), 1)
        if p["task_id"] in partition_has_red:
            overlay = img.copy()
            cv2.rectangle(overlay, (x, y), (x + w - 1, y + h - 1), (0, 0, 200), -1)
            cv2.addWeighted(overlay, 0.15, img, 0.85, 0, img)
            cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), (0, 0, 255), 2)
            label = f"#{p.get('part_index', '?')}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x, y - th - 4), (x + tw + 4, y), (0, 0, 255), -1)
            cv2.putText(img, label, (x + 2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    for obj in detections:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        cv2.rectangle(img, (x, y), (x + w, y + h), box_color, box_thickness)

    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def get_image_dimensions(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return 0, 0
    return img.shape[1], img.shape[0]
