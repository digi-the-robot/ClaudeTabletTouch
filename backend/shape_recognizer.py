"""
Shape Recognizer — $1 Unistroke Recognizer implementation.

Recognizes drawn shapes by comparing resampled, normalized stroke paths
against templates. Supports custom user-recorded templates saved to
templates.json, with built-in fallbacks.

Based on: Wobbrock, Wilson, Li (2007) — "Gestures without Libraries,
Toolkits or Training: A $1 Recognizer for User Interface Prototypes"
"""

import json
import math
import os
import logging

logger = logging.getLogger("tablet-touch.shapes")

TEMPLATES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "templates.json"
)

SHAPE_NAMES = ["heart", "circle", "star", "infinity", "check", "spiral", "moon"]

# --- Configuration ---

NUM_POINTS = 64          # Resample target
SQUARE_SIZE = 250.0      # Reference bounding box size
ANGLE_RANGE = math.radians(45)
ANGLE_STEP = math.radians(2)
HALF_DIAGONAL = math.sqrt(SQUARE_SIZE ** 2 + SQUARE_SIZE ** 2) / 2
PHI = 0.5 * (-1 + math.sqrt(5))  # Golden ratio


# --- Core $1 Algorithm ---

def _distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _path_length(points):
    total = 0.0
    for i in range(1, len(points)):
        total += _distance(points[i - 1], points[i])
    return total


def _centroid(points):
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return (cx, cy)


def _bounding_box(points):
    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    return (min_x, min_y, max_x - min_x, max_y - min_y)


def resample(points, n):
    """Resample a path to n evenly-spaced points."""
    if len(points) < 2:
        return points[:]

    total = _path_length(points)
    if total == 0:
        return [points[0]] * n

    interval = total / (n - 1)
    new_points = [points[0]]
    dist_so_far = 0.0
    i = 1

    while i < len(points) and len(new_points) < n:
        d = _distance(points[i - 1], points[i])
        if dist_so_far + d >= interval:
            ratio = (interval - dist_so_far) / d if d > 0 else 0
            qx = points[i - 1][0] + ratio * (points[i][0] - points[i - 1][0])
            qy = points[i - 1][1] + ratio * (points[i][1] - points[i - 1][1])
            new_points.append((qx, qy))
            points = [new_points[-1]] + points[i:]
            i = 1
            dist_so_far = 0.0
        else:
            dist_so_far += d
            i += 1

    # Pad if we ended up short
    while len(new_points) < n:
        new_points.append(points[-1])

    return new_points[:n]


def _indicative_angle(points):
    c = _centroid(points)
    return math.atan2(c[1] - points[0][1], c[0] - points[0][0])


def rotate_by(points, angle):
    """Rotate points around their centroid by a given angle."""
    c = _centroid(points)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    result = []
    for p in points:
        dx = p[0] - c[0]
        dy = p[1] - c[1]
        result.append((
            dx * cos_a - dy * sin_a + c[0],
            dx * sin_a + dy * cos_a + c[1],
        ))
    return result


def scale_to(points, size):
    """Scale points to fit within a size x size bounding box."""
    bb = _bounding_box(points)
    w = bb[2] if bb[2] > 0 else 1
    h = bb[3] if bb[3] > 0 else 1
    return [(p[0] * size / w, p[1] * size / h) for p in points]


def translate_to(points, target):
    """Translate points so their centroid is at the target point."""
    c = _centroid(points)
    return [(p[0] + target[0] - c[0], p[1] + target[1] - c[1]) for p in points]


def _path_distance(a, b):
    """Average distance between corresponding points of two paths."""
    total = sum(_distance(a[i], b[i]) for i in range(len(a)))
    return total / len(a)


def _distance_at_angle(points, template, angle):
    rotated = rotate_by(points, angle)
    return _path_distance(rotated, template)


