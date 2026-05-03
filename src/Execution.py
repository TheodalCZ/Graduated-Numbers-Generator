"""
Graduated Numbers Generator

Author: Bc. Pavel Sedláček
Contact:
pavel.seldacek2000@seznam.cz
www.linkedin.com/in/pavelsedlacek-1142000cz
---GitHub profil---
Date: May 2026

Master's Thesis: Automating the Creation of Graduated Number Maps in ArcGIS
Institution: Palacký University Olomouc, Faculty of Science, Department of Geoinformatics
Supervisor: Mgr. Radek Barvíř, Ph.D.

Description:
This script serves as the core execution module for the Graded Numeric Labels toolbox.
Key capabilities and automated processes include:
- Generating Maplex label classes based on numeric attribute classification.
- Supporting statistical methods like Natural Breaks, Quantile, and Equal Interval.
- Leveraging the ArcGIS Pro CIM (Cartographic Information Model) API for advanced styling.
- Interpolating variable font weights across multiple label categories.
- Scaling numbers dynamically, dropping trailing zeroes, and appending custom suffixes.
- Rendering text colour and halo width/colour gradients directly on map layers.

Dependencies:
- arcpy: Esri's site-package for ArcGIS Pro automation and CIM manipulation.
- fontTools: For deep binary analysis of font files and Variable Font axes detection.
- winreg: Windows Registry access for system font style discovery.
- statistics: Descriptive statistics (mean, median) for UI data previews.
- re: Regular expressions for color parsing and string cleaning.
- decimal: High-precision arithmetic rounding for class breaks.
- random: Random sampling for Jenks Natural Breaks optimization.
- os: System path management and font file detection.
- traceback: For detailed error reporting in the ArcGIS Geoprocessing window.
"""

import os
import random
import re
import statistics
import traceback
import winreg
from decimal import Decimal, ROUND_HALF_UP

import arcpy
from fontTools.ttLib import TTFont


def calculate_breaks(values, method, num_categories):
    """Calculate class breaks from values using the given method."""
    values = sorted(values)
    min_val, max_val = min(values), max(values)
    if method == "Equal Interval":
        step = (max_val - min_val) / num_categories
        return [min_val + i * step for i in range(num_categories)] + [max_val]
    if method == "Quantile":
        breaks = []
        for i in range(num_categories):
            index = int(i * len(values) / num_categories)
            breaks.append(values[index])
        breaks.append(max_val)
        if breaks[0] > min_val:
            breaks[0] = min_val
        breaks = sorted(list(set(breaks)))
        return breaks
    if method == "Natural Breaks":
        return natural_breaks(values, num_categories)
    if method == "Proportional (Unclassed)":
        # One class per unique value, with split points at midpoints.
        unique_values = sorted(set(values))
        if not unique_values:
            return []
        if len(unique_values) == 1:
            return [unique_values[0], unique_values[0]]
        breaks = [unique_values[0]]
        for i in range(len(unique_values) - 1):
            mid = (unique_values[i] + unique_values[i + 1]) / 2.0
            breaks.append(mid)
        breaks.append(unique_values[-1])
        return breaks
    if method == "Geometric Interval":
        if min_val <= 0:
            min_val = 0.0001
        breaks = [min_val]
        ratio = (max_val / min_val) ** (1 / num_categories)
        for _ in range(num_categories):
            breaks.append(breaks[-1] * ratio)
        breaks[-1] = max_val
        return breaks
    raise ValueError(f"Unknown classification method: {method}")


def natural_breaks(values, num_categories):
    """Compute Jenks natural breaks with optional sampling for performance.

    For large datasets (>3000 values), a sample of 3000 values is used to
    determine the breakpoints; the global minimum and maximum are preserved
    from the full dataset as absolute boundaries.
    """
    if len(values) == 0:
        return []
    if len(values) > 3000:
        full_min = min(values)
        full_max = max(values)
        sampled = random.sample(values, 3000)
        sampled_breaks = natural_breaks(sampled, num_categories)
        if not sampled_breaks:
            return []
        sampled_breaks[0] = full_min
        sampled_breaks[-1] = full_max
        return sampled_breaks

    values = sorted(values)
    n = len(values)
    mat1 = [[0] * (num_categories + 1) for _ in range(n + 1)]
    mat2 = [[0] * (num_categories + 1) for _ in range(n + 1)]
    # Initialise first column
    for i in range(1, n + 1):
        s1 = sum(values[:i])
        mat1[i][1] = sum((values[j] - s1 / i) ** 2 for j in range(i))
        mat2[i][1] = 1
    for l in range(2, num_categories + 1):
        for i in range(l, n + 1):
            mat1[i][l] = float("inf")
            for j in range(l - 1, i):
                s1 = sum(values[j:i])
                s2 = sum(v ** 2 for v in values[j:i])
                w = i - j
                variance = s2 - (s1 ** 2) / w
                if mat1[j][l - 1] + variance < mat1[i][l]:
                    mat1[i][l] = mat1[j][l - 1] + variance
                    mat2[i][l] = j
    breaks_idx = [0] * (num_categories + 1)
    breaks_idx[num_categories] = n
    for j in range(num_categories, 0, -1):
        breaks_idx[j - 1] = int(mat2[int(breaks_idx[j])][j])
    computed_breaks = [values[min(int(b), len(values) - 1)] for b in breaks_idx]
    computed_breaks[0] = min(values)
    computed_breaks[-1] = max(values)
    return computed_breaks


def cmyk_to_rgb(c, m, y, k):
    """Convert CMYK values (0-1) to RGB (0-255)."""
    r = int(round(255 * (1 - c) * (1 - k)))
    g = int(round(255 * (1 - m) * (1 - k)))
    b = int(round(255 * (1 - y) * (1 - k)))
    return [r, g, b]


def parse_color_as_cmyk(color_text):
    """Parse color as CMYK values (0-1), assuming it's CMYK format."""
    if not color_text:
        raise ValueError("Empty color string.")

    s = color_text.strip()
    parts = [p.strip() for p in s.split(",")]

    def parse_cmyk_value(p):
        """Parse a CMYK value: float, or percentage like '50%'."""
        p = p.strip()
        if p.endswith('%'):
            return float(p[:-1]) / 100.0
        else:
            v = float(p)
            return v / 100.0 if v > 1 else v

    if len(parts) == 4:
        try:
            c = parse_cmyk_value(parts[0])
            m = parse_cmyk_value(parts[1])
            y = parse_cmyk_value(parts[2])
            k = parse_cmyk_value(parts[3])
        except Exception:
            raise ValueError("CMYK values must be numeric or percentages.")
        if not all(0.0 <= v <= 1.0 for v in (c, m, y, k)):
            raise ValueError("CMYK components must be 0-1 or 0-100 or 0%-100%.")
        return [c, m, y, k]
    elif len(parts) == 5:
        # CMYKA, ignore alpha for now
        try:
            c = parse_cmyk_value(parts[0])
            m = parse_cmyk_value(parts[1])
            y = parse_cmyk_value(parts[2])
            k = parse_cmyk_value(parts[3])
        except Exception:
            raise ValueError("CMYKA values must be numeric or percentages.")
        if not all(0.0 <= v <= 1.0 for v in (c, m, y, k)):
            raise ValueError("CMYK components must be 0-1 or 0-100 or 0%-100%.")
        return [c, m, y, k]
    else:
        raise ValueError("Expected 4 or 5 parts for CMYK/CMYKA.")


def detect_color_format(color_text):
    """Detect the color format from the string."""
    if not color_text:
        return None
    s = color_text.strip()
    first_token = s.split(",")[0].strip()
    if re.match(r"^#?[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$", first_token):
        return "HEX"
    parts = [p.strip() for p in s.split(",")]
    if len(parts) == 3:
        # HSL if saturation/lightness are explicitly percentages or hue uses degrees
        if parts[1].endswith('%') or parts[2].endswith('%') or parts[0].lower().endswith('deg'):
            return "HSL"
        return "RGB"
    if len(parts) == 4:
        # Try RGBA first (strict: R,G,B must be in 0-255 range)
        try:
            r = int(float(parts[0]))
            g = int(float(parts[1]))
            b = int(float(parts[2]))
            if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                return "RGBA"
        except:
            pass
        
        # Then try HSLA if the values look like HSL/HSLA
        if looks_like_hsl(parts):
            return "HSLA"
        
        # Then try CMYK (supports percentages and 0-100 values)
        try:
            parse_cmyk_value(parts[0])
            parse_cmyk_value(parts[1])
            parse_cmyk_value(parts[2])
            parse_cmyk_value(parts[3])
            return "CMYK"
        except:
            pass
        
        return "UNKNOWN"
    if len(parts) == 5:
        return "CMYKA"
    return "UNKNOWN"


def interpolate_colors_cmyk(start_cmyk, end_cmyk, n):
    """Interpolate in CMYK space, then convert to RGB."""
    if n <= 0:
        return []
    if n == 1:
        rgb = cmyk_to_rgb(*start_cmyk)
        return [[rgb[0], rgb[1], rgb[2], 255]]
    out = []
    for i in range(n):
        t = i / float(n - 1)
        cmyk = [start_cmyk[j] + t * (end_cmyk[j] - start_cmyk[j]) for j in range(4)]
        rgb = cmyk_to_rgb(*cmyk)
        out.append([rgb[0], rgb[1], rgb[2], 255])
    return out


def interpolate_colors_with_mid_cmyk(start_cmyk, mid_cmyk, end_cmyk, n):
    """Interpolate in CMYK space with mid, then convert to RGB."""
    if n <= 0:
        return []
    if n == 1:
        rgb = cmyk_to_rgb(*mid_cmyk)
        return [[rgb[0], rgb[1], rgb[2], 255]]
    if n == 2:
        rgb_start = cmyk_to_rgb(*start_cmyk)
        rgb_end = cmyk_to_rgb(*end_cmyk)
        return [[rgb_start[0], rgb_start[1], rgb_start[2], 255], [rgb_end[0], rgb_end[1], rgb_end[2], 255]]

    mid_idx = (n + 1) // 2
    out = []

    # First half: start -> mid
    for i in range(mid_idx):
        if mid_idx > 1:
            t = i / (mid_idx - 1)
        else:
            t = 1.0
        cmyk = [start_cmyk[j] + t * (mid_cmyk[j] - start_cmyk[j]) for j in range(4)]
        rgb = cmyk_to_rgb(*cmyk)
        out.append([rgb[0], rgb[1], rgb[2], 255])

    # Second half: mid -> end
    remaining = n - mid_idx
    for i in range(1, remaining + 1):
        if remaining > 1:
            t = i / remaining
        else:
            t = 1.0
        cmyk = [mid_cmyk[j] + t * (end_cmyk[j] - mid_cmyk[j]) for j in range(4)]
        rgb = cmyk_to_rgb(*cmyk)
        out.append([rgb[0], rgb[1], rgb[2], 255])

    return out[:n]


