import { geoPath } from "d3-geo";
import { feature } from "topojson-client";
import usaStatesAtlas from "us-atlas/states-albers-10m.json";

type StateProperties = {
  name: string;
};

type StateGeometry = {
  type: "MultiPolygon";
  coordinates: number[][][][];
};

export type UsaStateFeature = {
  type: "Feature";
  id: string;
  properties: StateProperties;
  geometry: StateGeometry;
};

type UsaStateFeatureCollection = {
  type: "FeatureCollection";
  features: UsaStateFeature[];
};

const PADDING = 28;
const path = geoPath(null);
const atlas = usaStatesAtlas as any;
const allStates = feature(atlas, atlas.objects.states) as unknown as UsaStateFeatureCollection;
const bounds = path.bounds(allStates as any) as [[number, number], [number, number]];

export const USA_ACTIVE_STATE_NAME = "Iowa";
export const USA_MAP_VIEWBOX_WIDTH = Math.ceil(bounds[1][0] - bounds[0][0] + PADDING * 2);
export const USA_MAP_VIEWBOX_HEIGHT = Math.ceil(bounds[1][1] - bounds[0][1] + PADDING * 2);
export const USA_MAP_OFFSET_X = -bounds[0][0] + PADDING;
export const USA_MAP_OFFSET_Y = -bounds[0][1] + PADDING;

export const USA_STATE_FEATURES = allStates.features;

export function pathForState(feature: UsaStateFeature): string {
  return path(feature as any) ?? "";
}

export function centroidForState(feature: UsaStateFeature): [number, number] {
  const centroid = path.centroid(feature as any) as [number, number] | null;
  return centroid ?? [0, 0];
}