def _distance_at_best_angle(points, template):
    """Golden section search for the angle that minimizes path distance."""
    a = -ANGLE_RANGE
    b = ANGLE_RANGE
    x1 = PHI * a + (1 - PHI) * b
    x2 = (1 - PHI) * a + PHI * b
    f1 = _distance_at_angle(points, template, x1)
    f2 = _distance_at_angle(points, template, x2)

    while abs(b - a) > ANGLE_STEP:
        if f1 < f2:
            b = x2
            x2 = x1
            f2 = f1
            x1 = PHI * a + (1 - PHI) * b
            f1 = _distance_at_angle(points, template, x1)
        else:
            a = x1
            x1 = x2
            f1 = f2
            x2 = (1 - PHI) * a + PHI * b
            f2 = _distance_at_angle(points, template, x2)

    return min(f1, f2)


def _normalize(points):
    """Apply the full $1 normalization pipeline."""
    pts = resample(points, NUM_POINTS)
    angle = _indicative_angle(pts)
    pts = rotate_by(pts, -angle)
    pts = scale_to(pts, SQUARE_SIZE)
    pts = translate_to(pts, (0, 0))
    return pts


def recognize(points, templates):
    """
    Recognize a stroke against a set of templates.

    Args:
        points: list of (x, y) tuples
        templates: list of (name, normalized_points) tuples

    Returns:
        (name, confidence) or (None, 0.0) if no match
    """
    if len(points) < 5:
        return None, 0.0

    candidate = _normalize(points)

    best_dist = float("inf")
    best_name = None

    for name, template_pts in templates:
        dist = _distance_at_best_angle(candidate, template_pts)
        if dist < best_dist:
            best_dist = dist
            best_name = name

    # Convert distance to confidence score (0-1)
    score = 1.0 - best_dist / HALF_DIAGONAL
    score = max(0.0, min(1.0, score))

    return best_name, score


# --- Built-in fallback templates ---
# Used when no custom templates exist for a shape.

def _builtin_circle(n=32):
    return [
        (0.5 + 0.5 * math.sin(2 * math.pi * i / n),
         0.5 - 0.5 * math.cos(2 * math.pi * i / n))
        for i in range(n + 1)
    ]

def _builtin_heart():
    pts = []
    n = 50
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
        pts.append((x / 34 + 0.5, y / 34 + 0.4))
    return pts

def _builtin_star():
    indices = [0, 2, 4, 1, 3, 0]
    return [
        (0.5 + 0.5 * math.cos(math.pi * 2 * i / 5 - math.pi / 2),
         0.5 + 0.5 * math.sin(math.pi * 2 * i / 5 - math.pi / 2))
        for i in indices
    ]

def _builtin_check():
    return [(0.0, 0.5), (0.35, 1.0), (1.0, 0.0)]

def _builtin_x():
    return [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5), (1.0, 0.0), (0.0, 1.0)]

def _builtin_spiral(n=64):
    pts = []
    for i in range(n):
        t = i / n * 4 * math.pi
        r = 0.05 + 0.45 * (i / n)
        pts.append((0.5 + r * math.sin(t), 0.5 - r * math.cos(t)))
    return pts

def _builtin_moon():
    return [(0.0, 0.0), (0.25, 1.0), (0.5, 0.0), (0.75, 1.0), (1.0, 0.0)]


_BUILTIN_TEMPLATES = [
    ("heart",  _builtin_heart()),
    ("circle", _builtin_circle()),
    ("circle", _builtin_circle()[::-1]),  # counter-clockwise
    ("star",   _builtin_star()),
    ("infinity",      _builtin_x()),
    ("check",  _builtin_check()),
    ("spiral", _builtin_spiral()),
    ("moon", _builtin_moon()),
]

_BUILTIN_NORMALIZED = [(name, _normalize(pts)) for name, pts in _BUILTIN_TEMPLATES]


# --- Custom template management ---

_custom_templates: dict[str, list[list[tuple]]] = {}  # {shape: [normalized_points, ...]}


