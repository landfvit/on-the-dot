# Brand Assets

The black-background user originals remain unchanged in
`trivia_app/static/brand/logo.png` and `trivia_app/static/brand/mark.png`.

## Web Variants

The transparent wordmark and white-background symbol were made with the built-in
image generation tool. Full-resolution editing outputs are kept as `logo-transparent-source.png` and
`mark-white.png` in the same directory. The latter is an archived white-background
variant, no longer used by the favicon. These sources are not public routes.

Wordmark prompt:

> Background extraction of this exact existing logo for use directly on a website. Deliver a PNG with GENUINE TRANSPARENT ALPHA BACKGROUND, NOT a white background and NOT a painted checkerboard. Remove ALL black background outside the green circular discs, including the little spaces between discs. Preserve the green circles and their existing BLACK LETTERS and the black hexagon inside the small period exactly. The black lettering INSIDE the green discs must remain opaque black. Text is the original stylized ON THE DOT. Keep the original layout, shapes, green color, square canvas and margins; do not redesign or retype. No white square, no black square, no border, no shadows, no gradients, no texture. Only ten opaque green discs with their original opaque black glyphs floating on a fully transparent canvas.

Symbol prompt:

> Edit this existing ON THE DOT symbol, do not redesign it. Replace ONLY the solid black background and black gaps between the circles with solid pure white #FFFFFF. Preserve the nine identical vivid green discs in a touching 3-by-3 grid, plus the small green period at the lower right; preserve the same green hue and the exact shapes and relative positions. No letters. Keep the original square canvas and margins; software will tightly frame it for a favicon and add rounded corners later. Absolutely flat uniform fills, clean geometric circle edges, no shadows, no gradients, no shading, no texture or other decoration. Output one square PNG.

## Web Exports

Run `node tools/build_favicon.cjs` with Sharp available on `NODE_PATH` to create:

- `trivia_app/static/brand/favicon.svg`: native 3x3 circles plus period, in palette green `#88B04B`, with no background shape.
- `trivia_app/static/brand/favicon.png`: 64px browser fallback with transparent alpha.
- `trivia_app/static/brand/icon-180.png`: 180px transparent Apple touch icon.

The existing 432px `logo-transparent.png` remains on How to play only; it is no
longer used in the header or beside the Penalties heading.

Browser tests cover wordmark alpha and opaque lettering, no white/black favicon
background, green symbol coverage at 16px and 32px, logo layout and both favicon formats. Increment asset URL versions
when exporting a new favicon, because browsers cache tab icons separately.

## Horizontal Header

The header uses one native SVG circle per letter in `brand_wordmark.html`, with
no raster crops. The geometric glyphs follow the supplied logo, normalized to a
shared 100px grid, cap line at 27, baseline at 73 and center at 50. Repeated O and
T letters share their path definitions. Each word is a flex group; the small
period aligns with the bottom of the last circle.

In `points_theme.css`, `--wordmark-height` controls circle diameter (32px desktop,
24px mobile), `--letter-gap` and `--word-gap` control spacing, and `--glyph-weight`
sets the common stroke width. Circle fill uses `--brand-green`; the favicon
builder uses its matching hex value. The whole logo is one accessible home link
with a 44px touch target. Tests check letter geometry, exact palette color,
transparent corners, visible glyph pixels, and responsive layout.
