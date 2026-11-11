"""Shared data-quality layer: validation, outlier repair and incident dedupe.

Both the telemetry stream (pillars 1, 3, 4) and the incident stream (pillar 2)
pass through this module before any model sees them. The dedupe step is a
union-find over gated pairs: same category, same/adjacent node, tight time
window, and MiniLM (or fallback) cosine above the backend threshold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    CATEGORIES,
    DEDUPE_RADIUS_M,
    DEDUPE_WINDOW_MIN,
)
from .embeddings import get_embedder
from .graph import CampusGraph
from .schemas import RefineReport


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def refine_telemetry(df: pd.DataFrame) -> tuple[pd.DataFrame, RefineReport]:
    raw = len(df)
    report = RefineReport(raw_rows=raw)
    work = df.copy()
    work["ts"] = pd.to_datetime(work["ts"], errors="coerce")
    work = work.dropna(subset=["ts", "node_id", "capacity"])
    work = work[work["capacity"] > 0]
    work = work[work["occupancy"] >= 0]
    dropped_negative = raw - len(work)
    if dropped_negative:
        report.issues.append(f"dropped {dropped_negative} non-physical readings")

    before = len(work)
    work = work.sort_values("ts").drop_duplicates(subset=["node_id", "ts"], keep="last")
    report.duplicate_rows_removed = before - len(work)

    ceiling = (work["capacity"] * 1.05).astype(float)
    clipped = int((work["occupancy"] > ceiling).sum())
    work["occupancy"] = np.minimum(work["occupancy"], ceiling).round().astype(int)
    if clipped:
        report.issues.append(f"winsorised {clipped} sensor spikes at 105% capacity")

    work["queue_len"] = work["queue_len"].clip(lower=0).fillna(0).astype(int)
    work["wait_min"] = work["wait_min"].clip(lower=0).fillna(0.0)

    gaps = 0
    for _, group in work.sort_values("ts").groupby("node_id"):
        if len(group) > 1:
            gaps += int((group["ts"].diff().dt.total_seconds() > 45 * 60).sum())
    report.staleness_gaps = gaps
    if gaps:
        report.issues.append(f"{gaps} telemetry gaps over 45 minutes flagged")

    report.accepted_rows = len(work)
    report.dropped_rows = raw - len(work)
    report.quality_score = round(
        float(len(work)) / max(raw, 1) * (1.0 - min(0.15, gaps / max(len(work), 1))), 4
    )
    return work.sort_values(["node_id", "ts"]).reset_index(drop=True), report


def refine_incidents(
    df: pd.DataFrame,
    graph: CampusGraph,
    embedder=None,
    threshold: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, RefineReport]:
    embedder = embedder or get_embedder()
    threshold = threshold if threshold is not None else embedder.dedupe_threshold
    report = RefineReport(raw_rows=len(df))
    work = df.copy()
    work["reported_at"] = pd.to_datetime(work["reported_at"], errors="coerce")
    work["description"] = work["description"].astype(str).str.strip()
    valid = (
        work["reported_at"].notna()
        & work["node_id"].isin(graph.nodes)
        & work["category"].isin(CATEGORIES)
        & (work["description"].str.len() >= 8)
    )
    work = work[valid].sort_values("reported_at").reset_index(drop=True)
    report.accepted_rows = len(work)
    report.dropped_rows = report.raw_rows - len(work)

    if work.empty:
        report.quality_score = 0.0
        return work, pd.DataFrame(), report

    embeddings = embedder.encode(work["description"].tolist())
    size = len(work)
    uf = _UnionFind(size)
    pair_similarities: dict[tuple[int, int], float] = {}
    window = np.timedelta64(DEDUPE_WINDOW_MIN, "m")
    times = work["reported_at"].to_numpy()
    nodes = work["node_id"].tolist()
    categories = work["category"].tolist()

    for i in range(size):
        for j in range(i + 1, size):
            if times[j] - times[i] > window:
                break
            if categories[i] != categories[j]:
                continue
            if nodes[i] != nodes[j] and graph.distance_m(nodes[i], nodes[j]) > DEDUPE_RADIUS_M:
                continue
            similarity = float(np.dot(embeddings[i], embeddings[j]))
            if similarity >= threshold:
                uf.union(i, j)
                pair_similarities[(i, j)] = similarity

    roots = [uf.find(i) for i in range(size)]
    root_to_cluster: dict[int, str] = {}
    cluster_ids: list[str] = []
    for root in roots:
        if root not in root_to_cluster:
            root_to_cluster[root] = f"cl-{len(root_to_cluster):04d}"
        cluster_ids.append(root_to_cluster[root])

    work["pred_cluster_id"] = cluster_ids
    sizes = work.groupby("pred_cluster_id").size()
    work["cluster_size"] = work["pred_cluster_id"].map(sizes).astype(int)

    similarity_by_cluster: dict[str, list[float]] = {}
    for (i, j), sim in pair_similarities.items():
        similarity_by_cluster.setdefault(cluster_ids[i], []).append(sim)

    clusters = []
    for cluster_id, group in work.groupby("pred_cluster_id", sort=True):
        canonical = group.iloc[0]
        sims = similarity_by_cluster.get(cluster_id, [])
        clusters.append(
            {
                "cluster_id": cluster_id,
                "node_id": canonical["node_id"],
                "category": canonical["category"],
                "reported_at": canonical["reported_at"],
                "merged_reports": len(group),
                "canonical_description": canonical["description"],
                "mean_similarity": float(np.mean(sims)) if sims else 0.0,
                "report_ids": list(group["report_id"]),
            }
        )
    cluster_frame = pd.DataFrame(clusters).sort_values("reported_at").reset_index(drop=True)

    report.incident_reports_merged = int(len(work) - len(cluster_frame))
    report.clusters_formed = len(cluster_frame)
    report.quality_score = round(
        float(len(work)) / max(report.raw_rows, 1) * (1.0 - 0.05 * min(1.0, len(report.issues))), 4
    )
    if report.incident_reports_merged:
        report.issues.append(
            f"collapsed {report.incident_reports_merged} duplicate reports into {len(cluster_frame)} canonical incidents"
        )
    return work, cluster_frame, report
