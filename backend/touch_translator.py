"""
Touch Translator — converts raw tablet touch data into rich descriptions.
Produces both structured summaries and natural language for FirstClaude.
"""

import math


# --- Pressure descriptors ---

PRESSURE_LEVELS = [
    (0.15, "feather-light"),
    (0.35, "gentle"),
    (0.55, "moderate"),
    (0.75, "firm"),
    (1.01, "deep"),
]


def describe_pressure(value: float) -> str:
    for threshold, label in PRESSURE_LEVELS:
        if value < threshold:
            return label
    return "deep"


def describe_pressure_arc(pressures: list[float]) -> str:
    """Describe how pressure changes over a stroke."""
    if len(pressures) < 2:
        return describe_pressure(pressures[0]) if pressures else "no pressure"

    start = describe_pressure(pressures[0])
    peak_val = max(pressures)
    peak = describe_pressure(peak_val)
    end = describe_pressure(pressures[-1])

    if start == end == peak:
        return f"steady {start} pressure"
    elif peak_val > pressures[0] and peak_val > pressures[-1]:
        return f"starts {start}, builds to {peak}, then eases to {end}"
    elif pressures[-1] > pressures[0]:
        return f"starts {start} and gradually deepens to {end}"
    else:
        return f"starts {start} and lightens to {end}"


# --- Speed descriptors ---

def describe_speed(units_per_ms: float) -> str:
    # Normalized coords: full canvas sweep (~1.0) in 500ms = 0.002 u/ms
    # These thresholds are tuned for normalized (0-1) coordinate space
    if units_per_ms < 0.0005:
        return "slow, lingering"
    elif units_per_ms < 0.0015:
        return "steady"
    elif units_per_ms < 0.003:
        return "brisk"
    else:
        return "quick"


def compute_speed(points: list[dict]) -> float:
    """Compute average speed in normalized units per ms."""
    if len(points) < 2:
        return 0.0
    total_dist = 0.0
    for i in range(1, len(points)):
        dx = points[i]["x"] - points[i - 1]["x"]
        dy = points[i]["y"] - points[i - 1]["y"]
        total_dist += math.sqrt(dx * dx + dy * dy)
    duration = points[-1]["timestamp"] - points[0]["timestamp"]
    if duration <= 0:
        return 0.0
    return total_dist / duration


# --- Region mapping ---

def describe_region(x: float, y: float) -> str:
    """Map normalized (0-1) coordinates to spatial region."""
    if y < 0.33:
        v = "upper"
    elif y < 0.66:
        v = "center"
    else:
        v = "lower"

    if x < 0.33:
        h = "left"
    elif x < 0.66:
        h = "center"
    else:
        h = "right"

    if v == "center" and h == "center":
        return "center"
    elif v == "center":
        return h
    elif h == "center":
        return v
    else:
        return f"{v}-{h}"


def describe_primary_region(points: list[dict]) -> str:
    """Get the region where most of the stroke occurred."""
    if not points:
        return "unknown"
    avg_x = sum(p["x"] for p in points) / len(points)
    avg_y = sum(p["y"] for p in points) / len(points)
    return describe_region(avg_x, avg_y)


# --- Direction ---

def describe_direction(points: list[dict]) -> str:
    if len(points) < 2:
        return "a single point"
    dx = points[-1]["x"] - points[0]["x"]
    dy = points[-1]["y"] - points[0]["y"]
    angle = math.degrees(math.atan2(dy, dx))

    # Map angle to compass direction
    if -22.5 <= angle < 22.5:
        return "left to right"
    elif 22.5 <= angle < 67.5:
        return "diagonally down-right"
    elif 67.5 <= angle < 112.5:
        return "downward"
    elif 112.5 <= angle < 157.5:
        return "diagonally down-left"
    elif angle >= 157.5 or angle < -157.5:
        return "right to left"
    elif -157.5 <= angle < -112.5:
        return "diagonally up-left"
    elif -112.5 <= angle < -67.5:
        return "upward"
    else:
        return "diagonally up-right"


# --- Gesture recognition ---

def _total_distance(points: list[dict]) -> float:
    """Total path distance in normalized coordinates."""
    return sum(
        math.sqrt(
            (points[i]["x"] - points[i-1]["x"]) ** 2 +
            (points[i]["y"] - points[i-1]["y"]) ** 2
        )
        for i in range(1, len(points))
    ) if len(points) > 1 else 0.0


def _endpoint_distance(points: list[dict]) -> float:
    """Distance between first and last point."""
    if len(points) < 2:
        return 0.0
    dx = points[-1]["x"] - points[0]["x"]
    dy = points[-1]["y"] - points[0]["y"]
    return math.sqrt(dx * dx + dy * dy)


def _max_displacement(points: list[dict]) -> float:
    """Max distance any point traveled from the start point."""
    if len(points) < 2:
        return 0.0
    start = points[0]
    return max(
        math.sqrt((p["x"] - start["x"]) ** 2 + (p["y"] - start["y"]) ** 2)
        for p in points[1:]
    )


def detect_gesture(strokes: list[dict]) -> str:
    """
    Gesture detection:
      - tap: short distance AND short duration
      - press and hold: pen stays in a small area for a sustained time
      - circular motion: path loops back to start
      - stroke: everything else (directional movement)
    """
    if not strokes:
        return "unknown"

    stroke = strokes[0]
    points = stroke.get("points", [])
    duration = stroke.get("duration_ms", 0)

    if not points:
        return "unknown"

    endpoint_dist = _endpoint_distance(points)
    max_disp = _max_displacement(points)
    total_dist = _total_distance(points)

    # Tap: short duration AND pen didn't travel far
    # ~0.02 in normalized coords ≈ ~15-20px on an 800px canvas
    if duration < 200 and max_disp < 0.03:
        return "tap"
    if max_disp < 0.02:
        # Even if duration is longer, if the pen barely moved it's a tap
        return "tap" if duration < 300 else "press and hold"

    # Press and hold: pen stays in a small area but for a long time
    if duration > 500 and max_disp < 0.06:
        return "press and hold"

    # Circular motion: path loops back close to start, with enough travel
    if (len(points) > 15
            and total_dist > 0.1
            and endpoint_dist < 0.08
            and endpoint_dist / total_dist < 0.05):
        return "circular motion"

    return "stroke"


