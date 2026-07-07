import { useRef, useState, type PointerEvent, type WheelEvent } from "react";

type BaseViewportState = {
  zoom: number;
  panX: number;
  panY: number;
};

type ScreenPoint = {
  x: number;
  y: number;
};

type PointerRecord<TTargetId> = {
  clientX: number;
  clientY: number;
  targetId: TTargetId | null;
};

type PanGesture<TViewport extends BaseViewportState, TTargetId> = {
  kind: "pan";
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startPoint: ScreenPoint;
  startViewport: TViewport;
  tapTargetId: TTargetId | null;
  moved: boolean;
};

type PinchGesture<TViewport extends BaseViewportState> = {
  kind: "pinch";
  pointerIds: [number, number];
  startViewport: TViewport;
  startMidpoint: ScreenPoint;
  startDistance: number;
};

type GestureState<TViewport extends BaseViewportState, TTargetId> =
  | { kind: "idle" }
  | PanGesture<TViewport, TTargetId>
  | PinchGesture<TViewport>;

type UseSvgViewportControlsOptions<TViewport extends BaseViewportState, TTargetId> = {
  createInitialViewport: () => TViewport;
  dragThresholdPx?: number;
  getTargetId: (target: EventTarget | null) => TTargetId | null;
  onGestureStart?: () => void;
  onTapTarget?: (targetId: TTargetId) => void;
  screenPointFromClient: (clientX: number, clientY: number, bounds: DOMRect) => ScreenPoint;
  wheelZoomSensitivity?: number;
  zoomAtPoint: (viewport: TViewport, anchor: ScreenPoint, nextZoom: number) => TViewport;
};

function midpoint(pointA: ScreenPoint, pointB: ScreenPoint): ScreenPoint {
  return {
    x: (pointA.x + pointB.x) / 2,
    y: (pointA.y + pointB.y) / 2,
  };
}

function distance(pointA: ScreenPoint, pointB: ScreenPoint): number {
  return Math.hypot(pointA.x - pointB.x, pointA.y - pointB.y);
}

function isPrimaryPointerButton(event: PointerEvent<SVGSVGElement>): boolean {
  return event.pointerType !== "mouse" || event.button === 0;
}

