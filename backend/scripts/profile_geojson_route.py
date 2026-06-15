import argparse
import ctypes
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.geojson_transport_service import build_train_route_from_geojson
from app.services.train_route_service import _fetch_from_osm_railway


class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def _process_memory_snapshot() -> dict[str, float]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    get_process_memory_info.restype = ctypes.c_int

    counters = _PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(counters)
    ok = get_process_memory_info(get_current_process(), ctypes.byref(counters), counters.cb)
    if not ok:
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")

    return {
        "working_mb": round(counters.WorkingSetSize / (1024 * 1024), 2),
        "peak_working_mb": round(counters.PeakWorkingSetSize / (1024 * 1024), 2),
        "private_mb": round(counters.PrivateUsage / (1024 * 1024), 2),
        "peak_pagefile_mb": round(counters.PeakPagefileUsage / (1024 * 1024), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat1", type=float, required=True)
    parser.add_argument("--lon1", type=float, required=True)
    parser.add_argument("--lat2", type=float, required=True)
    parser.add_argument("--lon2", type=float, required=True)
    parser.add_argument("--country", type=str, default="")
    parser.add_argument("--mode", choices=("geojson", "osm"), default="geojson")
    args = parser.parse_args()

    peak = {
        "working_mb": 0.0,
        "private_mb": 0.0,
    }
    stop_event = threading.Event()

    def sample_memory() -> None:
        while not stop_event.is_set():
            try:
                snapshot = _process_memory_snapshot()
                peak["working_mb"] = max(peak["working_mb"], snapshot["working_mb"])
                peak["private_mb"] = max(peak["private_mb"], snapshot["private_mb"])
            except OSError:
                pass
            time.sleep(0.1)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    before = _process_memory_snapshot()
    sampler.start()
    start = time.perf_counter()
    if args.mode == "geojson":
        route = build_train_route_from_geojson(
            args.lat1,
            args.lon1,
            args.lat2,
            args.lon2,
            country_hint=args.country or None,
        )
    else:
        route = asyncio.run(
            _fetch_from_osm_railway(
                args.lat1,
                args.lon1,
                args.lat2,
                args.lon2,
            )
        )
    elapsed = time.perf_counter() - start
    stop_event.set()
    sampler.join(timeout=1.0)
    after = _process_memory_snapshot()
    payload = {
        "elapsed_seconds": round(elapsed, 3),
        "provider": (route or {}).get("provider"),
        "route_points": len((route or {}).get("geometry") or []),
        "has_route": bool(route and route.get("geometry")),
        "mode": args.mode,
        "memory_before": before,
        "memory_after": after,
        "peak_sampled": peak,
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
