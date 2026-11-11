"""Export the dashboard payload consumed by Next.js / Vercel."""
from __future__ import annotations

from .engine import CampusPulseEngine


def main() -> None:
    engine = CampusPulseEngine.load_or_bootstrap()
    path = engine.export_snapshot()
    snapshot = engine.snapshot()
    print(f"[snapshot] wrote {path} ({len(snapshot.places)} places, "
          f"{len(snapshot.triage['queue'])} queued incidents, CSI {snapshot.csi.score})")


if __name__ == "__main__":
    main()
