import type { GraphNode } from "./types";

/**
 * Approximate pixel anchors for the 20 graph nodes on the TIET campus image
 * (1400 x 792). The graph owns distances, risk and ETAs; these anchors only
 * project the same route onto the photographed map for wayfinding.
 */
export const CAMPUS_MAP_WIDTH = 1400;
export const CAMPUS_MAP_HEIGHT = 792;

export const MAP_POSITIONS: Record<string, [number, number]> = {
  gate_main: [1165, 665],
  gate_north: [630, 58],
  block_a: [907, 315],
  block_b: [895, 442],
  block_c: [950, 450],
  block_d: [1015, 452],
  library: [945, 388],
  canteen_main: [830, 525],
  canteen_north: [1030, 575],
  foodcourt: [730, 470],
  mess_main: [1040, 533],
  mess_north: [900, 210],
  hostel_b1: [283, 585],
  hostel_b2: [390, 585],
  hostel_g1: [702, 585],
  laundry: [923, 555],
  sports: [675, 290],
  vending_hub: [818, 460],
  medical: [990, 650],
  amphitheatre: [365, 340],
};

export function projectNode(node: GraphNode): [number, number] | null {
  return MAP_POSITIONS[node.id] ?? null;
}