def parse_alpha(a_raw):
    """Convert an alpha value from fraction or 0–255 to a 0–255 integer.

    If the input is between 0 and 1 inclusive, it is treated as a fraction
    and converted to 0–255. Otherwise it is interpreted as a direct 0–255
    value. Raises ValueError if the input is outside the valid range.
    """
    if 0 <= a_raw <= 1:
        a = int(round(a_raw * 255))
    else:
        a = int(round(a_raw))
    if not (0 <= a <= 255):
        raise ValueError("Alpha must be 0-1 or 0-255.")
    return a


def parse_cmyk_value(p):
    """Parse a CMYK value: float, or percentage like '50%'."""
    p = p.strip()
    if p.endswith('%'):
        return float(p[:-1]) / 100.0
    else:
        v = float(p)
        return v / 100.0 if v > 1 else v


def parse_hsl_angle(p):
    """Parse HSL hue value (degrees)."""
    p = p.strip().lower()
    if p.endswith('deg'):
        p = p[:-3]
    return float(p)


def parse_hsl_component(p):
    """Parse HSL saturation/lightness value (0-1, 0-100, or percentage)."""
    p = p.strip()
    if p.endswith('%'):
        return float(p[:-1]) / 100.0
    v = float(p)
    return v / 100.0 if v > 1 else v


def looks_like_hsl(parts):
    """Check if parts look like HSL/HSLA values.

    Considers explicit percent notation, degree hue notation, or numeric
    saturation/lightness in the 0-100 range.
    """
    if len(parts) < 3:
        return False
    if parts[0].strip().lower().endswith('deg'):
        return True
    if parts[1].strip().endswith('%') or parts[2].strip().endswith('%'):
        return True
    try:
        s = float(parts[1].strip())
        l = float(parts[2].strip())
        return 0 <= s <= 100 and 0 <= l <= 100
    except Exception:
        return False


def hsl_to_rgb(h, s, l):
    """Convert HSL to RGB values in 0-255 range."""
    h = h % 360.0
    if s < 0:
        s = 0.0
    if s > 1:
        s = 1.0
    if l < 0:
        l = 0.0
    if l > 1:
        l = 1.0

    c = (1 - abs(2 * l - 1)) * s
    h_prime = h / 60.0
    x = c * (1 - abs((h_prime % 2) - 1))
    m = l - c / 2.0

    if 0 <= h_prime < 1:
        rp, gp, bp = c, x, 0
    elif 1 <= h_prime < 2:
        rp, gp, bp = x, c, 0
    elif 2 <= h_prime < 3:
        rp, gp, bp = 0, c, x
    elif 3 <= h_prime < 4:
        rp, gp, bp = 0, x, c
    elif 4 <= h_prime < 5:
        rp, gp, bp = x, 0, c
    else:
        rp, gp, bp = c, 0, x

    return [
        int(round((rp + m) * 255)),
        int(round((gp + m) * 255)),
        int(round((bp + m) * 255))
    ]


def parse_color(color_text, mode=None):
    """Auto-detect and parse a color string into RGBA format (0-255 scale).

    Intelligently detects color format from input string and converts to a
    normalized RGBA list. Supports hexadecimal, RGB, RGBA, CMYK, and CMYKA
    color formats, making it flexible for users providing colors in various
    cartographic and web-friendly notations.

    Args:
        color_text (str): Color specification string. Can be:
            - HEX: "#RRGGBB", "RRGGBB", "#RRGGBBAA", or "RRGGBBAA"
            - RGB: "R,G,B" (R,G,B 0-255; alpha defaults to 255)
            - RGBA: "R,G,B,A" (R,G,B 0-255; A 0-1 or 0-255)
            - CMYK: "C,M,Y,K" (C,M,Y,K 0-1, 0-100, or 0%-100%; alpha defaults to 255)
            - CMYKA: "C,M,Y,K,A" (C,M,Y,K 0-1, 0-100, or 0%-100%; A 0-1 or 0-255)
            - HSL: "H,S,L" (H 0-360; S/L 0-1, 0-100, or 0%-100%)
            - HSLA: "H,S,L,A" (H 0-360; S/L 0-1, 0-100, or 0%-100%; A 0-1 or 0-255)
        mode (str, optional): Unused parameter retained for API compatibility.

    Returns:
        list of int: RGBA color as [R, G, B, A] where R, G, B, A are in
            range 0-255. Alpha is always normalized to 0-255 regardless of
            input format.

    Raises:
        ValueError: If color_text is empty or if the specified color components
            are out of valid ranges or in an unrecognized format.

    Notes:
        - HEX detection: Matched first token before comma (or entire string).
        - 4-part ambiguity: If all values <=1, treated as CMYK (0-1/0-100/0%-100%);
          otherwise tried as RGBA (0-255, 0-255, 0-255, 0-1/0-255).
        - CMYK conversion: Standard CMY to RGB formula with black (K) factor.
        - Alpha normalization: Delegated to parse_alpha() for consistency.
    """
    if not color_text:
        raise ValueError("Empty color string.")

    s = color_text.strip()
    # detect HEX if string contains '#' or matches hex pattern (first token)
    first_token = s.split(",")[0].strip()
    if re.match(r"^#?[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$", first_token):
        # treat as HEX
        hex_s = first_token
        if hex_s.startswith("#"):
            hex_s = hex_s[1:]
        rgb_hex = hex_s[0:6]
        alpha_hex = hex_s[6:8] if len(hex_s) == 8 else "FF"
        r = int(rgb_hex[0:2], 16)
        g = int(rgb_hex[2:4], 16)
        b = int(rgb_hex[4:6], 16)
        a = int(alpha_hex, 16)
        return [r, g, b, a]

    # otherwise expect comma-separated numeric components
    parts = [p.strip() for p in s.split(",")]

    # RGB or HSL (3 parts)
    if len(parts) == 3:
        # HSL if saturation/lightness are explicitly percentages or hue uses degrees
        if parts[1].endswith('%') or parts[2].endswith('%') or parts[0].lower().endswith('deg'):
            try:
                h = parse_hsl_angle(parts[0])
                s = parse_hsl_component(parts[1])
                l = parse_hsl_component(parts[2])
                if 0 <= h <= 360 and 0 <= s <= 1 and 0 <= l <= 1:
                    rgb = hsl_to_rgb(h, s, l)
                    return [rgb[0], rgb[1], rgb[2], 255]
            except Exception:
                pass

        try:
            r = int(float(parts[0]))
            g = int(float(parts[1]))
            b = int(float(parts[2]))
        except Exception:
            raise ValueError("RGB values must be numeric.")
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("RGB R,G,B must be 0-255.")
        return [r, g, b, 255]

    # 4 parts - Try HSLA first if saturation/lightness are percentages or Hue uses degrees, then CMYK, then RGBA
    if len(parts) == 4:
        # Try HSLA first when the format is explicit
        if parts[1].endswith('%') or parts[2].endswith('%') or parts[0].lower().endswith('deg'):
            try:
                h = parse_hsl_angle(parts[0])
                s = parse_hsl_component(parts[1])
                l = parse_hsl_component(parts[2])
                a_raw = float(parts[3])
                a = parse_alpha(a_raw)
                if 0 <= h <= 360 and 0 <= s <= 1 and 0 <= l <= 1:
                    rgb = hsl_to_rgb(h, s, l)
                    return [rgb[0], rgb[1], rgb[2], a]
            except Exception:
                pass

        # Try CMYK (supports 0-1, 0-100, percentages)
        try:
            c = parse_cmyk_value(parts[0])
            m = parse_cmyk_value(parts[1])
            y = parse_cmyk_value(parts[2])
            k = parse_cmyk_value(parts[3])
            if all(0.0 <= v <= 1.0 for v in (c, m, y, k)):
                r = int(round(255 * (1 - c) * (1 - k)))
                g = int(round(255 * (1 - m) * (1 - k)))
                b = int(round(255 * (1 - y) * (1 - k)))
                return [r, g, b, 255]
        except Exception:
            pass

        # Try RGBA (RGB 0-255 + alpha)
        try:
            r = int(float(parts[0]))
            g = int(float(parts[1]))
            b = int(float(parts[2]))
            a_raw = float(parts[3])
            if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                a = parse_alpha(a_raw)
                return [r, g, b, a]
        except Exception:
            pass

        raise ValueError(
            "4-part color must be either RGBA (0-255, 0-255, 0-255, "
            "0-1/0-255) or CMYK (0-1/0-100/0%-100%, 0-1/0-100/0%-100%, "
            "0-1/0-100/0%-100%, 0-1/0-100/0%-100%)."
        )

    # CMYKA (5 parts)
    if len(parts) == 5:
        # CMYKA
        try:
            c = parse_cmyk_value(parts[0])
            m = parse_cmyk_value(parts[1])
            y = parse_cmyk_value(parts[2])
            k = parse_cmyk_value(parts[3])
            a_raw = float(parts[4])
        except Exception:
            raise ValueError("CMYKA values must be numeric or percentages.")

        if not all(0.0 <= v <= 1.0 for v in (c, m, y, k)):
            raise ValueError("CMYK components must be 0-1 or 0-100 or 0%-100%.")
        r = int(round(255 * (1 - c) * (1 - k)))
        g = int(round(255 * (1 - m) * (1 - k)))
        b = int(round(255 * (1 - y) * (1 - k)))
        a = parse_alpha(a_raw)
        return [r, g, b, a]

    raise ValueError(
        "Unrecognized color format. Use HEX (#RRGGBB or RRGGBBAA), RGB (R,G,B), "
        "RGBA (R,G,B,A), HSL (H,S,L), HSLA (H,S,L,A), CMYK (C,M,Y,K), or CMYKA (C,M,Y,K,A)."
    )