def _load_custom_templates():
    """Load custom templates from templates.json if it exists."""
    global _custom_templates
    if os.path.exists(TEMPLATES_PATH):
        try:
            with open(TEMPLATES_PATH, "r") as f:
                raw = json.load(f)
            _custom_templates = {
                name: [[tuple(p) for p in sample] for sample in samples]
                for name, samples in raw.items()
            }
            total = sum(len(v) for v in _custom_templates.values())
            logger.info(f"Loaded {total} custom templates from templates.json")
        except Exception as e:
            logger.error(f"Failed to load templates.json: {e}")
            _custom_templates = {}
    else:
        _custom_templates = {}


def _save_custom_templates():
    """Save custom templates to templates.json."""
    try:
        # Convert tuples to lists for JSON serialization
        raw = {
            name: [list(list(p) for p in sample) for sample in samples]
            for name, samples in _custom_templates.items()
        }
        with open(TEMPLATES_PATH, "w") as f:
            json.dump(raw, f, indent=2)
        logger.info(f"Saved custom templates to templates.json")
    except Exception as e:
        logger.error(f"Failed to save templates.json: {e}")


def save_template(shape_name: str, points: list[dict]) -> bool:
    """
    Record a custom template from user-drawn stroke points.

    Args:
        shape_name: one of SHAPE_NAMES
        points: list of dicts with 'x' and 'y' keys

    Returns:
        True if saved successfully
    """
    if shape_name not in SHAPE_NAMES:
        logger.warning(f"Unknown shape name: {shape_name}")
        return False

    if len(points) < 5:
        logger.warning("Too few points for a template")
        return False

    xy_points = [(p["x"], p["y"]) for p in points]
    normalized = _normalize(xy_points)

    if shape_name not in _custom_templates:
        _custom_templates[shape_name] = []
    _custom_templates[shape_name].append(normalized)

    _save_custom_templates()
    logger.info(f"Saved template for '{shape_name}' ({len(_custom_templates[shape_name])} total)")
    return True


def delete_templates(shape_name: str = None) -> bool:
    """
    Delete custom templates. If shape_name given, delete only that shape.
    If None, delete all custom templates.
    """
    if shape_name:
        if shape_name in _custom_templates:
            del _custom_templates[shape_name]
    else:
        _custom_templates.clear()
    _save_custom_templates()
    return True


def get_template_counts() -> dict:
    """Return how many custom templates exist for each shape."""
    return {
        name: len(_custom_templates.get(name, []))
        for name in SHAPE_NAMES
    }


def _get_active_templates() -> list[tuple]:
    """
    Build the active template list.
    For shapes with custom templates, use ONLY custom ones.
    For shapes without custom templates, use built-in fallbacks.
    """
    shapes_with_custom = set(_custom_templates.keys())
    templates = []

    # Add custom templates
    for name, samples in _custom_templates.items():
        for sample in samples:
            templates.append((name, sample))

    # Add built-in fallbacks for shapes without custom templates
    for name, pts in _BUILTIN_NORMALIZED:
        if name not in shapes_with_custom:
            templates.append((name, pts))

    return templates


# --- Public API ---

def recognize_shape(points: list[dict], confidence_threshold: float = 0.75):
    """
    Try to recognize a shape from stroke points.

    Args:
        points: list of dicts with 'x' and 'y' keys (normalized 0-1)
        confidence_threshold: minimum confidence to accept a match

    Returns:
        (shape_name, confidence) or (None, 0.0) if no match above threshold
    """
    if len(points) < 5:
        return None, 0.0

    xy_points = [(p["x"], p["y"]) for p in points]
    templates = _get_active_templates()

    if not templates:
        return None, 0.0

    name, confidence = recognize(xy_points, templates)

    if confidence >= confidence_threshold:
        return name, confidence
    return None, 0.0


# Load custom templates on import
_load_custom_templates()
