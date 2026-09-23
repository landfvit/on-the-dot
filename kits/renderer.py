from pathlib import Path
from html import escape
import xml.etree.ElementTree as ET
from PIL import Image, ImageColor

from .vectorizer import (
    png_to_svg_geometry,
    save_vectorized_png,
    image_to_svg_geometry,
)


KITS_CODE_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = KITS_CODE_DIRECTORY.parent

KIT_DATA_DIRECTORY = PROJECT_ROOT / "data" / "kits"

BASE_DIRECTORY = KIT_DATA_DIRECTORY / "base"
PATTERNS_DIRECTORY = KIT_DATA_DIRECTORY / "patterns"
VECTORS_DIRECTORY = KIT_DATA_DIRECTORY / "vectors"
RENDERED_DIRECTORY = KIT_DATA_DIRECTORY / "rendered"


def normalize_color(color):

    if not color:
        raise ValueError("Kit color is missing")

    color = color.strip().replace("#", "")

    if len(color) == 3:
        color = ''.join(c * 2 for c in color)
    if len(color) != 6:
        raise ValueError(f"Invalid kit color: {color}")

    try:
        int(color, 16)

    except ValueError:
        raise ValueError(f"Invalid kit color: {color}")

    return "#" + color.lower()


def get_pattern_path(pattern, part):

    if not pattern:
        return None

    safe_pattern = pattern.replace("/", "_")

    path = (
        PATTERNS_DIRECTORY
        / safe_pattern
        / f"{part}.png"
    )

    if not path.exists():
        raise FileNotFoundError(f"Missing kit pattern: {path}")

    return path


def get_base_path(part):

    path = (
        BASE_DIRECTORY
        / f"{part}.svg"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing Wikimedia SVG base: {path}"
        )

    return path


def vectorize_pattern(pattern, part):

    png_path = get_pattern_path(
        pattern,
        part,
    )

    if png_path is None:
        return None

    safe_pattern = pattern.replace("/", "_")

    svg_path = (
        VECTORS_DIRECTORY
        / "patterns"
        / safe_pattern
        / f"{part}.svg"
    )

    if not svg_path.exists() or svg_path.stat().st_mtime_ns < png_path.stat().st_mtime_ns:

        save_vectorized_png(
            png_path,
            svg_path,
        )

    return svg_path


def get_pattern_geometry(pattern, part):

    if not pattern:
        return ""

    png_path = get_pattern_path(
        pattern,
        part,
    )

    if png_path is None:
        return ""

    vectorize_pattern(
        pattern,
        part,
    )

    data = png_to_svg_geometry(
        png_path
    )

    return data["geometry"]


def extract_svg_inner(svg_text):
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    root = ET.fromstring(svg_text)
    if root.tag.split('}')[-1] != 'svg':
        raise ValueError('Expected an SVG document')
    return ''.join(ET.tostring(child, encoding='unicode') for child in root)


def recolor_svg(svg_text, color):
    color = normalize_color(color)
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    root = ET.fromstring(svg_text)
    # Commons bases mask the area OUTSIDE the garment; color goes behind them.
    background = ET.Element('{http://www.w3.org/2000/svg}rect', {
        'width': root.attrib['width'], 'height': root.attrib['height'], 'fill': color,
    })
    root.insert(0, background)
    return ET.tostring(root, encoding='unicode')


def get_base_geometry(part, color):

    path = get_base_path(part)

    svg_text = path.read_text(
        encoding="utf-8"
    )

    svg_text = recolor_svg(
        svg_text,
        color,
    )

    return extract_svg_inner(
        svg_text
    )


def create_part(part, data):

    base_geometry = get_base_geometry(
        part,
        data.get("color"),
    )

    pattern_geometry = get_pattern_geometry(
        data.get("pattern"),
        part,
    )

    return f"""
<g id="{part}">
    <g class="base">
        {base_geometry}
    </g>

    <g class="pattern">
        {pattern_geometry}
    </g>
</g>
"""


def create_shirt(kit_data):

    left_arm = create_part(
        "left_arm",
        kit_data["left_arm"],
    )

    body = create_part(
        "body",
        kit_data["body"],
    )

    right_arm = create_part(
        "right_arm",
        kit_data["right_arm"],
    )

    return f"""
<g transform="translate(0 0)">
    {left_arm}
</g>

<g transform="translate(31 0)">
    {body}
</g>

<g transform="translate(69 0)">
    {right_arm}
</g>
"""


def create_shorts(kit_data):

    return create_part(
        "shorts",
        kit_data["shorts"],
    )


def create_socks(kit_data):

    return create_part(
        "socks",
        kit_data["socks"],
    )


def create_team_directory_name(team):

    return (
        team
        .lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("/", "_")
    )


def render_kit(
    team,
    kit_type,
    kit_data,
):

    team_name = escape(team)
    kit_name = escape(kit_type)

    shirt = create_shirt(
        kit_data
    )

    shorts = create_shorts(
        kit_data
    )

    socks = create_socks(
        kit_data
    )

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>

<svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 120 145"
    width="480"
    height="580"
    shape-rendering="crispEdges"
>

<title>{team_name} - {kit_name}</title>

<g transform="translate(10 5)">
{shirt}
</g>

<g transform="translate(10 70)">
{shorts}
</g>

<g transform="translate(10 112)">
{socks}
</g>

</svg>
"""

    team_directory = (
        RENDERED_DIRECTORY
        / create_team_directory_name(team)
    )

    team_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        team_directory
        / f"{kit_type}.svg"
    )

    output_path.write_text(
        svg,
        encoding="utf-8",
    )

    print(
        f"Rendered SVG -> {output_path}"
    )

    return output_path


def compose_layers(layers, paths, width=100, height=135):
    """Reproduce the source's geometry, colors and alpha, without resampling."""
    if not layers or len(layers) != len(paths):
        raise ValueError('Every kit layer needs a source image')
    canvas = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    for layer, path in zip(layers, paths):
        geometry = [layer[k] for k in ('left', 'top', 'width', 'height')]
        if any(v != int(v) for v in geometry):
            raise ValueError('Pixel kit geometry must use whole pixels')
        x, y, w, h = map(int, geometry)
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
            raise ValueError('Kit layer is outside its canvas')
        color = layer.get('color', 'transparent')
        rgba = (0, 0, 0, 0) if color == 'transparent' else ImageColor.getcolor(normalize_color(color), 'RGBA')
        part = Image.new('RGBA', (w, h), rgba)
        with Image.open(path) as source:
            overlay = source.convert('RGBA')
        if overlay.size != (w, h):
            raise ValueError(f'Unexpected pattern size: {overlay.size}; expected {(w, h)}')
        part.alpha_composite(overlay)
        canvas.alpha_composite(part, (x, y))
    return canvas


def render_pixel_kit(layers, paths, output_stem, title, source_urls):
    image = compose_layers(layers, paths)
    data = image_to_svg_geometry(image)
    output_stem = Path(output_stem)
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    description = escape('Source artwork and licenses: ' + ' '.join(source_urls))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {data["width"]} {data["height"]}" '
           f'width="400" height="540" shape-rendering="crispEdges">'
           f'<title>{escape(title)}</title><desc>{description}</desc>{data["geometry"]}</svg>')
    output_stem.with_suffix('.svg').write_text(svg, encoding='utf-8')
    image.resize((400, 540), Image.Resampling.NEAREST).save(output_stem.with_suffix('.png'))
    return output_stem.with_suffix('.svg')
