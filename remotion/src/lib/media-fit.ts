/**
 * Where a fitted picture lands on the canvas.
 *
 * This module imports NOTHING. That is deliberate and it is the reason it is a
 * file of its own rather than three more exports in media-geometry.ts: the
 * project's renderer tests execute the real module under node rather than
 * asserting on how its source reads (see tests/test_renderer_frame_scaling.py),
 * and media-geometry.ts cannot be imported that way -- it pulls in react,
 * remotion and @remotion/media-utils, and its relative imports are
 * extensionless. Geometry that decides where the picture goes should be
 * checkable without booting a renderer.
 */

/** Intrinsic or canvas dimensions, in pixels. */
export type FitDimensions = {width: number; height: number};

/** Where a fitted picture actually lands on the canvas, in canvas pixels. */
export type MediaRect = {left: number; top: number; width: number; height: number};

/**
 * The rect an `object-fit` picture occupies on the canvas.
 *
 * Both of the renderer's presentations need this and they need it to AGREE. The
 * covering branch needs it to place annotations against a picture that has been
 * scaled up and cropped; the matted branch needs it to place annotations
 * against a picture that has been fitted whole. They are the same arithmetic
 * with one operator different -- `max` fills the canvas and overflows, `min`
 * fits inside it -- and they were written out separately, which is a standing
 * invitation for one to be corrected and the other left behind. Solving for the
 * picture in two places is how an annotation ends up somewhere nobody pointed.
 *
 * `focusX`/`focusY` are the CSS `object-position` percentages, and the offset
 * expression is the same for both fits: the leftover space is distributed by
 * the focus point. On `cover` the leftover is negative and the expression says
 * which part of the overflow is cropped away; on `contain` it is positive and
 * the same expression says where the mat is left. One formula, because it is
 * one idea.
 *
 * NOTE what this deliberately does NOT depend on: the source's pixel count. The
 * rect is a function of the canvas and the source's ASPECT only -- scale the
 * source up or down and the returned rect is identical. That is the property
 * that keeps a low-resolution scan from rendering as a stamp in a dark field,
 * and it is what tests/test_matted_plate_framing.py pins.
 */
export const mediaFitRect = (
  fit: 'cover' | 'contain',
  canvas: FitDimensions,
  source: FitDimensions,
  focusX: number,
  focusY: number,
): MediaRect => {
  const scale =
    fit === 'cover'
      ? Math.max(canvas.width / source.width, canvas.height / source.height)
      : Math.min(canvas.width / source.width, canvas.height / source.height);
  const width = source.width * scale;
  const height = source.height * scale;
  return {
    left: (canvas.width - width) * (focusX / 100),
    top: (canvas.height - height) * (focusY / 100),
    width,
    height,
  };
};
