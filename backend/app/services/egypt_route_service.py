from __future__ import annotations

import heapq
import json
import logging
import math
import threading
from pathlib import Path
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)

EGYPT_BOUNDS = {
    "south": 21.5,
    "north": 31.9,
    "west": 24.5,
    "east": 36.2,
}

GRAPH_NODE_SNAP_RADIUS_DEGREES = 0.04
GRAPH_NODE_CANDIDATE_LIMIT = 12
MAX_ROUTE_LENGTH_RATIO = 4.5

_dataset_lock = threading.Lock()
_dataset_cache: Optional["_EgyptRouteDataset"] = None


def is_egypt_coordinate(lat: float, lon: float) -> bool:
    return (
        EGYPT_BOUNDS["south"] <= lat <= EGYPT_BOUNDS["north"]
        and EGYPT_BOUNDS["west"] <= lon <= EGYPT_BOUNDS["east"]
    )


def _distance_sq(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _polyline_length(points: list[list[float]]) -> float:
    total = 0.0
    for index in range(len(points) - 1):
        total += math.sqrt(_distance_sq(points[index], points[index + 1]))
    return total


def _dedupe_points(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for lat, lon in points:
        if not deduped or deduped[-1][0] != lat or deduped[-1][1] != lon:
            deduped.append([lat, lon])
    return deduped


def _graph_node_key(point: list[float]) -> str:
    return f"{point[0]:.6f},{point[1]:.6f}"


def _nearest_graph_candidates(
    graph_nodes: dict[str, list[float]],
    target: list[float],
    limit: int = GRAPH_NODE_CANDIDATE_LIMIT,
) -> list[tuple[str, list[float], float]]:
    candidates: list[tuple[str, list[float], float]] = []
    for key, point in graph_nodes.items():
        candidates.append((key, point, _distance_sq(point, target)))
    candidates.sort(key=lambda item: item[2])
    return candidates[:limit]


def _shortest_graph_path(
    adjacency: dict[str, list[tuple[str, float]]],
    graph_nodes: dict[str, list[float]],
    start_key: str,
    end_key: str,
) -> Optional[list[list[float]]]:
    queue: list[tuple[float, str]] = [(0.0, start_key)]
    distances = {start_key: 0.0}
    previous: dict[str, Optional[str]] = {start_key: None}

    while queue:
        current_distance, current_key = heapq.heappop(queue)
        if current_key == end_key:
            break
        if current_distance > distances.get(current_key, float("inf")):
            continue
        for next_key, edge_weight in adjacency.get(current_key, []):
            next_distance = current_distance + edge_weight
            if next_distance >= distances.get(next_key, float("inf")):
                continue
            distances[next_key] = next_distance
            previous[next_key] = current_key
            heapq.heappush(queue, (next_distance, next_key))

    if end_key not in previous:
        return None

    keys: list[str] = []
    current_key: Optional[str] = end_key
    while current_key is not None:
        keys.append(current_key)
        current_key = previous.get(current_key)
    keys.reverse()
    return [graph_nodes[key] for key in keys if key in graph_nodes]


class _EgyptRouteDataset:
    def __init__(self, path: Path):
        self.path = path
        self._graph_nodes: Optional[dict[str, list[float]]] = None
        self._adjacency: Optional[dict[str, list[tuple[str, float]]]] = None

    def _load_graph(self) -> tuple[dict[str, list[float]], dict[str, list[tuple[str, float]]]]:
        if self._graph_nodes is not None and self._adjacency is not None:
            return self._graph_nodes, self._adjacency

        graph_nodes: dict[str, list[float]] = {}
        adjacency: dict[str, list[tuple[str, float]]] = {}

        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for feature in data.get("features") or []:
            props = feature.get("properties") or {}
            if str(props.get("railway") or "").strip().lower() not in {"rail", "light_rail", "subway", "tram"}:
                continue

            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "LineString":
                continue
            coordinates = geometry.get("coordinates") or []
            points = _dedupe_points([[float(latlon[1]), float(latlon[0])] for latlon in coordinates if len(latlon) >= 2])
            if len(points) < 2:
                continue

            for index in range(len(points) - 1):
                point_a = points[index]
                point_b = points[index + 1]
                key_a = _graph_node_key(point_a)
                key_b = _graph_node_key(point_b)
                graph_nodes[key_a] = point_a
                graph_nodes[key_b] = point_b
                weight = math.sqrt(_distance_sq(point_a, point_b))
                adjacency.setdefault(key_a, []).append((key_b, weight))
                adjacency.setdefault(key_b, []).append((key_a, weight))

        self._graph_nodes = graph_nodes
        self._adjacency = adjacency
        return graph_nodes, adjacency

    def build_route(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[dict]:
        graph_nodes, adjacency = self._load_graph()
        if not graph_nodes:
            return None

        start = [lat1, lon1]
        end = [lat2, lon2]
        max_snap_dist = GRAPH_NODE_SNAP_RADIUS_DEGREES ** 2
        start_candidates = [c for c in _nearest_graph_candidates(graph_nodes, start) if c[2] <= max_snap_dist]
        end_candidates = [c for c in _nearest_graph_candidates(graph_nodes, end) if c[2] <= max_snap_dist]

        if not start_candidates or not end_candidates:
            logger.info(
                "egypt_geojson: route failed no_snap_candidates for %.5f,%.5f -> %.5f,%.5f start_candidates=%s end_candidates=%s",
                lat1, lon1, lat2, lon2, len(start_candidates), len(end_candidates),
            )
            return None

        best_geometry = None
        best_start_point = None
        best_end_point = None
        best_score = None

        for start_key, start_point, start_dist in start_candidates:
            for end_key, end_point, end_dist in end_candidates:
                geometry = _shortest_graph_path(adjacency, graph_nodes, start_key, end_key)
                if not geometry or len(geometry) < 2:
                    continue
                route_length = _polyline_length(geometry)
                score = route_length + start_dist + end_dist
                if best_score is None or score < best_score:
                    best_geometry = geometry
                    best_start_point = start_point
                    best_end_point = end_point
                    best_score = score

        if not best_geometry or best_start_point is None or best_end_point is None:
            logger.info(
                "egypt_geojson: route failed no_connected_path for %.5f,%.5f -> %.5f,%.5f start_candidates=%s end_candidates=%s",
                lat1, lon1, lat2, lon2, len(start_candidates), len(end_candidates),
            )
            return None

        direct_length = math.sqrt(_distance_sq(start, end))
        route_length = _polyline_length(best_geometry)
        if direct_length > 0 and route_length > direct_length * MAX_ROUTE_LENGTH_RATIO:
            logger.info(
                "egypt_geojson: route failed length_ratio for %.5f,%.5f -> %.5f,%.5f route=%.6f direct=%.6f max_ratio=%.2f",
                lat1, lon1, lat2, lon2, route_length, direct_length, MAX_ROUTE_LENGTH_RATIO,
            )
            return None

        logger.info(
            "egypt_geojson: route accepted for %.5f,%.5f -> %.5f,%.5f points=%s",
            lat1, lon1, lat2, lon2, len(best_geometry),
        )
        return {
            "geometry": best_geometry,
            "anchor_start": best_start_point,
            "anchor_end": best_end_point,
        }


def _get_dataset() -> Optional[_EgyptRouteDataset]:
    global _dataset_cache

    configured_path = Path(settings.EGYPT_RAIL_GEOJSON_PATH.strip()) if settings.EGYPT_RAIL_GEOJSON_PATH.strip() else None
    if not configured_path:
        return None
    if not configured_path.is_absolute():
        configured_path = (Path(__file__).resolve().parents[3] / configured_path).resolve()
    if not configured_path.exists():
        logger.warning("egypt_geojson: configured file not found at %s", configured_path)
        return None

    with _dataset_lock:
        if _dataset_cache is None or _dataset_cache.path != configured_path:
            _dataset_cache = _EgyptRouteDataset(configured_path)
    return _dataset_cache


def build_route_from_egypt_geojson(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[dict]:
    if not (is_egypt_coordinate(lat1, lon1) and is_egypt_coordinate(lat2, lon2)):
        return None
    dataset = _get_dataset()
    if not dataset:
        return None
    return dataset.build_route(lat1, lon1, lat2, lon2)
