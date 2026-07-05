import { useRef, useState, type PointerEvent, type WheelEvent } from "react";

import {
  USA_ACTIVE_STATE_NAME,
  USA_MAP_OFFSET_X,
  USA_MAP_OFFSET_Y,
  USA_MAP_VIEWBOX_HEIGHT,
  USA_MAP_VIEWBOX_WIDTH,
  USA_STATE_FEATURES,
  pathForState,
} from "../data/usaMapData";
import {
  createInitialViewport,
  screenPointFromClient,
  transformForViewport,
  type ViewportState,
  zoomAtPoint,
} from "../lib/mapViewport";

const ZOOM_STEP = 1.28;
const DRAG_THRESHOLD_PX = 4;

type DragState = {
  pointerId: number;
  startX: number;
  startY: number;
  startPanX: number;
  startPanY: number;
  startStateName: string | null;
  moved: boolean;
};

function normalizeName(name: string | undefined): string {
  return name?.trim() ?? "";
}

function fillForState(name: string, hovered: boolean, selected: boolean): string {
  if (name === USA_ACTIVE_STATE_NAME) {
    return hovered || selected ? "#0f766e" : "#14b8a6";
  }

  if (selected) {
    return "#cbd5e1";
  }

  return hovered ? "#cbd5e1" : "#e5e7eb";
}

function strokeForState(name: string, hovered: boolean, selected: boolean): string {
  if (name === USA_ACTIVE_STATE_NAME) {
    return hovered || selected ? "#0f172a" : "#115e59";
  }

  if (selected) {
    return "#475569";
  }

  return hovered ? "#64748b" : "#cbd5e1";
}

function strokeWidthForState(name: string, hovered: boolean, selected: boolean): number {
  if (name === USA_ACTIVE_STATE_NAME) {
    return hovered || selected ? 2.8 : 2.1;
  }

  return hovered || selected ? 1.8 : 1.05;
}

export function UsaMapPage() {
  const [viewport, setViewport] = useState<ViewportState>(() => createInitialViewport());
  const [hoveredStateName, setHoveredStateName] = useState<string | null>(null);
  const [selectedStateName, setSelectedStateName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragStateRef = useRef<DragState | null>(null);

  const stateFeatures = USA_STATE_FEATURES;

  const activeState = stateFeatures.find((state) => normalizeName(state.properties?.name) === USA_ACTIVE_STATE_NAME) ?? null;

  function handleReset() {
    setViewport(createInitialViewport());
    setHoveredStateName(null);
    setSelectedStateName(null);
  }

  function handleWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const anchor = screenPointFromClient(
      event.clientX,
      event.clientY,
      bounds,
      USA_MAP_VIEWBOX_WIDTH,
      USA_MAP_VIEWBOX_HEIGHT,
    );
    const factor = Math.exp(-event.deltaY * 0.0013);
    setViewport((current) => zoomAtPoint(current, anchor, current.zoom * factor));
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) {
      return;
    }

    const stateName = normalizeName((event.target as Element | null)?.closest("[data-state-name]")?.getAttribute("data-state-name") ?? "");
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startPanX: viewport.panX,
      startPanY: viewport.panY,
      startStateName: stateName || null,
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
    const scaleX = USA_MAP_VIEWBOX_WIDTH / bounds.width;
    const scaleY = USA_MAP_VIEWBOX_HEIGHT / bounds.height;
    const deltaX = event.clientX - state.startX;
    const deltaY = event.clientY - state.startY;
    const movedDistance = Math.hypot(deltaX, deltaY);

    if (!state.moved && movedDistance >= DRAG_THRESHOLD_PX) {
      state.moved = true;
      setDragging(true);
      setHoveredStateName(null);
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

    if (!state.moved && state.startStateName) {
      setSelectedStateName(state.startStateName);
    }

    dragStateRef.current = null;
    setDragging(false);

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <div className="usa-map-page">
      <svg
        aria-label="Interactive USA map with Iowa active"
        className={`usa-map-svg${dragging ? " is-dragging" : ""}`}
        data-active-state={activeState?.properties?.name ?? USA_ACTIVE_STATE_NAME}
        data-hovered-state={hoveredStateName ?? ""}
        data-selected-state={selectedStateName ?? ""}
        data-pan-x={viewport.panX.toFixed(2)}
        data-pan-y={viewport.panY.toFixed(2)}
        data-zoom={viewport.zoom.toFixed(3)}
        role="img"
        viewBox={`0 0 ${USA_MAP_VIEWBOX_WIDTH} ${USA_MAP_VIEWBOX_HEIGHT}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishPointer}
        onPointerCancel={finishPointer}
        onPointerLeave={() => {
          if (!dragging) {
            setHoveredStateName(null);
          }
        }}
        onWheel={handleWheel}
        onDoubleClick={handleReset}
      >
        <g transform={transformForViewport(viewport)}>
          <g transform={`translate(${USA_MAP_OFFSET_X.toFixed(2)} ${USA_MAP_OFFSET_Y.toFixed(2)})`}>
            {stateFeatures.map((state) => {
              const stateName = normalizeName(state.properties?.name);
              const isHovered = stateName === hoveredStateName;
              const isSelected = stateName === selectedStateName;
              const isActive = stateName === USA_ACTIVE_STATE_NAME;
              return (
                <path
                  key={stateName || state.id}
                  className={[
                    "usa-map-state",
                    isHovered ? "is-hovered" : "",
                    isSelected ? "is-selected" : "",
                    isActive ? "is-active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  d={pathForState(state)}
                  data-state-name={stateName}
                  fill={fillForState(stateName, isHovered, isSelected)}
                  stroke={strokeForState(stateName, isHovered, isSelected)}
                  strokeWidth={strokeWidthForState(stateName, isHovered, isSelected)}
                  onPointerEnter={() => {
                    if (!dragging) {
                      setHoveredStateName(stateName);
                    }
                  }}
                  onPointerLeave={() => {
                    if (!dragging) {
                      setHoveredStateName((current) => (current === stateName ? null : current));
                    }
                  }}
                >
                  <title>{stateName}</title>
                </path>
              );
            })}
          </g>
        </g>
      </svg>
    </div>
  );
}
