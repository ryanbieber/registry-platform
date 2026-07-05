import { useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import { Link } from "react-router-dom";

import { type H3Cell } from "../api/client";
import { STATIC_MAP_MODE } from "../config";
import { getStaticIowaH3Map } from "../data/iowaH3MapData";
import {
  MAP_VIEWBOX_HEIGHT,
  MAP_VIEWBOX_WIDTH,
  createInitialViewport,
  formatZoom,
  projectBoundary,
  resolutionForZoom,
  screenPointFromClient,
  transformForViewport,
  type ViewportState,
  zoomAtPoint,
} from "../lib/iowaH3Viewport";

const ZOOM_STEP = 1.24;
const DRAG_THRESHOLD_PX = 4;

type ProjectedCell = H3Cell & {
  fill: string;
  points: string;
};

type DragState = {
  pointerId: number;
  startX: number;
  startY: number;
  startPanX: number;
  startPanY: number;
  startCellId: string | null;
  moved: boolean;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function colorForCount(count: number, maxCount: number): string {
  if (maxCount <= 1) {
    return "rgba(13, 148, 136, 0.34)";
  }

  const ratio = clamp(count / maxCount, 0, 1);
  const hue = 166 - ratio * 112;
  const saturation = 68;
  const lightness = 92 - ratio * 42;
  return `hsl(${hue.toFixed(0)} ${saturation}% ${lightness.toFixed(0)}%)`;
}

function formatCoordinate(value: number): string {
  return value.toFixed(5);
}

function getCellIdFromTarget(target: EventTarget | null): string | null {
  if (!(target instanceof Element)) {
    return null;
  }

  const cellElement = target.closest("[data-h3-index]");
  return cellElement ? cellElement.getAttribute("data-h3-index") : null;
}

export function IowaH3MapPage() {
  const [viewport, setViewport] = useState<ViewportState>(() => createInitialViewport());
  const [hoveredCellId, setHoveredCellId] = useState<string | null>(null);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragStateRef = useRef<DragState | null>(null);
  const resolution = useMemo(() => resolutionForZoom(viewport.zoom), [viewport.zoom]);
  const map = useMemo(() => getStaticIowaH3Map(resolution), [resolution]);

  const projectedCells = useMemo<ProjectedCell[]>(() => {
    const maxCount = Math.max(...map.cells.map((cell) => cell.count), 1);
    return map.cells.map((cell) => ({
      ...cell,
      fill: colorForCount(cell.count, maxCount),
      points: projectBoundary(cell.boundary),
    }));
  }, [map]);

  const cellIds = useMemo(() => new Set(projectedCells.map((cell) => cell.h3_index)), [projectedCells]);

  useEffect(() => {
    if (!projectedCells.length) {
      setSelectedCellId(null);
      setHoveredCellId(null);
      return;
    }

    setSelectedCellId((current) => {
      if (current && cellIds.has(current)) {
        return current;
      }
      return projectedCells[0]?.h3_index ?? null;
    });

    setHoveredCellId((current) => {
      if (current && cellIds.has(current)) {
        return current;
      }
      return null;
    });
  }, [cellIds, projectedCells]);

  const activeCellId = hoveredCellId ?? selectedCellId;
  const activeCell = useMemo(
    () => projectedCells.find((cell) => cell.h3_index === activeCellId) ?? projectedCells[0] ?? null,
    [activeCellId, projectedCells],
  );

  function handleZoomIn() {
    const anchor = { x: MAP_VIEWBOX_WIDTH / 2, y: MAP_VIEWBOX_HEIGHT / 2 };
    setViewport((current) => zoomAtPoint(current, anchor, current.zoom * ZOOM_STEP));
  }

  function handleZoomOut() {
    const anchor = { x: MAP_VIEWBOX_WIDTH / 2, y: MAP_VIEWBOX_HEIGHT / 2 };
    setViewport((current) => zoomAtPoint(current, anchor, current.zoom / ZOOM_STEP));
  }

  function handleReset() {
    setViewport(createInitialViewport());
  }

  function handleWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const anchor = screenPointFromClient(event.clientX, event.clientY, bounds);
    const factor = Math.exp(-event.deltaY * 0.0014);
    setViewport((current) => zoomAtPoint(current, anchor, current.zoom * factor));
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) {
      return;
    }

    const cellId = getCellIdFromTarget(event.target);
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startPanX: viewport.panX,
      startPanY: viewport.panY,
      startCellId: cellId,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    const state = dragStateRef.current;
    if (!state || state.pointerId !== event.pointerId) {
      return;
    }

    const bounds = event.currentTarget.getBoundingClientRect();
    const scaleX = MAP_VIEWBOX_WIDTH / bounds.width;
    const scaleY = MAP_VIEWBOX_HEIGHT / bounds.height;
    const deltaX = event.clientX - state.startX;
    const deltaY = event.clientY - state.startY;
    const movedDistance = Math.hypot(deltaX, deltaY);

    if (!state.moved && movedDistance >= DRAG_THRESHOLD_PX) {
      state.moved = true;
      setDragging(true);
      setHoveredCellId(null);
    }

    if (state.moved) {
      setViewport((current) => ({
        ...current,
        panX: state.startPanX + deltaX * scaleX,
        panY: state.startPanY + deltaY * scaleY,
      }));
    }
  }

  function finishPointer(event: PointerEvent<SVGSVGElement>) {
    const state = dragStateRef.current;
    if (!state || state.pointerId !== event.pointerId) {
      return;
    }

    if (!state.moved && state.startCellId) {
      setSelectedCellId(state.startCellId);
      setHoveredCellId(state.startCellId);
    }

    dragStateRef.current = null;
    setDragging(false);

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <div className="map-page">
      <div className="map-stage">
        <svg
          aria-label="Iowa H3 density map"
          className={`map-svg${dragging ? " is-dragging" : ""}`}
          data-pan-x={viewport.panX.toFixed(2)}
          data-pan-y={viewport.panY.toFixed(2)}
          data-resolution={resolution}
          data-zoom={viewport.zoom.toFixed(3)}
          role="img"
          viewBox={`0 0 ${MAP_VIEWBOX_WIDTH} ${MAP_VIEWBOX_HEIGHT}`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={finishPointer}
          onPointerCancel={finishPointer}
          onPointerLeave={() => {
            if (!dragging) {
              setHoveredCellId(null);
            }
          }}
          onWheel={handleWheel}
        >
          <g transform={transformForViewport(viewport)}>
            {projectedCells.map((cell) => {
              const isSelected = cell.h3_index === selectedCellId;
              const isHovered = cell.h3_index === hoveredCellId;
              const isActive = cell.h3_index === activeCellId;

              return (
                <polygon
                  key={cell.h3_index}
                  className={[
                    "map-cell",
                    isHovered ? "is-hovered" : "",
                    isSelected ? "is-selected" : "",
                    isActive ? "is-active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  data-h3-index={cell.h3_index}
                  fill={cell.fill}
                  points={cell.points}
                  stroke="rgba(17, 32, 44, 0.28)"
                  strokeWidth={isActive ? 2.4 : isSelected ? 1.9 : 1.1}
                  onPointerEnter={() => {
                    if (!dragging) {
                      setHoveredCellId(cell.h3_index);
                    }
                  }}
                  onPointerLeave={() => {
                    if (!dragging) {
                      setHoveredCellId((current) => (current === cell.h3_index ? null : current));
                    }
                  }}
                >
                  <title>{`${cell.h3_index} - ${cell.count} people`}</title>
                </polygon>
              );
            })}
          </g>
        </svg>

        <div className="map-overlay map-toolbar">
          <div className="map-heading">
            {STATIC_MAP_MODE ? null : (
              <Link className="map-back-link" to="/" aria-label="Back to search">
                ←
              </Link>
            )}
            <div>
              <p className="eyebrow">Spatial map</p>
              <h1>Iowa H3 grid</h1>
            </div>
          </div>
          <div className="map-meta" aria-label="Map status">
            <span>H3 res {resolution}</span>
            <span>{formatZoom(viewport.zoom)}</span>
            <span>{`${map.total_people} unique people`}</span>
          </div>
          <div className="map-controls" aria-label="Map controls">
            <button className="secondary-button map-control" type="button" onClick={handleZoomOut} aria-label="Zoom out">
              -
            </button>
            <button className="secondary-button map-control" type="button" onClick={handleZoomIn} aria-label="Zoom in">
              +
            </button>
            <button className="secondary-button map-control" type="button" onClick={handleReset} aria-label="Reset view">
              ↺
            </button>
          </div>
        </div>

        {projectedCells.length ? (
          <aside className="map-overlay map-inspector">
            <p className="eyebrow">Cell details</p>
            {activeCell ? (
              <div className="map-inspector__content">
                <h2>{activeCell.h3_index}</h2>
                <dl className="map-stats">
                  <div>
                    <dt>People</dt>
                    <dd>{activeCell.count}</dd>
                  </div>
                  <div>
                    <dt>Center</dt>
                    <dd>
                      {formatCoordinate(activeCell.center_latitude)}, {formatCoordinate(activeCell.center_longitude)}
                    </dd>
                  </div>
                </dl>
                <div>
                  <p className="map-inspector__label">Person UUIDs</p>
                  <div className="uuid-list">
                    {activeCell.person_ids.map((personId) => (
                      <code key={personId}>{personId}</code>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p>No cell selected.</p>
            )}
          </aside>
        ) : (
          <div className="map-overlay map-empty-state">
            <p>No geocoded Iowa addresses are available yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