def interpolate_colors(start_rgba, end_rgba, n):
    """Generate a list of n linearly interpolated RGBA colors from start to end.

    Performs per-channel linear interpolation between two RGBA colors to create
    a smooth color gradient. Essential for generating multi-category label
    gradients where each class gets a progressively blended color.

    Args:
        start_rgba (list of int): Starting color as [R, G, B, A], each 0-255.
        end_rgba (list of int): Ending color as [R, G, B, A], each 0-255.
        n (int): Number of colors to generate (including start and end).

    Returns:
        list of list of int: List of n colors, each as [R, G, B, A]. If n=0
            or negative, returns empty list. If n=1, returns [start_rgba].

    Notes:
        - Interpolation parameter t ranges from 0 to 1 across n steps.
        - Each channel is rounded independently to nearest integer.
        - Output always includes both start and end colors as first and last
          elements when n >= 2.
    """
    if n <= 0:
        return []
    if n == 1:
        return [list(start_rgba)]
    out = []
    for i in range(n):
        t = i / float(n - 1)
        c = [int(round(start_rgba[j] + t * (end_rgba[j] - start_rgba[j]))) for j in range(4)]
        out.append(c)
    return out


def interpolate_colors_with_mid(start_rgba, mid_rgba, end_rgba, n):
    """Generate n RGBA colors interpolated through a midpoint for smooth gradients.

    Creates a three-part gradient (start → mid → end) that often produces more
    natural color transitions than simple two-color gradients. Used for
    sophisticated label styling where a balanced mid-tone improves readability.

    Args:
        start_rgba (list of int): Start color as [R, G, B, A], each 0-255.
        mid_rgba (list of int): Midpoint color as [R, G, B, A], each 0-255.
        end_rgba (list of int): End color as [R, G, B, A], each 0-255.
        n (int): Total number of colors to generate.

    Returns:
        list of list of int: List of exactly n colors, each [R, G, B, A].
            For n ≤ 2, returns special cases. For n > 2, splits into two
            segments and avoids duplicate at the junction point.

    Notes:
        - Special cases:
            - n ≤ 0: Returns [].
            - n = 1: Returns [mid_rgba].
            - n = 2: Returns [start_rgba, end_rgba].
        - For n > 2: Midpoint is included in segment 1; segment 2 starts
          from midpoint and excludes it in subsequent iterations to avoid
          duplication.
        - Even distribution: mid_idx = (n+1)//2 ensures reasonable balance
          even when n is odd.
    """
    if n <= 0:
        return []
    if n == 1:
        return [list(mid_rgba)]
    if n == 2:
        return [list(start_rgba), list(end_rgba)]

    # Split into two halves
    mid_idx = (n + 1) // 2  # Include middle point in first half for even distribution
    out = []

    # First half: start -> mid
    for i in range(mid_idx):
        if mid_idx > 1:
            t = i / (mid_idx - 1)
        else:
            t = 1.0
        c = [int(round(start_rgba[j] + t * (mid_rgba[j] - start_rgba[j]))) for j in range(4)]
        out.append(c)

    # Second half: mid -> end (exclude mid point on second iteration to avoid duplication)
    remaining = n - mid_idx
    for i in range(1, remaining + 1):
        if remaining > 1:
            t = i / remaining
        else:
            t = 1.0
        c = [int(round(mid_rgba[j] + t * (end_rgba[j] - mid_rgba[j]))) for j in range(4)]
        out.append(c)

    return out[:n]


def get_parsed_color_cmyk(color_text, error_prefix):
    """Safely parse a color string as CMYK, reporting errors to ArcGIS Geoprocessing.

    Similar to get_parsed_color but returns [c,m,y,k] in 0-1 range.
    """
    if color_text:
        try:
            return parse_color_as_cmyk(color_text)
        except Exception as e:
            arcpy.AddError(f"{error_prefix}: {e}")
    return None


def get_parsed_color(color_text, error_prefix):
    """Safely parse a color string, reporting errors to ArcGIS Geoprocessing.

    Wrapper around parse_color() that converts exceptions into arcpy.AddError()
    messages with a user-friendly prefix. Returns None on failure without raising,
    allowing graceful error handling in the main workflow.

    Args:
        color_text (str): Color specification string (see parse_color() for format).
        error_prefix (str): Descriptive prefix for error message, e.g.,
            "Invalid start color specification".

    Returns:
        list of int or None: RGBA color as [R, G, B, A] if parsing succeeds,
            or None if parsing fails. On failure, arcpy.AddError() is called
            with a message combining error_prefix and the exception details.

    Notes:
        - Empty or None input: Returns None without error message.
        - Used throughout main() for all user-provided color parameters to
          ensure robust error reporting in the ArcGIS UI.
    """
    if color_text:
        try:
            return parse_color(color_text)
        except Exception as err:
            arcpy.AddError(f"{error_prefix}: {err}")
            return None
    return None


def create_halo_symbol(color_rgba, width):
    """Create a CIM polygon symbol for label halo (outline) effect.

    Constructs a CIM-compatible halo polygon symbol with solid fill color.
    The width parameter is informational; the caller is responsible for setting
    sym.haloSize. This function is called for each label class in the gradient.

    Args:
        color_rgba (list of int): Halo color as [R, G, B, A], each 0-255.
        width (float): Halo width in points (stored for reference; not set here).

    Returns:
        arcpy.cim.CIMPolygonSymbol: CIM polygon symbol object configured with
            the specified color fill. Ready to be assigned to a text symbol's
            haloSymbol property.

    Notes:
        - CIM version: "V2" is used for ArcGIS Pro 2.x+ compatibility.
        - Properties set:
            - enable = True (halo is active).
            - colorLocked = False (color can be modified).
            - overprint = False (standard rendering).
        - The haloSize property must be set separately by the caller to apply
          the width.
    """
    halo_color = arcpy.cim.CreateCIMObjectFromClassName('CIMRGBColor', 'V2')
    halo_color.values = color_rgba
    halo_fill = arcpy.cim.CreateCIMObjectFromClassName('CIMSolidFill', 'V2')
    halo_fill.color = halo_color
    halo_fill.enable = True
    halo_fill.colorLocked = False
    halo_fill.overprint = False
    halo_polygon = arcpy.cim.CreateCIMObjectFromClassName('CIMPolygonSymbol', 'V2')
    halo_polygon.symbolLayers = [halo_fill]
    return halo_polygon


def create_default_separators():
    """Create standard Maplex label stacking separators for line wrapping control.

    Generates a pair of CIM stacking separator objects (space and comma) that
    control where Maplex label engine can break labels across multiple lines.
    These are used to manage label wrapping behavior on map layers.

    Returns:
        list of arcpy.cim.CIMMaplexStackingSeparator: Two separator objects:
            [0] Space separator (separator=' ').
            [1] Comma separator (separator=',').
            Both have visible=True and forcedSplit=False.

    Notes:
        - Used by Maplex to identify potential break points during label
          placement. With these separators, labels can wrap at spaces and
          commas if needed.
        - forcedSplit=False means a line is not forced to split at these
          points; Maplex uses them as options during optimization.
        - Returned list can be assigned to labelClass.maplexLabelPlacementProperties
          .labelStackingProperties.stackingSeparators.
    """
    space_sep = arcpy.cim.CreateCIMObjectFromClassName('CIMMaplexStackingSeparator', 'V2')
    space_sep.separator = ' '
    space_sep.visible = True
    space_sep.forcedSplit = False
    comma_sep = arcpy.cim.CreateCIMObjectFromClassName('CIMMaplexStackingSeparator', 'V2')
    comma_sep.separator = ','
    comma_sep.visible = True
    comma_sep.forcedSplit = False
    return [space_sep, comma_sep]


