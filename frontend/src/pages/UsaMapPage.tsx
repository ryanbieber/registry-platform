import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

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
import { useSvgViewportControls } from "../lib/useSvgViewportControls";

const ZOOM_STEP = 1.28;

function normalizeName(name: string | undefined): string {
  return name?.trim() ?? "";
}

function formatZoom(zoom: number): string {
  return `${zoom.toFixed(2)}x`;
}

function getStateNameFromTarget(target: EventTarget | null): string | null {
  if (!(target instanceof Element)) {
    return null;
  }

  const stateElement = target.closest("[data-state-name]");
  return normalizeName(stateElement?.getAttribute("data-state-name") ?? "") || null;
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
  const navigate = useNavigate();
  const [hoveredStateName, setHoveredStateName] = useState<string | null>(null);
  const [selectedStateName, setSelectedStateName] = useState<string | null>(null);
  const {
    dragging,
    handlePointerCancel,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleWheel,
    resetViewport,
    viewport,
    zoomFromCenter,
  } = useSvgViewportControls<ViewportState, string>({
    createInitialViewport,
    getTargetId: getStateNameFromTarget,
    onGestureStart: () => setHoveredStateName(null),
    onTapTarget: (stateName) => {
      if (stateName === USA_ACTIVE_STATE_NAME) {
        navigate("/map/iowa");
        return;
      }

      setSelectedStateName(stateName);
    },
    screenPointFromClient: (clientX, clientY, bounds) =>
      screenPointFromClient(clientX, clientY, bounds, USA_MAP_VIEWBOX_WIDTH, USA_MAP_VIEWBOX_HEIGHT),
    zoomAtPoint,
  });

  const stateFeatures = USA_STATE_FEATURES;

  const activeState = stateFeatures.find((state) => normalizeName(state.properties?.name) === USA_ACTIVE_STATE_NAME) ?? null;

  function handleReset() {
    resetViewport();
    setHoveredStateName(null);
    setSelectedStateName(null);
  }

  function handleZoomIn() {
    zoomFromCenter(ZOOM_STEP, USA_MAP_VIEWBOX_WIDTH, USA_MAP_VIEWBOX_HEIGHT);
  }

  function handleZoomOut() {
    zoomFromCenter(1 / ZOOM_STEP, USA_MAP_VIEWBOX_WIDTH, USA_MAP_VIEWBOX_HEIGHT);
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
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
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

      <div className="map-overlay map-toolbar">
        <div className="map-heading">
          <div>
            <p className="eyebrow">Spatial map</p>
            <h1>USA overview</h1>
          </div>
        </div>
        <div className="map-meta" aria-label="Map status">
          <span>51 jurisdictions</span>
          <span>{formatZoom(viewport.zoom)}</span>
          <span>Tap Iowa for H3 grid</span>
        </div>
        <div className="map-controls" aria-label="Map controls">
          <Link className="secondary-button map-action-link" to="/map/iowa" aria-label="Open Iowa grid">
            Open Iowa
          </Link>
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
    </div>
  );
}
