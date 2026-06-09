"""
Shared train-route logic: Overpass fetch + A* pathfinding + DB cache.
Used by both the /routes/train endpoint and the segment creation hook.
"""
import json
import heapq
import logging
import httpx
from typing import Optional, List
from sqlalchemy.orm import Session

from ..models.route_cache import RouteCache

logger = logging.getLogger(__name__)


# ─── Cache key ────────────────────────────────────────────────────────────────
def make_cache_key(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Round to 3 dp (~110 m) so nearby identical journeys share an entry."""
    return f"{lat1:.3f},{lon1:.3f}|{lat2:.3f},{lon2:.3f}"


# ─── A* helpers ───────────────────────────────────────────────────────────────
def _euclid(a: tuple, b: tuple) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _a_star(
    nodes: dict,
    adj:   dict,
    start_id: str,
    goal_id: str,
    goal_pos: tuple,
) -> Optional[List[str]]:
    g_score   = {start_id: 0.0}
    open_heap = [(_euclid(nodes[start_id], goal_pos), start_id)]
    came_from: dict[str, str] = {}
    visited:   set[str] = set()
    iterations = 0

    while open_heap and iterations < 80_000:
        iterations += 1
        _, cur = heapq.heappop(open_heap)
        if cur in visited:
            continue
        visited.add(cur)
        if cur == goal_id:
            path: list[str] = []
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            path.append(start_id)
            path.reverse()
            return path
        for nb, d in adj.get(cur, []):
            if nb in visited:
                continue
            tentative = g_score[cur] + d
            if tentative < g_score.get(nb, float("inf")):
                came_from[nb] = cur
                g_score[nb]   = tentative
                f = tentative + _euclid(nodes[nb], goal_pos)
                heapq.heappush(open_heap, (f, nb))
    return None


# ─── Overpass fetch + graph ───────────────────────────────────────────────────
async def _fetch_from_overpass(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> Optional[list]:
    lat_diff = abs(lat2 - lat1)
    lon_diff = abs(lon2 - lon1)
    # Bbox too large → Overpass would time out / return too much data
    if lat_diff > 8 or lon_diff > 12:
        logger.info("train_route: bbox too large, skipping Overpass")
        return None

    margin = max(lat_diff, lon_diff) * 0.2 + 0.4
    south = round(min(lat1, lat2) - margin, 4)
    north = round(max(lat1, lat2) + margin, 4)
    west  = round(min(lon1, lon2) - margin, 4)
    east  = round(max(lon1, lon2) + margin, 4)

    query = (
        f'[out:json][timeout:30];'
        f'way["railway"~"^(rail|light_rail|narrow_gauge)$"]'
        f'["service"!~"^(siding|yard|crossover|spur)$"]'
        f'({south},{west},{north},{east});out geom;'
    )

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.get(
                "https://overpass-api.de/api/interpreter",
                params={"data": query},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("train_route: Overpass request failed: %s", exc)
        return None

    elements = data.get("elements", [])
    if not elements:
        logger.info("train_route: Overpass returned no railway ways in bbox")
        return None

    nodes: dict[str, tuple] = {}
    adj:   dict[str, list]  = {}

    for way in elements:
        geom = way.get("geometry") or []
        if len(geom) < 2:
            continue
        for i, pt in enumerate(geom):
            nid = f"{pt['lat']:.5f},{pt['lon']:.5f}"
            nodes.setdefault(nid, (pt["lat"], pt["lon"]))
            adj.setdefault(nid, [])
            if i > 0:
                prev = geom[i - 1]
                pid  = f"{prev['lat']:.5f},{prev['lon']:.5f}"
                adj.setdefault(pid, [])
                d = _euclid(nodes[nid], (prev["lat"], prev["lon"]))
                adj[nid].append((pid, d))
                adj[pid].append((nid, d))

    if not nodes:
        return None

    start_id = min(nodes, key=lambda nid: _euclid(nodes[nid], (lat1, lon1)))
    goal_id  = min(nodes, key=lambda nid: _euclid(nodes[nid], (lat2, lon2)))
    if start_id == goal_id:
        return None

    path = _a_star(nodes, adj, start_id, goal_id, (lat2, lon2))
    if not path:
        logger.info("train_route: A* found no path between the two nearest rail nodes")
        return None

    return (
        [[lat1, lon1]]
        + [[nodes[nid][0], nodes[nid][1]] for nid in path]
        + [[lat2, lon2]]
    )


# ─── Public API ───────────────────────────────────────────────────────────────
def get_cached_geometry(db: Session, key: str) -> Optional[list]:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    if row:
        return json.loads(row.geometry_json)
    return None


def save_geometry(db: Session, key: str, geometry: list) -> None:
    db.add(RouteCache(cache_key=key, geometry_json=json.dumps(geometry)))
    try:
        db.commit()
    except Exception:
        db.rollback()


async def fetch_and_cache(
    db: Session, lat1: float, lon1: float, lat2: float, lon2: float
) -> Optional[list]:
    """
    Check DB cache first. If missing, fetch from Overpass, store result,
    and return geometry (or None when no railway path is found).
    """
    key = make_cache_key(lat1, lon1, lat2, lon2)

    cached = get_cached_geometry(db, key)
    if cached is not None:
        return cached

    geometry = await _fetch_from_overpass(lat1, lon1, lat2, lon2)

    if geometry:
        save_geometry(db, key, geometry)
    else:
        # Store a sentinel so we don't hammer Overpass repeatedly for the same
        # route pair that has no rail coverage
        save_geometry(db, key, [])

    return geometry if geometry else None