def main():
    """Main execution entry point: generate and style graduated number labels.

    Orchestrates the entire workflow for creating Maplex label classes with
    graduated styling. Reads all user parameters, classifies data using the
    selected method, generates label classes with Arcade expressions, and
    applies CIM-based styling (fonts, colors, halos, offsets, etc.) to each
    category.

    Workflow:
        1. Load and validate all parameters from the toolbox GUI.
        2. Extract attribute values from input layer.
        3. Generate class breaks using the chosen classification method.
        4. Scale breaks based on user-selected value scale factor.
        5. Create one label class per category with Arcade expression filters.
        6. Interpolate font weights/styles and colors across categories.
        7. Apply CIM styling (text symbol, halo, shadow, offset, etc.).
        8. Configure Maplex label placement properties (wrapping, stacking, etc.).
        9. Enable labels on the layer and report success.

    Parameters (via arcpy.GetParameterInfo()):
        0: input_layer (Feature Layer) - Target layer for label generation.
        1: attribute_field (Field) - Numeric field for classification.
        2: total_element_count (Long, output) - Count of valid values.
        3: value_range_info (String, output) - Min/max info.
        4: average_and_median (String, output) - Descriptive statistics.
        5: classification_method (String) - One of: "Equal Interval", "Quantile",
           "Natural Breaks", "Geometric Interval", "Manual", "Proportional".
        6: number_of_categories (Long) - Number of classes (2-10 typical).
        7: custom_breaks_text (String) - Manual break values if method="Manual".
        8-9: min_size, max_size (Double) - Font size range for gradient.
        10: font_family (String) - Font family name.
        11-13: font_weight/style parameters for gradient mode.
        14-18: Text color and gradient parameters.
        19-22: Formatting (thousands separator, scaling, suffix, decimals).
        23-26: Advanced controls (wrapping, offsets, underline).
        27-32: Halo color, width, and gradient parameters.
        33-35: Shadow color and offset.

    Returns:
        None. Results manifest as label classes and styling on the layer.
        All messaging is via arcpy.AddMessage(), arcpy.AddWarning(), or
        arcpy.AddError().

    Raises:
        Exception: Broad exception handling with traceback logged to ArcGIS
            Geoprocessing window. Does not re-raise.

    Notes:
        - Nested helper functions:
            - _get_param_text(): Fetches parameter value by index or name.
            - _get_registry_variable_family(): Maps base font names to registry
              entries (handles "Oswald" → "Oswald Variable").
            - _apply_variable_axes_to_symbol(): Sets CIM fontVariationSettings
              for variable fonts (wght, ital axes).
            - get_true_font_styles(): Detects available styles for a font family.
            - get_font_weight_range(): Reads min/max weight from font file's fvar.
        - Variable Font Handling: When is_variable=True, fontStyleName is always
          "Regular" and weight is controlled via fontVariationSettings axis values.
        - Quantile Uniqueness: Quantile breaks are deduplicated to prevent
          ArcGIS CIM errors on datasets with many identical values.
        - Arcade Expressions: Each label class uses a ternary expression to
          filter features and format values (scaling, rounding, thousand separator).
        - Color Gradients: Supports 2-color (start→end) and 3-color (start→mid→end)
          gradients for both text and halo.
    """
    try:
        arcpy.AddMessage("Loading parameters...")
        arcpy.AddMessage(
            "Color formats: RGB -> R,G,B (R,G,B 0-255); "
            "RGBA -> R,G,B,A (R,G,B 0-255, A 0-1 or 0-255); "
            "CMYK -> C,M,Y,K (C,M,Y,K 0-1, 0-100, or 0%-100%); "
            "CMYKA -> C,M,Y,K,A (C,M,Y,K 0-1, 0-100, or 0%-100%, A 0-1 or 0-255); "
            "HSL/HSLA -> H,S,L or H,S,L,A (H 0-360, S/L 0-1/0-100/0%-100%)."
        )

        def _get_param_text(index, name=None):
            """Return parameter value as text by searching for a parameter by name.

            Attempts to retrieve a parameter by name (more reliable), with fallback
            to index-based retrieval if name lookup fails.

            Args:
                index (int): Parameter index (for fallback retrieval using arcpy).
                name (str, optional): Parameter name (preferred lookup method).

            Returns:
                str or None: Parameter value as text (valueAsText), or via index if
                    name lookup fails. Returns None if value cannot be retrieved.

            Notes:
                - Priority: valueAsText > value (preserves string formatting).
                - Broad exception handling ensures robust fallback to index retrieval.
            """
            try:
                if name:
                    params = arcpy.GetParameterInfo()
                    for p in params:
                        try:
                            if getattr(p, "name", None) == name:
                                # prefer valueAsText when available
                                return p.valueAsText if p.valueAsText is not None else p.value
                        except Exception:
                            continue
            except Exception:
                pass
            return arcpy.GetParameterAsText(index)

        def _as_bool(raw_value, default=False):
            """Convert ArcGIS text/boolean parameter value to Python bool."""
            if raw_value is None:
                return default
            if isinstance(raw_value, str):
                return raw_value.strip().lower() in ("true", "1", "yes", "y")
            return bool(raw_value)

        def _as_float(raw_value, default=0.0):
            """Convert ArcGIS parameter value to float with safe fallback."""
            if raw_value is None or raw_value == "":
                return default
            try:
                return float(raw_value)
            except Exception:
                return default

        def _as_int(raw_value, default=0):
            """Convert ArcGIS parameter value to int with safe fallback."""
            if raw_value is None or raw_value == "":
                return default
            try:
                return int(raw_value)
            except Exception:
                return default

        def _get_registry_variable_family(family):
            """Return the registry font family name for a variable font (if available).

            ArcGIS tool UI may expose a base family name (e.g., 'Oswald'), but the
            actual variable font is registered as 'Oswald Variable' or similar. This
            function searches the registry for a variable font variant and returns it
            to ensure CIM variable font axes (wght) are correctly applied.

            Args:
                family (str): Font family name to search for (e.g., 'Oswald').

            Returns:
                str: Registry name of a variable font variant if found 
                    (e.g., 'Oswald Variable'), or the original family name if 
                    no variable variant exists.

            Notes:
                - Searches HKEY_LOCAL_MACHINE and HKEY_CURRENT_USER registry hives.
                - Prefers entries containing "variable" or "var" keywords.
                - Falls back to any registry entry matching the family name.
                - Robustness: Returns original family on any registry error.

            Examples:
                >>> _get_registry_variable_family('Oswald')
                'Oswald Variable'  # If found in registry

                >>> _get_registry_variable_family('Arial')
                'Arial'  # Non-variable font or not in registry
            """
            try:
                def _collect_matches(hive):
                    """Collect all registry entries matching the family (from given hive).
                    
                    Args:
                        hive: Registry hive (HKEY_LOCAL_MACHINE or HKEY_CURRENT_USER).
                    
                    Returns:
                        list of str: Registry names matching this family.
                    """
                    matches = []
                    try:
                        key = winreg.OpenKey(
                            hive,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                        )
                        i = 0
                        while True:
                            try:
                                name, _, _ = winreg.EnumValue(key, i)
                                i += 1
                                if not name:
                                    continue
                                name_clean = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
                                base = re.sub(r"[\-\–\:\,\|].*$", "", name_clean).strip()
                                if base.lower() == str(family or "").strip().lower():
                                    matches.append(name_clean)
                            except OSError:
                                break
                        winreg.CloseKey(key)
                    except Exception:
                        pass
                    return matches

                matches = []
                matches.extend(_collect_matches(winreg.HKEY_LOCAL_MACHINE))
                matches.extend(_collect_matches(winreg.HKEY_CURRENT_USER))

                # Prefer a variable font name
                for m in matches:
                    if "variable" in m.lower() or "var" in m.lower():
                        return m
                return matches[0] if matches else family
            except Exception:
                return family

        # Parameter loading follows the toolbox order exactly (0-35)
        # for easier code reading and thesis walk-through.

        # 0-4: Input and preview outputs
        input_layer = _get_param_text(0, 'input_layer')
        attribute_field = _get_param_text(1, 'attribute_field')
        # 2 = total_element_count (output)
        # 3 = value_range_info (output)
        # 4 = average_and_median (output)

        # 5-7: Classification
        classification_method = _get_param_text(5, 'classification_method')
        number_of_categories = _get_param_text(6, 'number_of_categories')
        custom_breaks_text = _get_param_text(7, 'custom_breaks')

        # 8-10: Size and font family
        min_size = _as_float(_get_param_text(8, 'min_size'), 0.0)
        max_size = _as_float(_get_param_text(9, 'max_size'), 0.0)
        font_family = _get_param_text(10, 'font_family')
        # If the `font_family` value is ever outside the value list, use the first
        # one from the value list (synchronization with the validator)
        try:
            params = arcpy.GetParameterInfo()
            font_list = None
            for p in params:
                if getattr(
                        p,
                        "name",
                        None) == "font_family" or getattr(
                        p,
                        "displayName",
                        None) == "Font Selection":
                    font_list = getattr(p, "filter", None)
                    if font_list and hasattr(font_list, "list"):
                        font_list = font_list.list
                    break
            if font_list and font_family not in font_list:
                requested_font_family = font_family
                font_family = font_list[0]
                arcpy.AddWarning(
                    f"Requested font family '{requested_font_family}' is not available. Using '{font_family}' instead."
                )
        except Exception:
            pass

        # Some variable fonts are registered as "<Family> Variable" (e.g. "Oswald Variable").
        # ArcGIS UI often shows just the base family (e.g. "Oswald"), so use the registry name
        # when available to ensure fontVariations (wght) works.
        font_family_cim = _get_registry_variable_family(font_family)

        def _apply_variable_axes_to_symbol(sym, axes):
            """Apply variable font axes to a CIM text symbol.

            For variable fonts, sets the CIM fontVariationSettings to enable
            weight interpolation and other axis control. Replaces any previously
            set axes.

            Args:
                sym: CIM text symbol object to modify.
                axes (dict): Mapping of axis tags to values (e.g., {'wght': 400}).
                    Axis tags: 'wght' (weight), 'ital' (italic), 'slnt' (slant), etc.

            Returns:
                None (modifies sym in place).

            Raises:
                Does not raise; warning logged on failure (via arcpy.AddWarning).

            Notes:
                - Creates CIMFontVariation objects for each axis.
                - Clears previous fontVariationSettings (replaces entirely).
                - Common axes: 'wght' (weight), 'ital' (italic), 'slnt' (slant).
                - Values: wght typically 100-900; ital 0-1; slnt negative values.
                - Robustness: Silently continues if axis application fails.

            Examples:
                >>> _apply_variable_axes_to_symbol(sym, {'wght': 600})
                # Applies weight axis with value 600 to the symbol
            """
            if not axes:
                return
            try:
                variations = []
                for tag, val in axes.items():
                    var_obj = arcpy.cim.CreateCIMObjectFromClassName('CIMFontVariation', 'V2')
                    var_obj.tagName = tag
                    var_obj.value = float(val)
                    variations.append(var_obj)
                # Replace the entire list (clear previous axes)
                sym.fontVariationSettings = variations
                arcpy.AddMessage(f"Variable font axes applied: {axes}")
            except Exception as e:
                arcpy.AddWarning(f"Failed to apply variable axes {axes}: {e}")

        # 11-13: Font style / weight
        font_weight_val = _get_param_text(11, 'font_weight')
        fw_mode = (font_weight_val or '').strip()
        is_gradient = fw_mode in {'Gradient Font Weight ...', 'Gradient Font Weight ...'}
        font_weight_min = _get_param_text(12, 'font_weight_min') if is_gradient else None
        font_weight_max = _get_param_text(13, 'font_weight_max') if is_gradient else None
        font_weight = None if is_gradient else font_weight_val

        # 14-18: Text appearance and gradient colors
        letter_spacing = _as_int(_get_param_text(14, 'letter_spacing'), 0)

        text_color = _get_param_text(15, 'text_color')
        if not text_color or not str(text_color).strip():
            text_color = "0,0,0,1"  # Default: black

        use_color_gradient = _as_bool(_get_param_text(16, 'use_color_gradient'), False)

        text_color_mid = _get_param_text(17, 'text_color_mid')
        if not use_color_gradient:
            text_color_mid = None

        text_color_end = _get_param_text(18, 'text_color_end')
        if not use_color_gradient:
            text_color_end = None

        # 19-22: Number formatting
        thousand_sep_raw = _get_param_text(19, 'thousand_separator')
        if str(thousand_sep_raw).lower() == "space":
            thousand_separator = " "
        elif str(thousand_sep_raw).lower() == "none":
            thousand_separator = ""
        else:
            thousand_separator = ","

        value_scale_raw = _get_param_text(20, 'value_scale')
        scale_map = {
            "0.000001 (millionths)": 0.000001,
            "0.001 (thousandths)": 0.001,
            "0.01 (hundredths)": 0.01,
            "0.1 (tenths)": 0.1,
            "1 (no scaling)": 1,
            "1,000 (thousands)": 1000,
            "1,000,000 (millions)": 1000000,
            "1,000,000,000 (billions)": 1000000000,
            "1,000,000,000,000 (trillions)": 1000000000000,
        }
        value_scale = scale_map.get(str(value_scale_raw), 1)

        value_suffix = _get_param_text(21, 'value_suffix')
        if value_suffix is None:
            value_suffix = ""

        dp_raw = _get_param_text(22, 'decimal_places_after_scale')
        try:
            max_decimals = int(str(dp_raw).strip()) if dp_raw is not None else 1
            if max_decimals < 0:
                max_decimals = 1
        except Exception:
            max_decimals = 1

        # 23-26: Advanced controls
        prevent_wrapping = _as_bool(_get_param_text(23, 'prevent_wrapping'), False)
        offset_x = _as_float(_get_param_text(24, 'label_offset_x'), 0.0)
        offset_y = _as_float(_get_param_text(25, 'label_offset_y'), 0.0)
        underline_text = _as_bool(_get_param_text(26, 'underline_text'), False)

        # 27-32: Halo controls
        halo_color_text = _get_param_text(27, 'halo_color')
        if not halo_color_text or not str(halo_color_text).strip():
            halo_color_text = "0,0,0,1"  # Default: black
        halo_width = _as_float(_get_param_text(28, 'halo_width'), 0.0)
        use_halo_gradient = _as_bool(_get_param_text(29, 'use_halo_gradient'), False)

        halo_color_mid_text = _get_param_text(30, 'halo_color_mid')
        if not use_halo_gradient:
            halo_color_mid_text = None

        halo_color_end_text = _get_param_text(31, 'halo_color_end')
        if not use_halo_gradient:
            halo_color_end_text = None

        halo_width_end = _as_float(_get_param_text(32, 'halo_width_end'), None)
        if not use_halo_gradient:
            halo_width_end = None
        elif halo_width_end is None:
            # If gradient is enabled but halo_width_end is empty, use same value as halo_width
            halo_width_end = halo_width

        # 33-35: Shadow controls
        shadow_color_text = _get_param_text(33, 'shadow_color') or ""
        shadow_offset_x = _as_float(_get_param_text(34, 'shadow_offset_x'), 0.0)
        shadow_offset_y = _as_float(_get_param_text(35, 'shadow_offset_y'), 0.0)

        # Detect color formats for potential CMYK interpolation
        color_texts_for_interpolation = [text_color]
        if use_color_gradient and text_color_mid:
            color_texts_for_interpolation.append(text_color_mid)
        if use_color_gradient and text_color_end:
            color_texts_for_interpolation.append(text_color_end)
        if halo_width > 0:
            color_texts_for_interpolation.append(halo_color_text)
            if use_halo_gradient and halo_color_mid_text:
                color_texts_for_interpolation.append(halo_color_mid_text)
            if use_halo_gradient and halo_color_end_text:
                color_texts_for_interpolation.append(halo_color_end_text)

        formats = [detect_color_format(ct) for ct in color_texts_for_interpolation if ct]
        use_cmyk_interpolation = all(f in ("CMYK", "CMYKA") for f in formats) and len(set(formats)) == 1

        if use_cmyk_interpolation:
            arcpy.AddMessage("All colors are in CMYK format - interpolating in CMYK color space for better accuracy.")

        # parse start color
        if use_cmyk_interpolation:
            font_color_start_cmyk = get_parsed_color_cmyk(text_color, "Invalid start color specification")
            if font_color_start_cmyk is None:
                return
            font_color_start = None  # Not used
        else:
            font_color_start = get_parsed_color(text_color, "Invalid start color specification")
            if font_color_start is None:
                return
            font_color_start_cmyk = None

        # Parse mid and end text colors (optional, only if gradient enabled)
        font_color_mid = None
        font_color_mid_cmyk = None
        font_color_end = None
        font_color_end_cmyk = None
        if use_color_gradient:
            if text_color_mid:
                if use_cmyk_interpolation:
                    font_color_mid_cmyk = get_parsed_color_cmyk(text_color_mid, "Invalid mid color specification")
                    if font_color_mid_cmyk is None:
                        return
                else:
                    font_color_mid = get_parsed_color(text_color_mid, "Invalid mid color specification")
                    if font_color_mid is None:
                        return
            if text_color_end:
                if use_cmyk_interpolation:
                    font_color_end_cmyk = get_parsed_color_cmyk(text_color_end, "Invalid end color specification")
                    if font_color_end_cmyk is None:
                        return
                else:
                    font_color_end = get_parsed_color(text_color_end, "Invalid end color specification")
                    if font_color_end is None:
                        return

        # For halo: parse start, mid (optional), and end (optional) colors
        halo_color_start = None
        halo_color_start_cmyk = None
        halo_color_mid = None
        halo_color_mid_cmyk = None
        halo_color_end = None
        halo_color_end_cmyk = None
        if halo_width > 0:
            if use_cmyk_interpolation:
                halo_color_start_cmyk = get_parsed_color_cmyk(halo_color_text, "Invalid start halo color")
                if halo_color_text and halo_color_start_cmyk is None:
                    return
            else:
                halo_color_start = get_parsed_color(halo_color_text, "Invalid start halo color")
                if halo_color_text and halo_color_start is None:
                    return

            if use_halo_gradient:
                if halo_color_mid_text:
                    if use_cmyk_interpolation:
                        halo_color_mid_cmyk = get_parsed_color_cmyk(halo_color_mid_text, "Invalid mid halo color")
                        if halo_color_mid_cmyk is None:
                            return
                    else:
                        halo_color_mid = get_parsed_color(halo_color_mid_text, "Invalid mid halo color")
                        if halo_color_mid is None:
                            return
                if halo_color_end_text:
                    if use_cmyk_interpolation:
                        halo_color_end_cmyk = get_parsed_color_cmyk(halo_color_end_text, "Invalid end halo color")
                        if halo_color_end_cmyk is None:
                            return
                    else:
                        halo_color_end = get_parsed_color(halo_color_end_text, "Invalid end halo color")
                        if halo_color_end is None:
                            return

                if halo_width_end is None:
                    halo_width_end = halo_width
            else:
                halo_color_mid = None
                halo_color_end = None
                halo_width_end = None

        if classification_method and "proportional" in str(classification_method).lower():
            classification_method = "Proportional (Unclassed)"

        if not all([input_layer, attribute_field, classification_method]):
            arcpy.AddError("One or more required parameters are missing.")
            return
        if not arcpy.Exists(input_layer):
            arcpy.AddError("Input layer does not exist.")
            return

        aprx = arcpy.mp.ArcGISProject("CURRENT")
        m = aprx.activeMap
        lyr = next(
            (
                layer
                for layer in m.listLayers()
                if layer.name == input_layer or layer.longName == input_layer
            ),
            None,
        )

        if not lyr:
            arcpy.AddError("Layer not found in the active map.")
            return
        if not lyr.supports("SHOWLABELS"):
            arcpy.AddError(f"Layer '{lyr.name}' does not support labels.")
            return
        values = [
            row[0]
            for row in arcpy.da.SearchCursor(input_layer, [attribute_field])
            if row[0] is not None
        ]
        if not values:
            arcpy.AddError("Attribute contains no values.")
            return

        min_val, max_val = min(values), max(values)

        # Determine class breaks
        method_text = str(classification_method or "").strip()
        method_norm = method_text.lower()
        normalized_method = classification_method
        if "manual" in method_norm:
            normalized_method = "Manual"
        elif "proportional" in method_norm:
            normalized_method = "Proportional (Unclassed)"

        if normalized_method == "Manual" and custom_breaks_text:
            try:
                # Replace semicolons with spaces (for splitting) and commas with dots (for floats)
                normalized_breaks = custom_breaks_text.replace(";", " ").replace(",", ".")
                inner_breaks = [float(b.strip()) for b in normalized_breaks.split() if b.strip()]

                # Sort the values to prevent illogical ranges
                breaks = [min_val] + sorted(inner_breaks) + [max_val]
                number_of_categories = len(breaks) - 1
            except Exception:
                arcpy.AddError(
                    "Invalid format for custom breaks. Please use spaces or semicolons "
                    "to separate numbers."
                )
                return
        elif normalized_method == "Proportional (Unclassed)":
            unique_values = sorted(set(values))
            if not unique_values:
                arcpy.AddError("Attribute contains no values.")
                return
            number_of_categories = len(unique_values)
            breaks = calculate_breaks(values, normalized_method, number_of_categories)
        else:
            number_of_categories = int(number_of_categories)
            breaks = calculate_breaks(values, normalized_method, number_of_categories)

        # Apply value scaling: divide all breaks by the scale factor for display
        original_breaks = breaks.copy()
        if value_scale != 1:
            breaks = [b / value_scale for b in breaks]

        # Always round breaks to specified decimal places using decimal for proper
        # rounding (even without scaling)
        breaks = [
            float(
                Decimal(str(b)).quantize(
                    Decimal('1.' + '0' * max_decimals),
                    rounding=ROUND_HALF_UP,
                )
            )
            for b in breaks
        ]

        # Always use user-specified decimal places
        arcpy.AddMessage("Generated class breaks:")
        for i in range(len(breaks) - 1):
            arcpy.AddMessage(f" - {breaks[i]} to {breaks[i + 1]}")

        # Remove existing generated label classes (those starting with "Values")
        cim_def = lyr.getDefinition("V3")
        original_count = len(cim_def.labelClasses)
        cim_def.labelClasses = [
            lc for lc in cim_def.labelClasses if not lc.name.startswith("Values")
        ]
        removed = original_count - len(cim_def.labelClasses)
        arcpy.AddMessage(f"Removed {removed} old label classes.")
        lyr.setDefinition(cim_def)

        # Ensure labels are off while updating
        lyr.showLabels = False
        for label_class in lyr.listLabelClasses():
            label_class.visible = False

        label_names = []

        # Create new label classes with Arcade expressions
        for i in range(len(breaks) - 1):
            lower = breaks[i]
            upper = breaks[i + 1]
            orig_lower = original_breaks[i]
            orig_upper = original_breaks[i + 1]
            # Assign values to categories: >= lower and < upper for all except last
            # Last category: >= lower and <= upper (includes upper boundary)
            # Note: comparison is on the original value (before scaling)
            if i == len(breaks) - 2:
                # Last category includes upper boundary
                comparison = (
                    f"$feature.{attribute_field} >= {orig_lower} "
                    f"&& $feature.{attribute_field} <= {orig_upper}"
                )
            else:
                # Other categories: exclude upper boundary
                comparison = (
                    f"$feature.{attribute_field} >= {orig_lower} "
                    f"&& $feature.{attribute_field} < {orig_upper}"
                )

            arcpy.AddMessage(f"Category {i}: {comparison}")

            # Format category name based on max_decimals
            # For display: show upper boundary minus small offset for non-last categories
            # to avoid showing overlapping values in the legend
            if max_decimals > 0:
                decimal_format = f".{max_decimals}f"
                if i == len(breaks) - 2:
                    # Last category: closed interval
                    name = (
                        f"Values {lower:{decimal_format}}{value_suffix} "
                        f"– {upper:{decimal_format}}{value_suffix}"
                    )
                else:
                    # Other categories: upper boundary minus one unit at lowest
                    # decimal place, e.g. if max_decimals=2, subtract 0.01.
                    step = 10 ** (-max_decimals)
                    upper_display = upper - step
                    name = (
                        f"Values {lower:{decimal_format}}{value_suffix} "
                        f"– {upper_display:{decimal_format}}{value_suffix}"
                    )
            else:
                if i == len(breaks) - 2:
                    # Last category: closed interval
                    name = (
                        f"Values {int(round(lower))}{value_suffix} "
                        f"– {int(round(upper))}{value_suffix}"
                    )
                else:
                    # Other categories: upper boundary minus 1
                    upper_display = int(round(upper)) - 1
                    name = (
                        f"Values {int(round(lower))}{value_suffix} "
                        f"– {upper_display}{value_suffix}"
                    )

            # Build format pattern based on data decimals
            # e.g., if max_decimals=4: "#,###.####"
            if max_decimals > 0:
                decimal_part = "#" * max_decimals
                format_pattern_base = f"#,##0.{decimal_part}"
            else:
                format_pattern_base = "#,##0"

            # Prepare Arcade formatting tags (wrap text if spacing > 0)
            chr_start = f"<CHR spacing='{letter_spacing}'>" if letter_spacing != 0 else ""
            chr_end = "</CHR>" if letter_spacing != 0 else ""

            # Format number with appropriate thousand separator and decimal separator
            if thousand_separator == " ":
                # Use non-breaking space as separator for thousands, comma for decimals
                expression = f"""
var val = $feature.{attribute_field} / {value_scale};
if ({comparison}) {{
  var formatted = Text(val, "{format_pattern_base}");
  formatted = Replace(formatted, ",", "\u00A0");
  formatted = Replace(formatted, ".", ",");
  return "{chr_start}" + formatted + "{value_suffix}{chr_end}";
}} else {{
  return null;
}}
""".strip()
            elif thousand_separator == "":
                # No separator for thousands, comma for decimals
                expression = f"""
var val = $feature.{attribute_field} / {value_scale};
if ({comparison}) {{
  var formatted = Text(val, "{format_pattern_base}");
  formatted = Replace(formatted, ",", "");
  formatted = Replace(formatted, ".", ",");
  return "{chr_start}" + formatted + "{value_suffix}{chr_end}";
}} else {{
  return null;
}}
""".strip()
            else:
                # Use comma as separator for thousands, dot for decimals
                expression = f"""
var val = $feature.{attribute_field} / {value_scale};
if ({comparison}) {{
  var formatted = Text(val, "{format_pattern_base}");
  return "{chr_start}" + formatted + "{value_suffix}{chr_end}";
}} else {{
  return null;
}}
""".strip()

            label_class = lyr.createLabelClass(name, expression)
            label_class.expressionEngine = "Arcade"
            label_class.expression = expression
            label_class.visible = True
            label_names.append(name)

        # Style label classes via CIM
        lay_cim = lyr.getDefinition("V3")
        label_classes = [lc for lc in lay_cim.labelClasses if lc.name.startswith("Values")]
        num_classes = len(label_classes)

        # prepare styles for classes
        styles_for_classes = [None] * num_classes
        weights_for_classes = [None] * num_classes  # filled only in gradient + variable mode
        font_families_for_classes = [font_family_cim] * \
            num_classes  # Will be set also in non-gradient mode

        # Shared vocabulary – must always be present (even without a gradient)
        name_to_weight = {
            "UltraThin": 100, "ExtraThin": 100, "Thin": 100, "Hairline": 100,
            "UltraLight": 200, "ExtraLight": 200, "Extra Light": 200,
            "Light": 300, "Book": 300,
            "Normal": 400, "Regular": 400, "Roman": 400,
            "Medium": 500,
            "SemiBold": 600, "DemiBold": 600, "Demi": 600,
            "Bold": 700,
            "UltraBold": 800, "ExtraBold": 800, "Extra Bold": 800,
            "Heavy": 900, "Black": 900,
            "UltraBlack": 950, "ExtraBlack": 950, "Extra Black": 950, "Ultra Heavy": 950
        }

        def parse_weight(val):
            """Parse a numeric weight (e.g. from a variable font slider) or return None.

            Supports values like "400", "400 (Regular)", "100-900", etc.
            """
            try:
                if val is None:
                    return None
                s = str(val).strip()
                match = re.search(r"([-+]?[0-9]*\.?[0-9]+)", s)
                if match:
                    return float(match.group(1))
                return None
            except Exception:
                return None

        def _style_key(style_name):
            """Normalize style names for robust comparisons (e.g., ExtraLight == Extra Light)."""
            return re.sub(r"[^a-z0-9]", "", str(style_name or "").lower())

        def _decode_name_record(name_record):
            try:
                return name_record.toUnicode().strip()
            except Exception:
                try:
                    return name_record.string.decode("utf-8", errors="ignore").strip()
                except Exception:
                    return ""

        def _normalize_family_name(family_name):
            family_name = re.sub(r"\s*\(.*?\)\s*$", "", str(family_name or "")).strip()
            family_name = re.sub(r"[-_]VariableFont.*$", "", family_name, flags=re.IGNORECASE).strip()
            family_name = re.sub(r"\s+", " ", family_name).strip()
            return family_name

        def _normalize_style_name(raw_style):
            if not raw_style:
                return None

            style_name_map = {
                "bi": "Bold Italic",
                "sb": "SemiBold",
                "db": "DemiBold",
                "li": "Light Italic",
                "b": "Bold",
                "i": "Italic",
                "z": "Regular",
            }
            strict_styles = {
                "thin", "extrathin", "ultrathin", "extralight", "ultralight", "light", "book",
                "regular", "normal", "medium", "semibold", "demibold", "bold", "extrabold",
                "ultrabold", "black", "heavy", "italic", "oblique"
            }

            raw_style = re.sub(r"[-_]", " ", str(raw_style).strip())
            raw_style = re.sub(r"\s+", " ", raw_style).strip()
            if not raw_style:
                return None

            key = raw_style.lower()
            if key in style_name_map:
                return style_name_map[key]

            tokens = [t for t in re.split(r"\s+", key) if t]
            if not tokens:
                return None

            normalized_tokens = []
            for token in tokens:
                if token in style_name_map:
                    normalized_tokens.extend(style_name_map[token].split())
                    continue
                if token not in strict_styles:
                    return None
                if token in ("italic", "oblique"):
                    normalized_tokens.append(token.title())
                elif token in ("regular", "normal"):
                    normalized_tokens.append("Regular")
                else:
                    normalized_tokens.append(token.title())

            if "Regular" in normalized_tokens and len(normalized_tokens) > 1:
                normalized_tokens = [token for token in normalized_tokens if token != "Regular"]

            style_value = " ".join(dict.fromkeys(normalized_tokens))
            if style_value.lower() == "regular italic":
                style_value = "Italic"
            return style_value or None

        def _iter_font_file_paths():
            font_paths = set()
            local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
            search_dirs = (
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                os.path.join(local_appdata, "Microsoft", "Windows", "Fonts"),
            )

            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
                    i = 0
                    while True:
                        try:
                            _, file_name, _ = winreg.EnumValue(key, i)
                            i += 1
                            candidate = str(file_name or "").strip()
                            if not candidate:
                                continue
                            if os.path.isabs(candidate) and os.path.exists(candidate):
                                font_paths.add(candidate)
                                continue
                            for base_dir in search_dirs:
                                resolved = os.path.join(base_dir, os.path.basename(candidate))
                                if os.path.exists(resolved):
                                    font_paths.add(resolved)
                                    break
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass

            for base_dir in search_dirs:
                if not os.path.isdir(base_dir):
                    continue
                try:
                    for file_name in os.listdir(base_dir):
                        if file_name.lower().endswith((".ttf", ".otf", ".ttc")):
                            font_paths.add(os.path.join(base_dir, file_name))
                except Exception:
                    pass

            return sorted(font_paths)

        def get_true_font_styles(fam):
            """Retrieve real available styles for a family from font metadata."""
            if fam:
                letters_only = ''.join(c for c in fam if c.isalpha())
                if letters_only and letters_only.isupper() and len(letters_only) >= 3:
                    return ["Regular"]

            fam_clean = _normalize_family_name(fam)
            styles = set()
            for font_path in _iter_font_file_paths():
                try:
                    font = TTFont(font_path, recalcBBoxes=False)
                except Exception:
                    continue

                try:
                    family_names = set()
                    style_names = set()
                    if "name" in font:
                        for name_record in font["name"].names:
                            decoded = _decode_name_record(name_record)
                            if not decoded:
                                continue
                            if name_record.nameID in (1, 16):
                                family_names.add(decoded)
                            elif name_record.nameID in (2, 17):
                                style_names.add(decoded)

                    normalized_families = {
                        _normalize_family_name(name)
                        for name in family_names
                        if _normalize_family_name(name)
                    }
                    if fam_clean not in normalized_families:
                        continue

                    for style_name in style_names:
                        normalized_style = _normalize_style_name(style_name)
                        if normalized_style:
                            styles.add(normalized_style)
                finally:
                    try:
                        font.close()
                    except Exception:
                        pass

            if not styles:
                return ["Regular"]
            # Sort Thin → Black
            weights_order = [
                "Thin",
                "ExtraLight",
                "UltraLight",
                "Light",
                "Regular",
                "Normal",
                "Medium",
                "DemiBold",
                "SemiBold",
                "Bold",
                "ExtraBold",
                "UltraBold",
                "Black",
                "Heavy",
                "ExtraBlack",
                "UltraBlack"]

            def sort_key(s):
                """Sort font styles by weight hierarchy and italic preference.
                
                Args:
                    s (str): Style name (e.g., "Bold Italic", "Light").
                
                Returns:
                    tuple: (weight_index, is_italic) for sorting. Lower values sort first.
                        Weight order: Thin (0) < Light (3) < Regular (4) < Bold (9) < Black (12).
                        Italic: 0 (non-italic) before 1 (italic) at same weight.
                """
                s_low = s.lower()
                italic = bool("italic" in s_low or "oblique" in s_low)
                base = re.sub(r"\b(italic|oblique)\b", "", s_low).strip()
                if not base:
                    base = "regular"
                w_idx = 99
                for k, w in enumerate(weights_order):
                    if w.lower() in base:
                        w_idx = k
                        break
                # sort by weight group first; then normal before italic at same weight
                return (w_idx, 1 if italic else 0)
            return sorted(list(styles), key=sort_key)

        def get_font_weight_range(font_fam):
            """Detect actual font weight range from font file metadata.

            Returns:
                tuple: (min_weight, max_weight, has_wght_axis)
            """
            fam_clean = _normalize_family_name(font_fam)
            for font_path in _iter_font_file_paths():
                try:
                    font = TTFont(font_path, recalcBBoxes=False)
                except Exception:
                    continue

                try:
                    family_names = set()
                    if "name" in font:
                        for name_record in font["name"].names:
                            if name_record.nameID in (1, 16):
                                decoded = _decode_name_record(name_record)
                                if decoded:
                                    family_names.add(_normalize_family_name(decoded))

                    if fam_clean not in family_names:
                        continue

                    if "fvar" in font:
                        for axis in font["fvar"].axes:
                            if axis.axisTag == "wght":
                                return (int(round(axis.minValue)), int(round(axis.maxValue)), True)
                finally:
                    try:
                        font.close()
                    except Exception:
                        pass

            return (100, 950, False)

        # Precompute style list and variable font detection
        # Use the actual registry font name (may include "Variable") for style discovery
        all_styles = get_true_font_styles(font_family_cim)
        if not all_styles:
            all_styles = ["Regular"]

        family_lower = font_family_cim.lower()
        min_weight, max_weight, has_wght_axis = get_font_weight_range(font_family_cim)
        is_variable = has_wght_axis or family_lower.endswith("variable") or " variable" in family_lower

        if is_gradient and font_weight_min and font_weight_max:
            # Gradient mode – interpolate styles or weights
            if is_variable:
                # For variable fonts, italic/oblique variants are removed,
                # aby se váhový gradient řídil pouze číselnou osou (wght).
                final_pool = [s for s in all_styles if "italic" not in s.lower()
                              and "oblique" not in s.lower()]
                if not final_pool:
                    final_pool = all_styles
            else:
                # Standard fonts may use italic depending on selected start/end style
                s_low = font_weight_min.lower()
                e_low = font_weight_max.lower()
                start_is_italic = "italic" in s_low or "oblique" in s_low
                end_is_italic = "italic" in e_low or "oblique" in e_low
                if start_is_italic and end_is_italic:
                    final_pool = [
                        s for s in all_styles if "italic" in s.lower() or "oblique" in s.lower()]
                elif not start_is_italic and not end_is_italic:
                    final_pool = [s for s in all_styles if "italic" not in s.lower()
                                  and "oblique" not in s.lower()]
                else:
                    final_pool = all_styles
                if not final_pool:
                    final_pool = all_styles

            # Find start/end indices
            def get_idx(val, lst):
                """Find the index of a style in a list (case-insensitive, space-tolerant).
                
                Args:
                    val (str): Style name to search for (e.g., "Bold", "Bold Italic").
                    lst (list of str): List of available styles to search in.
                
                Returns:
                    int: Index of matching style in lst. Returns -1 if not found.
                
                Notes:
                    - First, tries exact match (case-insensitive, spaces removed).
                    - If no exact match, tries substring match (case-insensitive).
                    - Returns first match found; -1 if neither exact nor partial match.
                
                Examples:
                    >>> get_idx("Bold Italic", ["Regular", "Bold", "Bold Italic"])
                    2
                    >>> get_idx("b", ["Regular", "Bold", "Bold Italic"])
                    1  # Substring match
                    >>> get_idx("NonExistent", ["Regular", "Bold"])
                    -1  # Not found
                """
                v_clean = str(val).lower().replace(" ", "")
                for i, s in enumerate(lst):
                    if str(s).lower().replace(" ", "") == v_clean:
                        return i
                for i, s in enumerate(lst):
                    if v_clean in str(s).lower().replace(" ", ""):
                        return i
                return -1

            start_idx = get_idx(font_weight_min, final_pool)
            end_idx = get_idx(font_weight_max, final_pool)
            if start_idx == -1:
                start_idx = 0
            if end_idx == -1:
                end_idx = len(final_pool) - 1

            # Interpolation
            if is_variable:
                weight_start = parse_weight(font_weight_min)
                weight_end = parse_weight(font_weight_max)
                if weight_start is None:
                    weight_start = name_to_weight.get(str(font_weight_min).split()[0], 400)
                if weight_end is None:
                    weight_end = name_to_weight.get(str(font_weight_max).split()[0], 700)
                weight_start = max(min_weight, min(max_weight, weight_start))
                weight_end = max(min_weight, min(max_weight, weight_end))
                for i in range(num_classes):
                    if num_classes > 1:
                        t = i / (num_classes - 1.0)
                        weight = weight_start + t * (weight_end - weight_start)
                    else:
                        weight = weight_start
                    weights_for_classes[i] = weight
                    styles_for_classes[i] = "Regular"  # base pro variable
            else:
                # Use even distribution of style steps to avoid uneven clustering (2-4-4-2 etc.)
                if num_classes <= 1:
                    styles_for_classes = [final_pool[start_idx]]
                else:
                    style_span = final_pool[min(start_idx, end_idx):max(start_idx, end_idx) + 1]
                    if start_idx > end_idx:
                        style_span = list(reversed(style_span))

                    n_styles = len(style_span)
                    if n_styles <= 1:
                        styles_for_classes = [style_span[0]] * num_classes
                    elif num_classes < n_styles:
                        # Downsample styles while preserving endpoints
                        indices = [int(round(i * (n_styles - 1) / (num_classes - 1)))
                                   for i in range(num_classes)]
                        styles_for_classes = [style_span[i] for i in indices]
                    else:
                        # Evenly distribute repeated style blocks when there are fewer styles than
                        # classes
                        base = num_classes // n_styles
                        extra = num_classes % n_styles
                        styles_for_classes = []
                        for i, style in enumerate(style_span):
                            count = base + (1 if i < extra else 0)
                            styles_for_classes.extend([style] * count)

                        # Safety fallback to exactly num_classes elements
                        if len(styles_for_classes) != num_classes:
                            styles_for_classes = (
                                styles_for_classes +
                                styles_for_classes)[
                                :num_classes]

                    # For non-variable fonts in gradient mode: compute font families for each
                    # style (important for Light variants)
                    font_families_for_classes = []
                    for style in styles_for_classes:
                        current_family = font_family
                        for kw in ("Light", "UltraLight", "ExtraLight"):
                            if kw.lower() in style.lower():
                                current_family = f"{font_family} {kw}"
                                break
                        font_families_for_classes.append(current_family)

                arcpy.AddMessage(f"Gradient Pool: {final_pool}, is_variable={is_variable}")

        else:
            # Non-gradient: one weight/style for all classes (validator)
            selected_style = (font_weight_val or "Regular").strip()
            requested_style = selected_style

            available_styles = [s.strip() for s in all_styles if s]
            available_by_key = {_style_key(s): s for s in available_styles}
            selected_key = _style_key(selected_style)

            current_font_family = font_family
            if is_variable:
                # === FIX FOR VARIABLE FONTS ===
                # "Regular" + weight and italic are always handled via axes.
                # This follows the SDK and Esri BUG-000176087 guidance.
                current_style = "Regular"
                # Robust parsing of font weights, including "Bold Italic," "Medium Italic," etc.
                numeric_weight = parse_weight(font_weight_val)
                if numeric_weight is None and font_weight_val:
                    weight_key = str(font_weight_val).split()[0].strip()
                    numeric_weight = name_to_weight.get(weight_key, 400)
                # Do not warn for variable fonts when a style name maps to a valid numeric
                # weight (e.g., ExtraLight -> 200) even if not listed explicitly in names.
                if numeric_weight is None and selected_key not in available_by_key:
                    if "regular" in available_by_key:
                        selected_style = "Regular"
                    elif available_styles:
                        selected_style = available_styles[0]
                    else:
                        selected_style = "Regular"
                    arcpy.AddWarning(
                        f"Requested font style '{requested_style}' is not available for '{font_family_cim}'. Using '{selected_style}' instead."
                    )
                    numeric_weight = parse_weight(selected_style)
                    if numeric_weight is None and selected_style:
                        fallback_key = str(selected_style).split()[0].strip()
                        numeric_weight = name_to_weight.get(fallback_key, 400)
                weights_for_classes = [numeric_weight] * num_classes
                styles_for_classes = ["Regular"] * num_classes
            else:
                # Validate selected style against available styles and fallback to Regular.
                if selected_key not in available_by_key:
                    matched = [s for s in available_styles if selected_key and selected_key in _style_key(s)]
                    if matched:
                        selected_style = matched[0]
                    elif "regular" in available_by_key:
                        selected_style = "Regular"
                    elif available_styles:
                        selected_style = available_styles[0]
                    else:
                        selected_style = "Regular"
                    arcpy.AddWarning(
                        f"Requested font style '{requested_style}' is not available for '{font_family_cim}'. Using '{selected_style}' instead."
                    )
                else:
                    selected_style = available_by_key[selected_key]

                current_style = selected_style
                current_font_family = font_family  # Start with base family (may be modified below)
                # Light/ExtraLight/UltraLight are often separate families (e.g. "Oswald Light")
                light_keywords = ["light", "ultralight", "extralight"]
                for kw in light_keywords:
                    if kw in selected_style.lower():
                        light_part = kw.capitalize()
                        current_font_family = f"{font_family} {light_part}"
                        current_style = selected_style.replace(light_part, "", 1).strip()
                        if not current_style:
                            current_style = "Regular"
                        break

                # Ensure current style is available for this family; otherwise fallback
                if _style_key(current_style) not in available_by_key:
                    if "regular" in available_by_key:
                        current_style = "Regular"
                    elif available_styles:
                        current_style = available_styles[0]

                styles_for_classes = [current_style] * num_classes
                font_families_for_classes = [current_font_family] * num_classes
                # Save the family name (important for Light)

            # font_family remains unchanged and is overwritten only during the symbol
            # assignment cycle.
            # (this is important so that the Light trick works only locally for the symbol)

        # prepare color list for classes
        if use_cmyk_interpolation:
            if use_color_gradient and font_color_mid_cmyk and font_color_end_cmyk:
                # Use 3-color interpolation: start -> mid -> end in CMYK
                colors_for_classes = interpolate_colors_with_mid_cmyk(
                    font_color_start_cmyk, font_color_mid_cmyk, font_color_end_cmyk, num_classes)
            elif use_color_gradient and font_color_end_cmyk:
                # Use 2-color interpolation: start -> end in CMYK
                colors_for_classes = interpolate_colors_cmyk(font_color_start_cmyk, font_color_end_cmyk, num_classes)
            else:
                # No gradient: use only start color
                rgb = cmyk_to_rgb(*font_color_start_cmyk)
                colors_for_classes = [[rgb[0], rgb[1], rgb[2], 255] for _ in range(num_classes)]
        else:
            if use_color_gradient and font_color_mid and font_color_end:
                # Use 3-color interpolation: start -> mid -> end
                colors_for_classes = interpolate_colors_with_mid(
                    font_color_start, font_color_mid, font_color_end, num_classes)
            elif use_color_gradient and font_color_end:
                # Use 2-color interpolation: start -> end (no mid)
                colors_for_classes = interpolate_colors(font_color_start, font_color_end, num_classes)
            else:
                # No gradient: use only start color
                colors_for_classes = [font_color_start for _ in range(num_classes)]

        halo_colors_for_classes = None
        halo_widths_for_classes = None
        if halo_width > 0:
            if use_cmyk_interpolation:
                if use_halo_gradient and halo_color_mid_cmyk and halo_color_end_cmyk:
                    # Use 3-color interpolation: start -> mid -> end in CMYK
                    halo_colors_for_classes = interpolate_colors_with_mid_cmyk(
                        halo_color_start_cmyk, halo_color_mid_cmyk, halo_color_end_cmyk, num_classes)
                elif use_halo_gradient and halo_color_end_cmyk:
                    # Use 2-color interpolation: start -> end in CMYK
                    halo_colors_for_classes = interpolate_colors_cmyk(
                        halo_color_start_cmyk, halo_color_end_cmyk, num_classes)
                else:
                    # No gradient: use only start color
                    rgb = cmyk_to_rgb(*halo_color_start_cmyk)
                    halo_colors_for_classes = [[rgb[0], rgb[1], rgb[2], 255] for _ in range(num_classes)]
            else:
                if use_halo_gradient and halo_color_mid and halo_color_end:
                    # Use 3-color interpolation: start -> mid -> end
                    halo_colors_for_classes = interpolate_colors_with_mid(
                        halo_color_start, halo_color_mid, halo_color_end, num_classes)
                elif use_halo_gradient and halo_color_end:
                    # Use 2-color interpolation: start -> end (no mid)
                    halo_colors_for_classes = interpolate_colors(
                        halo_color_start, halo_color_end, num_classes)
                else:
                    # No gradient: use only start color
                    halo_colors_for_classes = [halo_color_start] * num_classes

            if use_halo_gradient and halo_width_end is not None:
                if num_classes > 1:
                    halo_widths_for_classes = [
                        halo_width
                        + (halo_width_end - halo_width) * i / (num_classes - 1)
                        for i in range(num_classes)
                    ]
                else:
                    halo_widths_for_classes = [halo_width]
            else:
                halo_widths_for_classes = [halo_width] * num_classes

        if num_classes > 1:
            step = (max_size - min_size) / (num_classes - 1)
            manual_sizes = [min_size + i * step for i in range(num_classes)]
        else:
            manual_sizes = [min_size]
        for idx, lc in enumerate(label_classes):

            sym = lc.textSymbol.symbol
            raw_style = styles_for_classes[idx] if idx < len(
                styles_for_classes) else styles_for_classes[-1]
            numerical_weight = (
                weights_for_classes[idx]
                if weights_for_classes and weights_for_classes[idx] is not None
                else name_to_weight.get((raw_style or "").split()[0] or "Regular", 400)
            )

            # === CORRECTED LOGIC FOR VARIABLE FONTS (Google Sans, Inter, Roboto Flex, etc.) ===
            # fontStyleName = always "Regular" (SDK rule)
            # ital = 1.0 applies across the axis even for "Bold Italic", "Medium Italic", etc.
            style_lower = (raw_style or "Regular").lower()
            orig_lower = str(font_weight_val or raw_style or "Regular").lower()
            italic_requested = any(x in orig_lower for x in ["italic", "oblique", "regular italic"])
            use_variable = is_variable

            # 1. Preferred weights for generating the list (same as in the old version)
            # For non-gradient mode: use the pre-computed font family.
            # This may be "Calibri Light" if Light was detected.
            # For gradient mode: mostly "Calibri" but may be modified below for Light Italic
            assigned_family = font_families_for_classes[idx] if idx < len(
                font_families_for_classes) else font_families_for_classes[-1]
            sym.fontFamilyName = assigned_family

            if use_variable:
                sym.fontStyleName = "Regular"
            else:
                # Non-variable: Font style (Bold, Bold Italic, ...)
                sym.fontStyleName = raw_style or "Regular"
                if sym.fontStyleName and sym.fontStyleName not in all_styles:
                    arcpy.AddMessage(
                        f"DEBUG: non-variable style '{sym.fontStyleName}' not in {all_styles}")

            # 2.  Set the weight/italic axis up to the style
            if use_variable:

                axes = {}
                #  Detecting weight based on style or slider
                if "thin" in style_lower:
                    axes["wght"] = 100
                elif "extralight" in style_lower or "ultralight" in style_lower:
                    axes["wght"] = 200
                elif "light" in style_lower:
                    axes["wght"] = 300
                elif "medium" in style_lower:
                    axes["wght"] = 500
                elif "semibold" in style_lower or "demibold" in style_lower:
                    axes["wght"] = 600
                elif "bold" in style_lower:
                    axes["wght"] = 700
                elif "extrabold" in style_lower or "ultrabold" in style_lower:
                    axes["wght"] = 800
                elif "black" in style_lower or "heavy" in style_lower:
                    axes["wght"] = 900
                else:
                    axes["wght"] = numerical_weight if numerical_weight is not None else 400

                # Italic Detection
                if italic_requested:
                    axes["ital"] = 1.0
                    arcpy.AddMessage(
                        f"→ Italic requested: ital=1.0 + "
                        f"wght={axes.get('wght', 400)}"
                    )
                _apply_variable_axes_to_symbol(sym, axes)
                arcpy.AddMessage(f"Variable font: applied {axes} for class {idx}")

            # === LAYER NAME FIX ===
            # Add parentheses ONLY if gradient is enabled
            if is_gradient:
                try:
                    # For variable fonts, raw_style is often "Regular" even when weight differs.
                    # Show the numeric weight instead to reflect the actual rendered style.
                    if is_variable and numerical_weight is not None:
                        suffix = f"wght={int(round(numerical_weight))}"
                    else:
                        suffix = raw_style or "Regular"
                    lc.name = f"{lc.name} ({suffix})"
                except Exception:
                    pass
            # ===========================

            sym.height = float(manual_sizes[idx])
            sym.allowOverrun = True
            sym.lineSpacing = 0
            sym.maximumLines = 1
            sym.wordWrap = False

            # Set label offset X and Y (in points)
            try:
                sym.offsetX = offset_x
                sym.offsetY = offset_y
            except Exception:
                pass

            # Underline setting - new parameter
            sym.underline = underline_text
            if underline_text:
                arcpy.AddMessage(f"Underline enabled for label class: {lc.name}")

            # Shadow setting (corrected - direct properties on CIMTextSymbol)
            if shadow_color_text and str(shadow_color_text).strip() and (
                    shadow_offset_x != 0 or shadow_offset_y != 0):
                try:
                    # Parse color using your existing parse_color function
                    shadow_rgba = parse_color(shadow_color_text)  # [R, G, B, A] 0-255

                    # Create CIMRGBColor for shadow
                    shadow_col = arcpy.cim.CreateCIMObjectFromClassName('CIMRGBColor', 'V2')
                    shadow_col.values = shadow_rgba

                    # Apply directly to sym
                    sym.shadowColor = shadow_col
                    sym.shadowOffsetX = shadow_offset_x
                    sym.shadowOffsetY = shadow_offset_y

                    arcpy.AddMessage(
                        f"Shadow set: color={shadow_color_text}, "
                        f"offsetX={shadow_offset_x}, offsetY={shadow_offset_y}"
                    )
                except Exception as e:
                    arcpy.AddWarning(f"Failed to set shadow: {str(e)}. Shadow skipped.")
            else:
                # Explicitly disable shadow if no color or offsets zero
                sym.shadowOffsetX = 0
                sym.shadowOffsetY = 0
                arcpy.AddMessage("Shadow disabled (no color or zero offsets)")

            if lc.maplexLabelPlacementProperties:
                mlpp = lc.maplexLabelPlacementProperties

                # Access stacking properties
                stacking_props = mlpp.labelStackingProperties if hasattr(
                    mlpp, 'labelStackingProperties') else None

                if prevent_wrapping:
                    # Disable stacking via CIM properties (key: canStackLabel = False)
                    mlpp.canStackLabel = False

                    if stacking_props:
                        # Limit to 1 line and remove separators to prevent any splitting
                        stacking_props.maximumNumberOfLines = 1
                        stacking_props.stackingSeparators = []  # Empty list: No split points

                    mlpp.allowTextToWrap = False
                    mlpp.maximumCharactersPerLine = 500  # High value as extra precaution
                    arcpy.AddMessage(
                        "Prevent wrapping enabled: canStackLabel=False, "
                        "max lines=1, no separators"
                    )
                else:
                    # Enable stacking (restore defaults)
                    mlpp.canStackLabel = True

                    if stacking_props:
                        stacking_props.maximumNumberOfLines = 3  # Default
                        stacking_props.stackingSeparators = create_default_separators()

                    mlpp.allowTextToWrap = True
                    mlpp.maximumCharactersPerLine = 24  # Default
                    arcpy.AddMessage(
                        "Prevent wrapping disabled: canStackLabel=True, "
                        "restored defaults"
                    )

                mlpp.canPlaceOutsidePolygon = True

            fill = sym.symbol.symbolLayers[0]
            fill.color.values = colors_for_classes[idx]

            sym.symbol.symbolLayers = [fill]

            # Halo - Working settings for a colored polygon symbol
            if halo_width > 0 and halo_colors_for_classes and idx < len(halo_colors_for_classes):
                sym.haloSymbol = create_halo_symbol(
                    halo_colors_for_classes[idx],
                    halo_widths_for_classes[idx] if halo_widths_for_classes else halo_width)

                # Set the halo width explicitly (this was missing and caused non-working
                # halo thickness).
                if halo_widths_for_classes and idx < len(halo_widths_for_classes):
                    sym.haloSize = halo_widths_for_classes[idx]
                else:
                    sym.haloSize = halo_width

                halo_color = halo_colors_for_classes[idx] if halo_colors_for_classes and idx < len(
                    halo_colors_for_classes) else None
                size = sym.haloSize
                arcpy.AddMessage(f"Halo set for {lc.name}: size={size} pt, halo_color={halo_color}")

        lyr.setDefinition(lay_cim)
        lyr.showLabels = True
        # Do not force-save the project; user must decide when to save.
        arcpy.AddMessage("Labels were created and styled successfully.")

    except Exception as exc:  # pragma: no cover
        arcpy.AddError(f"An error occurred: {str(exc)}\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
