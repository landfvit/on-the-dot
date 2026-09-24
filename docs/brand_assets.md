# Brand Assets

The black-background user originals remain unchanged in
`trivia_app/static/brand/logo.png` and `trivia_app/static/brand/mark.png`.

## Web Variants

The transparent wordmark and white-background symbol were made with the built-in
image generation tool. Full-resolution editing outputs are kept as `logo-transparent-source.png` and
`mark-white.png` in the same directory. They are build sources, not public routes.

Wordmark prompt:

> Background extraction of this exact existing logo for use directly on a website. Deliver a PNG with GENUINE TRANSPARENT ALPHA BACKGROUND, NOT a white background and NOT a painted checkerboard. Remove ALL black background outside the green circular discs, including the little spaces between discs. Preserve the green circles and their existing BLACK LETTERS and the black hexagon inside the small period exactly. The black lettering INSIDE the green discs must remain opaque black. Text is the original stylized ON THE DOT. Keep the original layout, shapes, green color, square canvas and margins; do not redesign or retype. No white square, no black square, no border, no shadows, no gradients, no texture. Only ten opaque green discs with their original opaque black glyphs floating on a fully transparent canvas.

Symbol prompt:

> Edit this existing ON THE DOT symbol, do not redesign it. Replace ONLY the solid black background and black gaps between the circles with solid pure white #FFFFFF. Preserve the nine identical vivid green discs in a touching 3-by-3 grid, plus the small green period at the lower right; preserve the same green hue and the exact shapes and relative positions. No letters. Keep the original square canvas and margins; software will tightly frame it for a favicon and add rounded corners later. Absolutely flat uniform fills, clean geometric circle edges, no shadows, no gradients, no shading, no texture or other decoration. Output one square PNG.

## Web Exports

Run `node tools/build_favicon.cjs` with Sharp available on `NODE_PATH` to create:

- `trivia_app/static/brand/logo-transparent.png`: 432px wordmark with genuine alpha, displayed without any CSS background or border.
- `trivia_app/static/brand/favicon.svg`: tightly framed symbol with white background and rounded transparent outer corners.
- `trivia_app/static/brand/favicon.png`: 64px browser fallback with the same corners.
- `trivia_app/static/brand/icon-180.png`: 180px Apple touch icon.

Browser tests cover wordmark alpha and opaque lettering, white favicon pixels,
transparent corners, green symbol coverage at 16px and 32px, logo layout and both favicon formats. Increment asset URL versions
when exporting a new favicon, because browsers cache tab icons separately.

## Horizontal Header

The header composes three CSS viewports of the existing transparent wordmark:
`ON`, `THE`, and `DOT.`. No raster is regenerated or stretched. The first viewport
excludes the blank circle, while the last retains the small period. The original
square layout remains on the entry pages, and the favicon is unchanged.

In `points_theme.css`, `--wordmark-height` controls the circle height (32px on
desktop, 24px on mobile); `gap` controls the spacing between words. The crop
coordinates refer to the 432px PNG and must be updated if that source changes.
The whole logo is one home link with an accessible name and a 44px touch target.
