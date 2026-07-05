export const MAP_VIEWBOX_WIDTH = 960;
export const MAP_VIEWBOX_HEIGHT = 720;

export const IOWA_BOUNDS = {
  west: -96.7,
  east: -90.0,
  south: 40.3,
  north: 43.7,
} as const;

export const MIN_ZOOM = 0.7;
export const MAX_ZOOM = 4;

export type ViewportState = {
  zoom: number;
  panX: number;
  panY: number;
};

export type ScreenPoint = {
  x: number;
  y: number;
};

const RESOLUTION_STOPS = [
  { maxZoom: 0.78, resolution: 6 },
  { maxZoom: 0.95, resolution: 7 },
  { maxZoom: 1.45, resolution: 8 },
  { maxZoom: 2.15, resolution: 9 },
  { maxZoom: Number.POSITIVE_INFINITY, resolution: 10 },
] as const;

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function clampZoom(zoom: number): number {
  return clamp(zoom, MIN_ZOOM, MAX_ZOOM);
}

export function createInitialViewport(): ViewportState {
  return { zoom: 1, panX: 0, panY: 0 };
}

export function resolutionForZoom(zoom: number): number {
  const currentZoom = clampZoom(zoom);
  return RESOLUTION_STOPS.find((stop) => currentZoom < stop.maxZoom)?.resolution ?? 10;
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

export function panBy(viewport: ViewportState, deltaX: number, deltaY: number): ViewportState {
  return {
    ...viewport,
    panX: viewport.panX + deltaX,
    panY: viewport.panY + deltaY,
  };
}

export function screenPointFromClient(
  clientX: number,
  clientY: number,
  bounds: DOMRect,
): ScreenPoint {
  const scaleX = MAP_VIEWBOX_WIDTH / bounds.width;
  const scaleY = MAP_VIEWBOX_HEIGHT / bounds.height;
  return {
    x: (clientX - bounds.left) * scaleX,
    y: (clientY - bounds.top) * scaleY,
  };
}

export function transformForViewport(viewport: ViewportState): string {
  return `translate(${viewport.panX.toFixed(2)} ${viewport.panY.toFixed(2)}) scale(${viewport.zoom.toFixed(4)})`;
}

export function formatZoom(zoom: number): string {
  return `${zoom.toFixed(2)}x`;
}

export function projectLongitude(longitude: number): number {
  const widthSpan = IOWA_BOUNDS.east - IOWA_BOUNDS.west;
  return ((longitude - IOWA_BOUNDS.west) / widthSpan) * MAP_VIEWBOX_WIDTH;
}

export function projectLatitude(latitude: number): number {
  const heightSpan = IOWA_BOUNDS.north - IOWA_BOUNDS.south;
  return ((IOWA_BOUNDS.north - latitude) / heightSpan) * MAP_VIEWBOX_HEIGHT;
}

export function projectBoundary(boundary: Array<[number, number]>): string {
  return boundary
    .map(([longitude, latitude]) => `${projectLongitude(longitude).toFixed(2)},${projectLatitude(latitude).toFixed(2)}`)
    .join(" ");
}
