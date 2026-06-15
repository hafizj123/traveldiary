from __future__ import annotations

import logging
import os
import sys

from .services.geojson_import_service import run_geojson_import_task


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    task_id = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not task_id:
        print("GeoJSON import worker requires a task id.", file=sys.stderr)
        return 2

    print(f"GeoJSON import worker pid={os.getpid()} task_id={task_id} starting")
    try:
        run_geojson_import_task(task_id)
    except Exception:
        logging.exception("GeoJSON import worker failed for task %s", task_id)
        return 1
    print(f"GeoJSON import worker pid={os.getpid()} task_id={task_id} finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
