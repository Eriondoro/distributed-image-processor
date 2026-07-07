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


def draw_detections(image_bytes, detections, color=(0, 0, 255), thickness=2):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    for obj in detections:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)

    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def get_image_dimensions(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return 0, 0
    return img.shape[1], img.shape[0]
