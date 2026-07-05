import type { IowaH3Map } from "../api/client";

type CellFixture = {
  h3_index: string;
  count: number;
  person_ids: string[];
  center_latitude: number;
  center_longitude: number;
  boundary: Array<[number, number]>;
};

function makeCell(
  h3Index: string,
  centerLatitude: number,
  centerLongitude: number,
  count: number,
  personIds: string[],
  size: number,
): CellFixture {
  return {
    h3_index: h3Index,
    count,
    person_ids: personIds,
    center_latitude: centerLatitude,
    center_longitude: centerLongitude,
    boundary: [
      [centerLongitude - size, centerLatitude - size * 0.25],
      [centerLongitude - size * 0.4, centerLatitude + size],
      [centerLongitude + size * 0.4, centerLatitude + size],
      [centerLongitude + size, centerLatitude - size * 0.25],
      [centerLongitude + size * 0.55, centerLatitude - size],
      [centerLongitude - size * 0.55, centerLatitude - size],
    ],
  };
}

function makeFixture(resolution: number): IowaH3Map {
  if (resolution === 6) {
    return {
      state: "IA",
      resolution,
      total_people: 4,
      cells: [
        makeCell(
          "860000000000001",
          41.75,
          -93.65,
          3,
          [
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
            "33333333-3333-4333-8333-333333333333",
          ],
          0.42,
        ),
        makeCell("860000000000002", 42.05, -93.25, 1, ["44444444-4444-4444-8444-444444444444"], 0.28),
      ],
    };
  }

  if (resolution === 7) {
    return {
      state: "IA",
      resolution,
      total_people: 5,
      cells: [
        makeCell(
          "870000000000001",
          41.72,
          -93.62,
          2,
          ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"],
          0.28,
        ),
        makeCell(
          "870000000000002",
          41.95,
          -93.4,
          2,
          ["33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"],
          0.24,
        ),
        makeCell("870000000000003", 42.25, -93.1, 1, ["55555555-5555-4555-8555-555555555555"], 0.22),
      ],
    };
  }

  if (resolution === 8) {
    return {
      state: "IA",
      resolution,
      total_people: 6,
      cells: [
        makeCell(
          "880000000000001",
          41.5868,
          -93.625,
          3,
          ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"],
          0.14,
        ),
        makeCell(
          "880000000000002",
          41.7001,
          -93.8002,
          2,
          ["44444444-4444-4444-8444-444444444444", "55555555-5555-4555-8555-555555555555"],
          0.12,
        ),
        makeCell("880000000000003", 41.85, -93.35, 1, ["66666666-6666-4666-8666-666666666666"], 0.11),
      ],
    };
  }

  if (resolution === 9) {
    return {
      state: "IA",
      resolution,
      total_people: 7,
      cells: [
        makeCell(
          "890000000000001",
          41.5868,
          -93.625,
          2,
          ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"],
          0.08,
        ),
        makeCell(
          "890000000000002",
          41.635,
          -93.71,
          2,
          ["33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"],
          0.07,
        ),
        makeCell(
          "890000000000003",
          41.7001,
          -93.8002,
          2,
          ["55555555-5555-4555-8555-555555555555", "66666666-6666-4666-8666-666666666666"],
          0.065,
        ),
        makeCell("890000000000004", 41.92, -93.28, 1, ["77777777-7777-4777-8777-777777777777"], 0.06),
      ],
    };
  }

  return {
    state: "IA",
    resolution: 10,
    total_people: 8,
    cells: [
      makeCell(
        "8a0000000000001",
        41.5868,
        -93.625,
        2,
        ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"],
        0.05,
      ),
      makeCell(
        "8a0000000000002",
        41.615,
        -93.68,
        2,
        ["33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"],
        0.045,
      ),
      makeCell(
        "8a0000000000003",
        41.7001,
        -93.8002,
        2,
        ["55555555-5555-4555-8555-555555555555", "66666666-6666-4666-8666-666666666666"],
        0.042,
      ),
      makeCell(
        "8a0000000000004",
        41.92,
        -93.28,
        2,
        ["77777777-7777-4777-8777-777777777777", "88888888-8888-4888-8888-888888888888"],
        0.04,
      ),
    ],
  };
}

const STATIC_IOWA_H3_MAPS: Record<number, IowaH3Map> = {
  6: makeFixture(6),
  7: makeFixture(7),
  8: makeFixture(8),
  9: makeFixture(9),
  10: makeFixture(10),
};

export function getStaticIowaH3Map(resolution: number): IowaH3Map {
  const clampedResolution = Math.max(6, Math.min(resolution, 10));
  return STATIC_IOWA_H3_MAPS[clampedResolution] ?? STATIC_IOWA_H3_MAPS[10];
}