export function useSvgViewportControls<TViewport extends BaseViewportState, TTargetId>({
  createInitialViewport,
  dragThresholdPx = 4,
  getTargetId,
  onGestureStart,
  onTapTarget,
  screenPointFromClient,
  wheelZoomSensitivity = 0.00135,
  zoomAtPoint,
}: UseSvgViewportControlsOptions<TViewport, TTargetId>) {
  const [viewport, setViewport] = useState<TViewport>(() => createInitialViewport());
  const [dragging, setDragging] = useState(false);
  const activePointersRef = useRef<Map<number, PointerRecord<TTargetId>>>(new Map());
  const gestureRef = useRef<GestureState<TViewport, TTargetId>>({ kind: "idle" });
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;

  function beginPan(
    pointerId: number,
    point: ScreenPoint,
    clientX: number,
    clientY: number,
    targetId: TTargetId | null,
    moved: boolean,
  ) {
    gestureRef.current = {
      kind: "pan",
      pointerId,
      startClientX: clientX,
      startClientY: clientY,
      startPoint: point,
      startViewport: viewportRef.current,
      tapTargetId: targetId,
      moved,
    };
  }

  function beginPinch(bounds: DOMRect) {
    const pointerEntries = Array.from(activePointersRef.current.entries()).slice(0, 2);
    if (pointerEntries.length !== 2) {
      return;
    }

    const [[pointerIdA, pointerA], [pointerIdB, pointerB]] = pointerEntries;
    const pointA = screenPointFromClient(pointerA.clientX, pointerA.clientY, bounds);
    const pointB = screenPointFromClient(pointerB.clientX, pointerB.clientY, bounds);

    gestureRef.current = {
      kind: "pinch",
      pointerIds: [pointerIdA, pointerIdB],
      startViewport: viewportRef.current,
      startMidpoint: midpoint(pointA, pointB),
      startDistance: Math.max(distance(pointA, pointB), 1),
    };
    setDragging(true);
    onGestureStart?.();
  }

  function clearInteractionState() {
    activePointersRef.current.clear();
    gestureRef.current = { kind: "idle" };
    setDragging(false);
  }

  function resetViewport() {
    clearInteractionState();
    setViewport(createInitialViewport());
  }

  function zoomFromCenter(factor: number, width: number, height: number) {
    const anchor = { x: width / 2, y: height / 2 };
    setViewport((current) => zoomAtPoint(current, anchor, current.zoom * factor));
  }

  function handleWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const anchor = screenPointFromClient(event.clientX, event.clientY, bounds);
    const factor = Math.exp(-event.deltaY * wheelZoomSensitivity);
    setViewport((current) => zoomAtPoint(current, anchor, current.zoom * factor));
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (!isPrimaryPointerButton(event) || activePointersRef.current.size >= 2) {
      return;
    }

    const targetId = getTargetId(event.target);
    activePointersRef.current.set(event.pointerId, {
      clientX: event.clientX,
      clientY: event.clientY,
      targetId,
    });
    event.currentTarget.setPointerCapture(event.pointerId);

    const bounds = event.currentTarget.getBoundingClientRect();
    const point = screenPointFromClient(event.clientX, event.clientY, bounds);

    if (activePointersRef.current.size === 1) {
      beginPan(event.pointerId, point, event.clientX, event.clientY, targetId, false);
      return;
    }

    beginPinch(bounds);
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    const pointer = activePointersRef.current.get(event.pointerId);
    if (!pointer) {
      return;
    }

    pointer.clientX = event.clientX;
    pointer.clientY = event.clientY;

    const bounds = event.currentTarget.getBoundingClientRect();
    const gesture = gestureRef.current;

    if (gesture.kind === "pan" && gesture.pointerId === event.pointerId) {
      const point = screenPointFromClient(event.clientX, event.clientY, bounds);
      const movedDistance = Math.hypot(event.clientX - gesture.startClientX, event.clientY - gesture.startClientY);

      if (!gesture.moved && movedDistance >= dragThresholdPx) {
        gesture.moved = true;
        setDragging(true);
        onGestureStart?.();
      }

      if (gesture.moved) {
        const nextViewport = {
          ...gesture.startViewport,
          panX: gesture.startViewport.panX + (point.x - gesture.startPoint.x),
          panY: gesture.startViewport.panY + (point.y - gesture.startPoint.y),
        };
        setViewport(nextViewport);
      }

      return;
    }

    if (gesture.kind !== "pinch") {
      return;
    }

    const [pointerIdA, pointerIdB] = gesture.pointerIds;
    const pointerA = activePointersRef.current.get(pointerIdA);
    const pointerB = activePointersRef.current.get(pointerIdB);
    if (!pointerA || !pointerB) {
      return;
    }

    const pointA = screenPointFromClient(pointerA.clientX, pointerA.clientY, bounds);
    const pointB = screenPointFromClient(pointerB.clientX, pointerB.clientY, bounds);
    const currentMidpoint = midpoint(pointA, pointB);
    const currentDistance = Math.max(distance(pointA, pointB), 1);
    const scaledViewport = zoomAtPoint(
      gesture.startViewport,
      gesture.startMidpoint,
      gesture.startViewport.zoom * (currentDistance / gesture.startDistance),
    );

    setViewport({
      ...scaledViewport,
      panX: scaledViewport.panX + (currentMidpoint.x - gesture.startMidpoint.x),
      panY: scaledViewport.panY + (currentMidpoint.y - gesture.startMidpoint.y),
    });
  }

  function finishPointer(event: PointerEvent<SVGSVGElement>) {
    const trackedPointer = activePointersRef.current.get(event.pointerId);
    if (!trackedPointer) {
      return;
    }

    activePointersRef.current.delete(event.pointerId);

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    const bounds = event.currentTarget.getBoundingClientRect();
    const gesture = gestureRef.current;

    if (gesture.kind === "pan" && gesture.pointerId === event.pointerId) {
      if (!gesture.moved && gesture.tapTargetId !== null) {
        onTapTarget?.(gesture.tapTargetId);
      }
      gestureRef.current = { kind: "idle" };
      setDragging(false);
      return;
    }

    if (gesture.kind !== "pinch") {
      return;
    }

    const remainingPointerEntry = Array.from(activePointersRef.current.entries())[0];
    if (!remainingPointerEntry) {
      gestureRef.current = { kind: "idle" };
      setDragging(false);
      return;
    }

    const [pointerId, remainingPointer] = remainingPointerEntry;
    const point = screenPointFromClient(remainingPointer.clientX, remainingPointer.clientY, bounds);
    beginPan(pointerId, point, remainingPointer.clientX, remainingPointer.clientY, null, true);
    setDragging(true);
  }

  return {
    dragging,
    handlePointerCancel: finishPointer,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp: finishPointer,
    handleWheel,
    resetViewport,
    setViewport,
    viewport,
    zoomFromCenter,
  };
}
