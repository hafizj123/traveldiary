export const WORLD_BOUNDS = [
  [-90, -180],
  [90, 180],
]

export const DEFAULT_MAP_PROPS = {
  maxBounds: WORLD_BOUNDS,
  maxBoundsViscosity: 0.8,
  worldCopyJump: false,
  minZoom: 1,
  zoomSnap: 0.5,
}

export const DEFAULT_TILE_PROPS = {
  noWrap: true,
  bounds: WORLD_BOUNDS,
}
