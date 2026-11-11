"""Retrieval-grounded incident briefs.

Every sentence is assembled from retrieved historical incidents or structured
cluster facts; unsupported facts are never invented. An optional
OpenAI-compatible endpoint can rewrite the brief, but it receives only the
same retrieved context and falls back to the deterministic template on error.
"""
from __future__ import annotations

import os

import httpx

from .config import PLAYBOOKS


def _short(text: str, limit: int = 96) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def synthesize_incident(
    node_label: str,
    category: str,
    merged_reports: int,
    window_min: int,
    canonical_description: str,
    priority: str,
    sla_minutes: int,
    retrieved: list[dict],
) -> tuple[str, list[str]]:
    evidence_ids = [str(item.get("report_id", "")) for item in retrieved if item.get("report_id")]
    citations = []
    for idx, item in enumerate(retrieved[:3], start=1):
        citations.append(
            f"[{idx}] {_short(item.get('description', 'reported issue'))} "
            f"({item.get('category', category)}, resolved in {int(item.get('resolve_minutes', 0))} min)"
        )
    evidence_text = " ".join(citations) if citations else "No close historical match; using the current report only."
    summary = (
        f"{merged_reports} report(s) within {window_min} min at {node_label} describe a {category} issue. "
        f"Canonical signal: \u201c{_short(canonical_description, 120)}\u201d. "
        f"Matched history: {evidence_text} "
        f"Triage: {priority}, {sla_minutes}-minute SLA. "
        f"Playbook: {PLAYBOOKS.get(category, 'Dispatch the on-call crew and verify restoration.')}"
    )

    api_key = os.getenv("CAMPUSPULSE_LLM_API_KEY")
    base_url = os.getenv("CAMPUSPULSE_LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("CAMPUSPULSE_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return summary, evidence_ids

    prompt = (
        "Rewrite the incident brief in 3 sentences for a campus operations lead. "
        "Use ONLY facts present in the JSON context. Do not invent causes, names or numbers. "
        "Keep the citations. Context:\n"
        f"{summary}"
    )
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=8.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        return (content or summary), evidence_ids
    except Exception:
        return summary, evidence_ids
