export const MIN_ZOOM = 0.85;
export const MAX_ZOOM = 5;

export type ViewportState = {
  zoom: number;
  panX: number;
  panY: number;
};

export type ScreenPoint = {
  x: number;
  y: number;
};

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function clampZoom(zoom: number): number {
  return clamp(zoom, MIN_ZOOM, MAX_ZOOM);
}

export function createInitialViewport(): ViewportState {
  return { zoom: 1, panX: 0, panY: 0 };
}

export function zoomAtPoint(
  viewport: ViewportState,
  anchor: ScreenPoint,
  nextZoom: number,
): ViewportState {
  const zoom = clampZoom(nextZoom);
  const worldX = (anchor.x - viewport.panX) / viewport.zoom;
  const worldY = (anchor.y - viewport.panY) / viewport.zoom;
  return {
    zoom,
    panX: anchor.x - worldX * zoom,
    panY: anchor.y - worldY * zoom,
  };
}

export function screenPointFromClient(
  clientX: number,
  clientY: number,
  bounds: DOMRect,
  viewBoxWidth: number,
  viewBoxHeight: number,
): ScreenPoint {
  const scaleX = viewBoxWidth / bounds.width;
  const scaleY = viewBoxHeight / bounds.height;
  return {
    x: (clientX - bounds.left) * scaleX,
    y: (clientY - bounds.top) * scaleY,
  };
}

export function transformForViewport(viewport: ViewportState): string {
  return `translate(${viewport.panX.toFixed(2)} ${viewport.panY.toFixed(2)}) scale(${viewport.zoom.toFixed(4)})`;
}