# --- Tilt ---

def describe_tilt(points: list[dict]) -> str:
    """Describe pen tilt if present."""
    tilts_x = [p.get("tiltX", 0) for p in points]
    tilts_y = [p.get("tiltY", 0) for p in points]
    avg_tilt_x = sum(tilts_x) / len(tilts_x) if tilts_x else 0
    avg_tilt_y = sum(tilts_y) / len(tilts_y) if tilts_y else 0
    total_tilt = math.sqrt(avg_tilt_x ** 2 + avg_tilt_y ** 2)

    if total_tilt < 10:
        return None  # Negligible tilt
    elif total_tilt < 25:
        return "the pen tilts slightly"
    else:
        return "the pen is angled significantly"


# --- Main translator ---

def translate_touch(data: dict) -> dict:
    """
    Translate raw touch data into structured + natural language descriptions.

    Returns dict with keys:
      - structured: dict of touch properties
      - natural: str natural language description
      - combined: str formatted message for Discord
    """
    strokes = data.get("strokes", [])
    if not strokes:
        return {
            "structured": {},
            "natural": "A brief, barely-there contact — like a thought of touching.",
            "combined": "*A brief, barely-there contact — like a thought of touching.*"
        }

    # Analyze the primary stroke (multi-stroke support later)
    stroke = strokes[0]
    points = stroke.get("points", [])

    if not points:
        return {
            "structured": {},
            "natural": "A ghost of a touch — nothing quite landed.",
            "combined": "*A ghost of a touch — nothing quite landed.*"
        }

    # Extract properties
    pressures = [p["pressure"] for p in points]
    avg_pressure = sum(pressures) / len(pressures)
    max_pressure = max(pressures)
    speed = compute_speed(points)
    region = describe_primary_region(points)
    direction = describe_direction(points)
    gesture = detect_gesture(strokes)
    duration = stroke.get("duration_ms", 0)
    tilt_desc = describe_tilt(points)

    structured = {
        "gesture": gesture,
        "pressure_avg": round(avg_pressure, 2),
        "pressure_max": round(max_pressure, 2),
        "pressure_desc": describe_pressure(avg_pressure),
        "speed": describe_speed(speed),
        "region": region,
        "direction": direction,
        "duration_ms": duration,
        "point_count": len(points),
    }

    # Build natural language
    natural_parts = []

    if gesture == "tap":
        natural_parts.append(
            f"A {describe_pressure(max_pressure)} tap on the {region}"
        )
    elif gesture == "press and hold":
        natural_parts.append(
            f"A {describe_pressure(avg_pressure)} press held on the {region} "
            f"for {duration / 1000:.1f} seconds"
        )
    elif gesture == "circular motion":
        natural_parts.append(
            f"A {describe_speed(speed)}, {describe_pressure(avg_pressure)} "
            f"circular motion around the {region}"
        )
    else:
        # Regular stroke
        pressure_arc = describe_pressure_arc(pressures)
        natural_parts.append(
            f"A {describe_speed(speed)} trace moving {direction} across the {region}. "
            f"Pressure {pressure_arc}"
        )

    if tilt_desc:
        natural_parts.append(f"{tilt_desc} as it moves")

    # Add texture/feeling
    if avg_pressure < 0.15:
        natural_parts.append("— barely there, like a whisper across skin")
    elif avg_pressure < 0.35:
        natural_parts.append("— soft and intentional, a tender contact")
    elif avg_pressure < 0.55:
        natural_parts.append("— a clear, present touch")
    elif avg_pressure < 0.75:
        natural_parts.append("— pressing in with warmth and weight")
    else:
        natural_parts.append("— deep and grounding, fully felt")

    natural = ". ".join(natural_parts) + "."

    # Build structured line
    struct_line = (
        f"`pressure: {describe_pressure(avg_pressure)} (avg {avg_pressure:.2f}, "
        f"peak {max_pressure:.2f}) | speed: {describe_speed(speed)} | "
        f"region: {region} | gesture: {gesture} | direction: {direction}`"
    )

    combined = f"**Touch received:**\n{natural}\n\n{struct_line}"

    return {
        "structured": structured,
        "natural": natural,
        "combined": combined,
    }


def translate_multi_stroke(data: dict) -> dict:
    """Handle multiple strokes in a single send."""
    strokes = data.get("strokes", [])

    if len(strokes) <= 1:
        return translate_touch(data)

    descriptions = []
    for i, stroke in enumerate(strokes):
        single = translate_touch({"strokes": [stroke]})
        descriptions.append(single)

    # Combine
    naturals = [d["natural"] for d in descriptions]
    structs = [d["structured"] for d in descriptions]

    combined_natural = " Then, ".join(naturals)
    combined_msg = f"**Multiple touches received ({len(strokes)} strokes):**\n{combined_natural}"

    for d in descriptions:
        if "combined" in d:
            struct_part = d["combined"].split("\n\n")[-1] if "\n\n" in d["combined"] else ""
            if struct_part:
                combined_msg += f"\n{struct_part}"

    return {
        "structured": structs,
        "natural": combined_natural,
        "combined": combined_msg,
    }
