from pathlib import Path
from PIL import Image


# ==========================================
# COLOR
# ==========================================

def rgba_to_hex(r, g, b):
    """
    Convert RGB values to SVG hex color.
    """

    return f"#{r:02x}{g:02x}{b:02x}"


# ==========================================
# PIXEL VISIBILITY
# ==========================================

def is_visible(pixel):
    """
    Return True if pixel is visible.
    """

    return pixel[3] > 0


# ==========================================
# SAME PIXEL
# ==========================================

def same_pixel(a, b):
    """
    Compare complete RGBA values.
    """

    return a == b


# ==========================================
# CREATE SVG RECTANGLE
# ==========================================

def create_rect(
    x,
    y,
    width,
    pixel,
):
    """
    Convert one horizontal pixel run
    into an SVG rectangle.
    """

    r, g, b, a = pixel

    color = rgba_to_hex(
        r,
        g,
        b,
    )

    opacity = a / 255

    if opacity >= 0.999:

        return (
            f'<rect '
            f'x="{x}" '
            f'y="{y}" '
            f'width="{width}" '
            f'height="1" '
            f'fill="{color}"/>'
        )

    return (
        f'<rect '
        f'x="{x}" '
        f'y="{y}" '
        f'width="{width}" '
        f'height="1" '
        f'fill="{color}" '
        f'fill-opacity="{opacity:.4f}"/>'
    )


# ==========================================
# PNG -> SVG GEOMETRY
# ==========================================

def png_to_svg_geometry(
    png_path,
):
    """
    Convert a PNG into pure SVG geometry.

    IMPORTANT:

    This does NOT embed the PNG.

    Every visible horizontal run of pixels
    becomes an SVG rectangle.

    Example:

        █████
        █████

    becomes roughly:

        <rect x="0" y="0" width="5".../>
        <rect x="0" y="1" width="5".../>
    """

    png_path = Path(
        png_path
    )

    with Image.open(png_path) as source:
        image = source.convert("RGBA")

    return image_to_svg_geometry(image)


def image_to_svg_geometry(image):
    """Merge equal RGBA horizontal runs vertically without changing any pixels."""
    image = image.convert("RGBA")

    width, height = image.size

    pixels = image.load()

    rectangles = []
    active = {}

    for y in range(height):
        current = {}
        x = 0

        while x < width:

            pixel = pixels[x, y]

            # Transparent pixel.
            if not is_visible(pixel):

                x += 1
                continue

            # Find how long this color continues.
            start_x = x

            x += 1

            while x < width:

                next_pixel = pixels[x, y]

                if not is_visible(
                    next_pixel
                ):
                    break

                if not same_pixel(
                    pixel,
                    next_pixel,
                ):
                    break

                x += 1

            run_width = (
                x - start_x
            )

            key = (start_x, run_width, pixel)
            rectangle = active.pop(key, [start_x, y, run_width, 0, pixel])
            rectangle[3] += 1
            current[key] = rectangle
        rectangles.extend(active.values())
        active = current

    rectangles.extend(active.values())
    elements = []
    for x, y, run_width, run_height, pixel in rectangles:
        rect = create_rect(x, y, run_width, pixel)
        elements.append(rect.replace('height="1"', f'height="{run_height}"'))

    return {
        "width": width,
        "height": height,
        "geometry": "\n".join(
            elements
        ),
    }


# ==========================================
# SAVE VECTOR VERSION
# ==========================================

def save_vectorized_png(
    png_path,
    svg_path,
):
    """
    Convert one PNG into a standalone
    pure-vector SVG.
    """

    data = png_to_svg_geometry(
        png_path
    )

    svg_path = Path(
        svg_path
    )

    svg_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 {data["width"]} {data["height"]}"
    shape-rendering="crispEdges"
>
{data["geometry"]}
</svg>
"""

    svg_path.write_text(
        svg,
        encoding="utf-8",
    )

    return svg_path
