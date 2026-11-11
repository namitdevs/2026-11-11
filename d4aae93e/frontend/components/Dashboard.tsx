"use client";

import { useMemo, useState } from "react";
import type { ForecastBundle, Place, RouteResult, Snapshot } from "@/lib/types";
import CampusMap from "./CampusMap";
import CampusPhotoMap from "./CampusPhotoMap";
import ForecastChart from "./ForecastChart";
import { Badge, Card, Meter, PriorityBadge, SectionHeading, Stat } from "./ui";

const NAV = [
  ["overview", "Overview"],
  ["navigate", "Navigate"],
  ["predict", "Predict"],
  ["triage", "Triage"],
  ["mess", "Mess"],
  ["benchmarks", "Benchmarks"],
];

const KIND_TONE: Record<string, string> = {
  food: "amber",
  academic: "sky",
  transit: "mint",
  safety: "rose",
  residential: "violet",
  service: "slate",
  sports: "mint",
  landmark: "amber",
};

const fmt = (value: unknown, digits = 2) =>
  typeof value === "number" ? value.toFixed(digits) : "—";

const hhmm = (value: string) => (value ? value.slice(11, 16) : "—");

function CsiDial({ snapshot }: { snapshot: Snapshot }) {
  const score = Math.max(0, Math.min(100, snapshot.csi.score));
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const color = score >= 65 ? "#ff6b81" : score >= 45 ? "#ffb545" : "#35f0b0";
  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:gap-6">
      <div className="relative h-36 w-36 shrink-0">
        <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
          <circle cx="70" cy="70" r={radius} fill="none" stroke="#1b2740" strokeWidth="10" />
          <circle
            cx="70"
            cy="70"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - score / 100)}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="mono text-[9px] uppercase tracking-[0.2em] text-slate-500">campus stress</div>
            <div className="text-3xl font-semibold text-white">{score.toFixed(0)}</div>
            <div className="text-[11px] text-slate-400">{snapshot.csi.label}</div>
          </div>
        </div>
      </div>
      <div className="w-full space-y-2.5">
        {snapshot.csi.components.map((component) => (
          <div key={component.key}>
            <div className="mb-1 flex justify-between text-[11px] text-slate-400">
              <span>{component.label}</span>
              <span className="mono">{component.value.toFixed(0)}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${component.value}%`,
                  background: component.value >= 65 ? "#ff6b81" : component.value >= 45 ? "#ffb545" : "#35f0b0",
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PriorityFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {["all", "P0", "P1", "P2", "P3"].map((item) => (
        <button
          key={item}
          onClick={() => onChange(item)}
          className={`mono rounded-full border px-3 py-1 text-[10px] uppercase tracking-wider transition ${
            value === item
              ? "border-mint/40 bg-mint/15 text-mint"
              : "border-line bg-panel/60 text-slate-400 hover:border-slate-500"
          }`}
        >
          {item}
        </button>
      ))}
    </div>
  );
}

function BenchTable({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; values: string[] }[];
}) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line/70 px-4 py-3 text-sm font-medium text-white">{title}</div>
      <div className="overflow-x-auto p-4">
        <table className="w-full min-w-[380px] text-left text-xs">
          <tbody className="divide-y divide-line/60">
            {rows.map((row, index) => (
              <tr key={row.label} className={index === 0 ? "text-mint" : "text-slate-400"}>
                <td className="py-2 pr-4 font-medium">{row.label}</td>
                {row.values.map((value, valueIndex) => (
                  <td key={valueIndex} className="mono py-2 pr-4 text-right">
                    {value}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function Dashboard({ snapshot }: { snapshot: Snapshot }) {
  const [origin, setOrigin] = useState("gate_main");
  const [placeId, setPlaceId] = useState("central-library");
  const [mode, setMode] = useState<"fastest" | "safest">("safest");
  const [query, setQuery] = useState("cold coffee");
  const [forecastNode, setForecastNode] = useState("library");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [cartRequested, setCartRequested] = useState(false);

  const place = snapshot.places.find((item) => item.id === placeId) ?? snapshot.places[0];
  const routePair =
    snapshot.routes[origin]?.[place.id] ??
    snapshot.routes["gate_main"]?.[place.id] ??
    null;
  const route: RouteResult | null = routePair?.[mode] ?? null;
  const dispatch = snapshot.dispatches[origin];
  const forecast: ForecastBundle =
    snapshot.forecasts[forecastNode] ?? Object.values(snapshot.forecasts)[0];
  const nodeLabels = useMemo(
    () => Object.fromEntries(snapshot.graph.nodes.map((node) => [node.id, node.label])),
    [snapshot.graph.nodes],
  );
  const originOptions = ["gate_main", "gate_north", "hostel_g1"];
  const searchResults = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return snapshot.places.slice(0, 6);
    return snapshot.places
      .map((item) => {
        const haystack = [item.name, item.category, item.floor, item.landmark, ...item.aliases]
          .join(" ")
          .toLowerCase();
        let score = haystack.includes(needle) ? 10 : 0;
        if (item.name.toLowerCase().startsWith(needle)) score += 5;
        if (item.aliases.some((alias) => alias.toLowerCase() === needle)) score += 8;
        return { item, score };
      })
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6)
      .map((entry) => entry.item);
  }, [query, snapshot.places]);
  const queue = snapshot.triage.queue.filter(
    (item) => priorityFilter === "all" || item.priority === priorityFilter,
  );
  const messTotals = useMemo(() => {
    const saved = snapshot.mess.reduce((total, plan) => total + Math.max(0, plan.waste_saved_kg), 0);
    const head = snapshot.mess.reduce((total, plan) => total + plan.predicted_headcount, 0);
    const confidence =
      snapshot.mess.reduce((total, plan) => total + plan.confidence, 0) / Math.max(snapshot.mess.length, 1);
    return { saved, head, confidence };
  }, [snapshot.mess]);
  const bench = snapshot.benchmark ?? {};
  const wifiCluster = snapshot.triage.queue.find((item) => item.category === "wifi");
  const benchRows = {
    forecast: [
      {
        label: "LightGBM/XGBoost blend",
        values: [
          fmt(bench?.forecast?.model?.mae_occupancy_ratio, 4),
          fmt(bench?.forecast?.model?.r2_occupancy_ratio, 4),
        ],
      },
      {
        label: "Seasonal naive 24h",
        values: [
          fmt(bench?.forecast?.baselines?.seasonal_naive_24h?.mae, 4),
          fmt(bench?.forecast?.baselines?.seasonal_naive_24h?.r2, 4),
        ],
      },
      {
        label: "Persistence",
        values: [
          fmt(bench?.forecast?.baselines?.persistence?.mae, 4),
          fmt(bench?.forecast?.baselines?.persistence?.r2, 4),
        ],
      },
      {
        label: "Ridge",
        values: [fmt(bench?.forecast?.baselines?.ridge?.mae, 4), fmt(bench?.forecast?.baselines?.ridge?.r2, 4)],
      },
    ],
    triage: [
      {
        label: "XGBoost (group split)",
        values: [fmt(bench?.triage?.model?.macro_f1, 4), fmt(bench?.triage?.model?.accuracy, 4)],
      },
      {
        label: "LogReg structured",
        values: [
          fmt(bench?.triage?.baselines?.logreg_structured?.macro_f1, 4),
          fmt(bench?.triage?.baselines?.logreg_structured?.accuracy, 4),
        ],
      },
      {
        label: "Majority class",
        values: [
          fmt(bench?.triage?.baselines?.majority_class?.macro_f1, 4),
          fmt(bench?.triage?.baselines?.majority_class?.accuracy, 4),
        ],
      },
    ],
    mess: [
      {
        label: "LightGBM",
        values: [fmt(bench?.mess?.model?.headcount_mae, 2), fmt(bench?.mess?.model?.headcount_mape_pct, 2)],
      },
      {
        label: "Seasonal same-weekday",
        values: [
          fmt(bench?.mess?.baseline_seasonal?.headcount_mae, 2),
          fmt(bench?.mess?.baseline_seasonal?.headcount_mape_pct, 2),
        ],
      },
    ],
  };

  const selectPlace = (item: Place) => {
    setPlaceId(item.id);
    setCartRequested(false);
  };

  const presets = [
    { label: "cold coffee", query: "cold coffee", id: "food-court" },
    { label: "vending machine", query: "vending machine", id: "tan-block" },
    { label: "Central Library", query: "central library", id: "central-library" },
    { label: "Prithvi Hall", query: "prithvi hall", id: "prithvi-hall" },
  ];

  return (
    <div className="min-h-screen bg-ink text-slate-200">
      <header className="sticky top-0 z-40 border-b border-line/70 bg-ink/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 md:px-8">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-mint/30 bg-mint/10 text-xs font-bold text-mint">
              CP
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-white">CampusPulse</div>
              <div className="mono text-[9px] uppercase tracking-[0.22em] text-slate-500">
                unified campus intelligence
              </div>
            </div>
          </div>
          <nav className="hidden items-center gap-1 lg:flex">
            {NAV.map(([id, label]) => (
              <a
                key={id}
                href={`#${id}`}
                className="rounded-full px-3 py-1.5 text-xs text-slate-400 transition hover:bg-white/5 hover:text-white"
              >
                {label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2 text-[10px] text-slate-400">
            <a
              href="/"
              className="rounded-full border border-line px-3 py-1.5 text-xs text-slate-300 transition hover:border-mint/40 hover:text-white"
            >
              Campus app
            </a>
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />
            <span className="mono">replay 06 Feb 20:30</span>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden border-b border-line/60">
        <div className="grid-bg absolute inset-0 opacity-70" />
        <div className="absolute -right-24 -top-40 h-96 w-96 rounded-full bg-mint/10 blur-3xl" />
        <div className="relative mx-auto grid max-w-7xl gap-10 px-4 py-12 md:px-8 lg:grid-cols-[1.35fr_0.65fr] lg:py-16">
          <div className="fade-in">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="mint">Smart Campus · student life</Badge>
              <Badge tone="sky">digital twin replay</Badge>
              <Badge tone="violet">5 decisions · 1 graph</Badge>
            </div>
            <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight text-white md:text-6xl">
              One campus graph.
              <br />
              <span className="bg-gradient-to-r from-mint via-sky to-violet-300 bg-clip-text text-transparent">
                Five decisions, predicted.
              </span>
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-relaxed text-slate-400 md:text-base">
              Freshers find any block, vending machine or cafeteria in seconds. Golf carts are dispatched by
              predicted wait, not luck. The same spatial-temporal engine forecasts library pressure, collapses
              outage floods into one incident, plans mess prep, and reroutes night walks around risk.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <a
                href="#navigate"
                className="rounded-xl bg-mint px-4 py-2.5 text-sm font-semibold text-[#04120d] transition hover:bg-mint/90"
              >
                Find a place
              </a>
              <a
                href="#benchmarks"
                className="rounded-xl border border-line bg-panel/60 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Inspect the benchmark
              </a>
            </div>
            <div className="mt-7 grid max-w-xl grid-cols-2 gap-x-6 gap-y-2 text-[11px] text-slate-500 sm:grid-cols-3">
              <div><span className="mono text-mint">01</span> crowd and queue forecasts</div>
              <div><span className="mono text-mint">02</span> self-healing incident triage</div>
              <div><span className="mono text-mint">03</span> mess demand and waste</div>
              <div><span className="mono text-mint">04</span> risk-weighted safe routing</div>
              <div><span className="mono text-mint">05</span> wayfinding and cart dispatch</div>
              <div><span className="mono text-mint">06</span> one refined telemetry stream</div>
            </div>
          </div>
          <Card className="fade-in p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-sm font-medium text-white">Campus Stress Index</div>
              <Badge tone={snapshot.csi.score >= 65 ? "rose" : snapshot.csi.score >= 45 ? "amber" : "mint"}>
                {snapshot.csi.label}
              </Badge>
            </div>
            <CsiDial snapshot={snapshot} />
            <div className="mt-5 border-t border-line/70 pt-4 text-[11px] leading-relaxed text-slate-500">
              Composite of crowd pressure, incident load, mess variance, night mobility risk and cart response.
              Every component is computed from the same refined event stream.
            </div>
          </Card>
        </div>
      </section>

      <section className="mx-auto -mt-6 max-w-7xl px-4 md:px-8">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat
            label="Busiest right now"
            value={String(snapshot.kpis.busiest_node)}
            sub={`30-min pressure rank · ${snapshot.hotspots.length} sensor nodes`}
          />
          <Stat
            label="P0 / P1 incidents"
            value={Number(snapshot.kpis.p0_p1)}
            sub={`${snapshot.triage.stats.reports_last_24h} reports collapsed into ${snapshot.triage.stats.clusters_last_24h} incidents`}
            tone={Number(snapshot.kpis.p0_p1) > 0 ? "text-amber" : "text-mint"}
          />
          <Stat
            label="Cart ETA · Main Gate"
            value={`${fmt(snapshot.kpis.cart_wait_min, 1)} min`}
            sub={`${snapshot.kpis.carts_available} of 6 carts available`}
            tone="text-sky"
          />
          <Stat
            label="Waste avoided · next meals"
            value={`${fmt(snapshot.kpis.waste_saved_kg, 0)} kg`}
            sub={`vs 12% over-prep baseline · refine score ${fmt(snapshot.kpis.quality_score, 3)}`}
            tone="text-mint"
          />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-12 md:px-8">
        <SectionHeading
          id="overview"
          eyebrow="Live spatial state"
          title="The whole campus on one graph"
          description="Every node carries live telemetry, every edge carries a risk weight. The four predictive models and the wayfinding layer read the same structure, so one event propagates everywhere."
        />
        <div className="grid gap-4 lg:grid-cols-[1.55fr_1fr]">
          <Card className="p-3">
            <CampusMap
              nodes={snapshot.graph.nodes}
              edges={snapshot.graph.edges}
              route={route}
              carts={snapshot.carts}
              places={snapshot.places}
              selectedNode={place.node_id}
              onPickNode={(nodeId, selected) => {
                const target = snapshot.places.find((item) => item.id === selected);
                if (target) selectPlace(target);
              }}
            />
          </Card>
          <div className="space-y-4">
            <Card className="p-5">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-medium text-white">Operator brief</div>
                <Badge tone="mint">grounded</Badge>
              </div>
              <ol className="space-y-3">
                {snapshot.insights.map((insight, index) => (
                  <li key={index} className="flex gap-3 text-xs leading-relaxed text-slate-400">
                    <span className="mono mt-0.5 text-[10px] text-mint">{String(index + 1).padStart(2, "0")}</span>
                    <span>{insight}</span>
                  </li>
                ))}
              </ol>
            </Card>
            <Card className="p-5">
              <div className="mb-3 text-sm font-medium text-white">One event, five views</div>
              <div className="space-y-2 text-xs text-slate-400">
                <div className="flex items-start gap-2"><Badge tone="rose">wi-fi flood</Badge><span>{wifiCluster?.merged_reports ?? 23} paraphrased reports at Prithvi Hall</span></div>
                <div className="flex items-start gap-2"><Badge tone="sky">refiner</Badge><span>collapse to 1 canonical incident, similarity gate</span></div>
                <div className="flex items-start gap-2"><Badge tone="amber">triage</Badge><span>P1 with an SLA and a retrieval-grounded playbook</span></div>
                <div className="flex items-start gap-2"><Badge tone="mint">mobility</Badge><span>incident density reweights night edges and cart dispatch</span></div>
                <div className="flex items-start gap-2"><Badge tone="violet">mess</Badge><span>next-day prep recalculated from the same calendar and weather state</span></div>
              </div>
            </Card>
            <Card className="p-5">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-medium text-white">Refiner report</div>
                <Badge tone="slate">{fmt(snapshot.refine.quality_score, 3)} quality</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><div className="text-slate-500">raw rows</div><div className="mono text-white">{snapshot.refine.raw_rows.toLocaleString()}</div></div>
                <div><div className="text-slate-500">accepted</div><div className="mono text-white">{snapshot.refine.accepted_rows.toLocaleString()}</div></div>
                <div><div className="text-slate-500">telemetry dupes</div><div className="mono text-white">{snapshot.refine.duplicate_rows_removed}</div></div>
                <div><div className="text-slate-500">reports merged</div><div className="mono text-mint">{snapshot.refine.incident_reports_merged}</div></div>
              </div>
              <div className="mt-3 space-y-1 text-[10px] leading-relaxed text-slate-500">
                {snapshot.refine.issues.slice(0, 3).map((issue, index) => (
                  <div key={index}>· {issue}</div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-10 md:px-8">
        <SectionHeading
          id="navigate"
          eyebrow="Pillar 05 · wayfinding and micro-transit"
          title="Search like a fresher. Route like an operator."
          description="Type a craving, a machine or a department. The graph returns a walkable route, a last-50-metre landmark cue, a risk score and the nearest golf cart with a predicted ETA."
        />
        <Card className="mb-4 overflow-hidden p-1.5">
          <CampusPhotoMap
            nodes={snapshot.graph.nodes}
            places={snapshot.places}
            carts={snapshot.carts}
            fastest={routePair?.fastest ?? null}
            safest={routePair?.safest ?? null}
            mode={mode}
            origin={origin}
            selectedNode={place.node_id}
            onPickNode={(nodeId, selected) => {
              const target = snapshot.places.find((item) => item.id === selected);
              if (target) selectPlace(target);
            }}
          />
          <p className="px-2 py-1.5 text-[9px] leading-relaxed text-slate-600">
            Campus image: TIET map by thapar.helpclub29. The painted route is a graph projection for orientation;
            on-ground walkways and signage remain authoritative. Distances, risk and ETAs come from the engine, not the pixels.
          </p>
        </Card>
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="p-5">
            <div className="mb-3 text-sm font-medium text-white">Where do you want to go?</div>
            <div className="relative">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="cold coffee, vending machine, CS block..."
                className="w-full rounded-xl border border-line bg-[#070d18] px-3 py-2.5 pr-9 text-sm text-white outline-none transition focus:border-mint/60"
              />
              <svg viewBox="0 0 24 24" className="absolute right-3 top-3 h-4 w-4 text-slate-500" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {presets.map((preset) => (
                <button
                  key={preset.id}
                  onClick={() => {
                    setQuery(preset.query);
                    const target = snapshot.places.find((item) => item.id === preset.id);
                    if (target) selectPlace(target);
                  }}
                  className={`rounded-full border px-2.5 py-1 text-[10px] transition ${
                    placeId === preset.id
                      ? "border-mint/40 bg-mint/10 text-mint"
                      : "border-line text-slate-500 hover:border-slate-500 hover:text-slate-300"
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <div className="mt-3 space-y-1.5">
              {searchResults.map((item) => (
                <button
                  key={item.id}
                  onClick={() => selectPlace(item)}
                  className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                    item.id === place.id
                      ? "border-mint/40 bg-mint/10"
                      : "border-transparent hover:border-line hover:bg-white/[0.03]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-white">{item.name}</span>
                    <Badge tone={KIND_TONE[item.category] ?? "slate"}>{item.category}</Badge>
                  </div>
                  <div className="mt-0.5 text-[10px] text-slate-500">
                    {item.floor} · {item.landmark}
                  </div>
                </button>
              ))}
              {!searchResults.length ? (
                <div className="rounded-xl border border-line/70 p-3 text-xs text-slate-500">
                  No lexical match. The live API adds MiniLM semantic search across aliases and landmarks.
                </div>
              ) : null}
            </div>
            <div
              className="mt-4 overflow-hidden rounded-xl border border-line"
              style={{ background: `linear-gradient(145deg, hsl(${place.tone} 68% 24%) 0%, #08111f 72%)` }}
            >
              <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
                <span className="mono text-[9px] uppercase tracking-[0.18em] text-white/70">last-50m landmark</span>
                <span className="mono text-[9px] text-white/50">illustrative</span>
              </div>
              <div className="flex items-end gap-3 px-3 pb-3 pt-2">
                <svg viewBox="0 0 120 70" className="h-14 w-20 shrink-0" aria-hidden="true">
                  <rect x="10" y="18" width="100" height="46" rx="3" fill="#0b1422" opacity="0.55" />
                  <rect x="42" y="32" width="30" height="32" rx="2" fill="hsl(0 0% 100% / 0.18)" />
                  <rect x="66" y="44" width="2" height="2" fill="#e7eefb" />
                  <path d="M20 18h80" stroke="hsl(0 0% 100% / 0.3)" strokeWidth="2" />
                  <circle cx="28" cy="58" r="4" fill="hsl(0 0% 100% / 0.15)" />
                  <path d="M92 58h14" stroke="hsl(0 0% 100% / 0.3)" strokeWidth="2" />
                </svg>
                <div>
                  <div className="text-sm font-semibold text-white">{place.name}</div>
                  <div className="mt-0.5 text-[10px] text-white/70">{place.floor} · {place.open_hours}</div>
                  <div className="mt-1 text-[10px] leading-relaxed text-white/60">{place.landmark}</div>
                </div>
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-medium text-white">Route plan</div>
              <div className="flex rounded-lg border border-line bg-[#070d18] p-0.5">
                {(["fastest", "safest"] as const).map((item) => (
                  <button
                    key={item}
                    onClick={() => setMode(item)}
                    className={`rounded-md px-2.5 py-1 text-[10px] uppercase tracking-wider transition ${
                      mode === item ? "bg-mint/15 text-mint" : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-3">
              <label className="mono text-[9px] uppercase tracking-[0.18em] text-slate-500">starting from</label>
              <select
                value={origin}
                onChange={(event) => {
                  setOrigin(event.target.value);
                  setCartRequested(false);
                }}
                className="mt-1 w-full rounded-lg border border-line bg-[#070d18] px-2.5 py-2 text-xs text-white outline-none focus:border-mint/60"
              >
                {originOptions.map((id) => (
                  <option key={id} value={id}>{nodeLabels[id] ?? id}</option>
                ))}
              </select>
            </div>
            {route ? (
              <>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div className="rounded-lg border border-line/70 bg-[#070d18] p-2.5">
                    <div className="text-[9px] uppercase tracking-wider text-slate-500">walk time</div>
                    <div className="mono text-lg text-white">{route.eta_min.toFixed(0)} min</div>
                  </div>
                  <div className="rounded-lg border border-line/70 bg-[#070d18] p-2.5">
                    <div className="text-[9px] uppercase tracking-wider text-slate-500">distance</div>
                    <div className="mono text-lg text-white">{route.distance_m.toFixed(0)} m</div>
                  </div>
                  <div className="rounded-lg border border-line/70 bg-[#070d18] p-2.5">
                    <div className="text-[9px] uppercase tracking-wider text-slate-500">risk index</div>
                    <div className="mono text-lg text-amber">{route.risk_index.toFixed(0)}/100</div>
                  </div>
                  <div className="rounded-lg border border-line/70 bg-[#070d18] p-2.5">
                    <div className="text-[9px] uppercase tracking-wider text-slate-500">vs fastest</div>
                    <div className="mono text-lg text-mint">
                      {mode === "fastest"
                        ? "—"
                        : route.risk_reduction_pct > 0
                          ? `-${route.risk_reduction_pct.toFixed(0)}%`
                          : "already safest"}
                    </div>
                  </div>
                </div>
                {mode === "safest" && route.risk_reduction_pct === 0 ? (
                  <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                    This destination is reached by a lit, CCTV-covered path, so the safest route is the fastest one.
                    Try the Central Library preset to see the night model divert around a high-risk edge.
                  </p>
                ) : null}
                <div className="mt-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="mono text-[9px] uppercase tracking-[0.18em] text-slate-500">turn list</span>
                    <Badge tone="mint">night model</Badge>
                  </div>
                  <ol className="space-y-2">
                    {route.steps.map((step, index) => (
                      <li key={`${step.to_node}-${index}`} className="flex gap-2.5 text-[11px] text-slate-400">
                        <span className="mono grid h-5 w-5 shrink-0 place-items-center rounded-full border border-line text-[9px] text-slate-400">
                          {index + 1}
                        </span>
                        <span>
                          {step.instruction}
                          <span className="mono ml-1 text-slate-600">{step.distance_m.toFixed(0)}m</span>
                        </span>
                      </li>
                    ))}
                    <li className="flex gap-2.5 text-[11px] text-mint">
                      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-mint/40 text-[10px]">✓</span>
                      <span>Arrive at {place.name}. {place.landmark}.</span>
                    </li>
                  </ol>
                </div>
              </>
            ) : (
              <div className="mt-4 rounded-lg border border-line/70 p-3 text-xs text-slate-500">
                No route for this selection yet. Pick another place or origin.
              </div>
            )}
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-white">Golf cart dispatch</div>
              <Badge tone="sky">live fleet</Badge>
            </div>
            {dispatch ? (
              <>
                <div className="mt-4 rounded-xl border border-sky/20 bg-sky/[0.06] p-4">
                  <div className="flex items-baseline justify-between">
                    <div>
                      <div className="mono text-[9px] uppercase tracking-[0.18em] text-sky/70">nearest cart</div>
                      <div className="mt-1 text-xl font-semibold text-white">{dispatch.cart_label}</div>
                    </div>
                    <div className="text-right">
                      <div className="mono text-2xl text-sky">{dispatch.eta_min.toFixed(1)}</div>
                      <div className="text-[9px] uppercase tracking-wider text-slate-500">min ETA</div>
                    </div>
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{dispatch.reason}</p>
                  <button
                    onClick={() => setCartRequested(true)}
                    className="mt-3 w-full rounded-lg bg-sky px-3 py-2 text-xs font-semibold text-[#04121f] transition hover:bg-sky/90"
                  >
                    {cartRequested ? "Cart assigned" : "Request this cart"}
                  </button>
                  {cartRequested ? (
                    <div className="mt-2 rounded-lg border border-mint/25 bg-mint/[0.07] p-2 text-[10px] text-mint">
                      {dispatch.cart_label} assigned to {nodeLabels[dispatch.pickup_node] ?? dispatch.pickup_node}.
                      Driver notified. Estimated pickup {dispatch.eta_min.toFixed(1)} min.
                    </div>
                  ) : null}
                </div>
                <div className="mt-4">
                  <div className="mono mb-2 text-[9px] uppercase tracking-[0.18em] text-slate-500">fleet status</div>
                  <div className="space-y-1.5">
                    {snapshot.carts.map((cart) => (
                      <div key={cart.id} className="flex items-center justify-between gap-2 rounded-lg border border-line/60 px-2.5 py-1.5">
                        <div className="flex items-center gap-2">
                          <span className={`h-1.5 w-1.5 rounded-full ${cart.status === "available" ? "bg-mint" : cart.status === "charging" ? "bg-sky" : "bg-amber"}`} />
                          <span className="mono text-[10px] text-slate-300">{cart.label}</span>
                        </div>
                        <span className="truncate text-[10px] text-slate-500">{nodeLabels[cart.node_id]}</span>
                        <span className="mono text-[9px] uppercase tracking-wider text-slate-500">{cart.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <p className="mt-3 text-[10px] leading-relaxed text-slate-600">
                  Dispatch is a nearest-available assignment with ETA prediction. Fleet positions are simulated in this replay;
                  the adapter accepts driver-app pings or BLE beacons.
                </p>
              </>
            ) : (
              <div className="mt-4 text-xs text-slate-500">No dispatch data for this origin.</div>
            )}
          </Card>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-10 md:px-8">
        <SectionHeading
          id="predict"
          eyebrow="Pillar 01 · crowd and queue forecasting"
          title="See the next hour before it happens"
          description="LightGBM quantile models give the P10-P90 band, XGBoost sharpens the median, and the 70/30 blend is validated on a chronological split. Spatial neighbour occupancy is a first-class feature."
        />
        <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">{forecast.label}</div>
                <div className="mono text-[10px] text-slate-500">capacity {forecast.capacity} · horizons 15 / 30 / 60 min</div>
              </div>
              <select
                value={forecastNode}
                onChange={(event) => setForecastNode(event.target.value)}
                className="rounded-lg border border-line bg-[#070d18] px-2.5 py-1.5 text-xs text-white outline-none focus:border-mint/60"
              >
                {Object.entries(snapshot.forecasts).map(([id, bundle]) => (
                  <option key={id} value={id}>{bundle.label}</option>
                ))}
              </select>
            </div>
            <div className="mt-4">
              <ForecastChart bundle={forecast} />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
              <Badge tone="mint">quantile 0.1 / 0.5 / 0.9</Badge>
              <span>{forecast.model}</span>
            </div>
          </Card>
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm font-medium text-white">Pressure ranking</div>
              <Badge tone="amber">30-min forecast</Badge>
            </div>
            <div className="space-y-3">
              {snapshot.hotspots.slice(0, 7).map((hotspot) => (
                <button
                  key={hotspot.node_id}
                  onClick={() => setForecastNode(hotspot.node_id in snapshot.forecasts ? hotspot.node_id : "library")}
                  className="w-full text-left"
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="truncate text-xs text-slate-300">{hotspot.label}</span>
                    <span className="mono text-[10px] text-slate-500">
                      {Math.round(hotspot.occupancy_ratio * 100)}% → {Math.round(hotspot.predicted_ratio * 100)}%
                    </span>
                  </div>
                  <Meter value={hotspot.pressure * 100} tone={hotspot.pressure > 0.8 ? "bg-rose" : hotspot.pressure > 0.6 ? "bg-amber" : "bg-mint"} />
                  <div className="mt-1 flex justify-between text-[9px] text-slate-600">
                    <span>queue {hotspot.queue_len}</span>
                    <span>{hotspot.wait_min.toFixed(0)} min wait</span>
                  </div>
                </button>
              ))}
            </div>
            <div className="mt-4 border-t border-line/70 pt-3 text-[10px] leading-relaxed text-slate-500">
              Pressure = 55% predicted + 45% observed occupancy. Sensor nodes only; the graph is shared with routing.
            </div>
          </Card>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-10 md:px-8">
        <SectionHeading
          id="triage"
          eyebrow="Pillar 02 · closed-loop incident triage"
          title="Twenty-three reports. One incident. One playbook."
          description="The refiner gates pairs by building distance, time window, category and embedding cosine. XGBoost predicts priority, LightGBM predicts SLA, and the synthesizer cites retrieved incidents instead of inventing facts."
        />
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Stat label="Reports last 24h" value={snapshot.triage.stats.reports_last_24h} sub="raw student submissions" />
          <Stat label="Canonical incidents" value={snapshot.triage.stats.clusters_last_24h} sub={`collapse ratio ${fmt(snapshot.triage.stats.cluster_ratio, 2)}`} tone="text-sky" />
          <Stat label="P0 / P1 open" value={snapshot.triage.stats.p0_p1} sub="priority from XGBoost classifier" tone="text-amber" />
        </div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <PriorityFilter value={priorityFilter} onChange={setPriorityFilter} />
          <span className="mono text-[10px] uppercase tracking-wider text-slate-600">
            {snapshot.triage.queue[0]?.embedding_backend ?? "hashing"} embeddings · dedupe + retrieval
          </span>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {queue.map((cluster) => (
            <Card key={cluster.cluster_id} className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <PriorityBadge priority={cluster.priority} />
                  <Badge tone="slate">{cluster.category}</Badge>
                  <span className="mono text-[10px] text-slate-500">{hhmm(cluster.reported_at)}</span>
                </div>
                <span className="mono text-[10px] text-slate-500">
                  {cluster.merged_reports} report{cluster.merged_reports === 1 ? "" : "s"} → 1
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <div className="text-sm font-medium text-white">{cluster.node_label}</div>
                <div className="mono text-[10px] text-slate-500">
                  SLA {cluster.sla_minutes} min · conf {cluster.priority_confidence.toFixed(2)}
                </div>
              </div>
              <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-slate-400">{cluster.summary}</p>
              <details className="mt-2">
                <summary className="mono cursor-pointer text-[10px] uppercase tracking-wider text-mint/80">
                  brief, playbook and evidence
                </summary>
                <div className="mt-2 space-y-2 rounded-lg border border-line/70 bg-[#070d18] p-2.5">
                  <p className="text-[11px] leading-relaxed text-slate-300">{cluster.summary}</p>
                  <p className="text-[11px] leading-relaxed text-slate-400">
                    <span className="text-slate-500">Playbook: </span>{cluster.playbook}
                  </p>
                  {(cluster.evidence_snippets ?? []).length ? (
                    <div className="space-y-1 border-t border-line/60 pt-2">
                      {cluster.evidence_snippets.slice(0, 3).map((snippet, index) => (
                        <p key={index} className="text-[10px] leading-relaxed text-slate-400">
                          <span className="mono text-slate-600">[{index + 1}]</span> “{snippet}”
                        </p>
                      ))}
                    </div>
                  ) : null}
                  <div className="mono text-[9px] text-slate-600">
                    evidence ids: {cluster.evidence_ids.slice(0, 4).join(", ") || "current report only"}
                  </div>
                </div>
              </details>
              <div className="mt-3">
                <Meter value={cluster.priority_confidence * 100} label="classifier confidence" tone="bg-sky" />
              </div>
            </Card>
          ))}
          {!queue.length ? (
            <Card className="p-5 text-xs text-slate-500">No incidents match this filter.</Card>
          ) : null}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-10 md:px-8">
        <SectionHeading
          id="mess"
          eyebrow="Pillar 03 · mess demand and waste"
          title="Prep for the 90th percentile, not a guess"
          description="LightGBM forecasts headcount from calendar, weather, menu score and lagged meal uptake. P90 prep covers demand spikes while the mass-balance model projects waste against the current 12% over-prep policy."
        />
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Stat label="Next services" value={snapshot.mess.length} sub="both messes, upcoming meals" />
          <Stat label="Projected waste avoided" value={`${fmt(messTotals.saved, 0)} kg`} sub="vs baseline over-prep" tone="text-mint" />
          <Stat label="Mean confidence" value={`${fmt(messTotals.confidence * 100, 0)}%`} sub={`${messTotals.head.toLocaleString()} meals planned`} tone="text-sky" />
        </div>
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-xs">
              <thead className="border-b border-line/70 text-[9px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-3">service</th>
                  <th className="px-3 py-3">mess</th>
                  <th className="px-3 py-3 text-right">headcount</th>
                  <th className="px-3 py-3 text-right">P90</th>
                  <th className="px-3 py-3 text-right">prep</th>
                  <th className="px-3 py-3 text-right">exp. waste</th>
                  <th className="px-3 py-3 text-right">baseline</th>
                  <th className="px-3 py-3 text-right">saved</th>
                  <th className="px-4 py-3 text-right">confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {snapshot.mess.map((plan, index) => (
                  <tr key={`${plan.date}-${plan.meal}-${plan.mess_id}-${index}`} className="text-slate-300">
                    <td className="px-4 py-2.5">
                      <div className="capitalize text-white">{plan.meal}</div>
                      <div className="mono text-[9px] text-slate-500">{plan.date}</div>
                    </td>
                    <td className="px-3 py-2.5 text-slate-400">{plan.mess_label}</td>
                    <td className="mono px-3 py-2.5 text-right">{plan.predicted_headcount.toLocaleString()}</td>
                    <td className="mono px-3 py-2.5 text-right text-slate-500">{plan.p90_headcount.toLocaleString()}</td>
                    <td className="mono px-3 py-2.5 text-right">{plan.prep_kg.toFixed(0)} kg</td>
                    <td className="mono px-3 py-2.5 text-right text-amber">{plan.expected_waste_kg.toFixed(1)} kg</td>
                    <td className="mono px-3 py-2.5 text-right text-slate-500">{plan.baseline_waste_kg.toFixed(1)} kg</td>
                    <td className={`mono px-3 py-2.5 text-right ${plan.waste_saved_kg >= 0 ? "text-mint" : "text-rose"}`}>
                      {plan.waste_saved_kg >= 0 ? "+" : ""}{plan.waste_saved_kg.toFixed(1)} kg
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-end gap-2">
                        <div className="h-1 w-12 overflow-hidden rounded-full bg-slate-800">
                          <div className="h-full bg-mint" style={{ width: `${plan.confidence * 100}%` }} />
                        </div>
                        <span className="mono text-[9px] text-slate-500">{Math.round(plan.confidence * 100)}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <p className="mt-2 text-[10px] text-slate-600">
          Waste projection is a mass-balance model over predicted headcount and P90 prep; the separate waste regressor is benchmarked in the evaluation harness.
        </p>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-10 md:px-8">
        <SectionHeading
          id="benchmarks"
          eyebrow="Audit trail · reproducibility"
          title="Every claim has a baseline"
          description="Temporal splits, group-aware incident splits, ablations and latency are written to results/benchmark_metrics.json by python -m src.evaluate. The dataset is a seeded, documented digital twin; real telemetry adapters are the deployment swap."
        />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Forecast MAE" value={fmt(bench?.forecast?.model?.mae_occupancy_ratio, 4)} sub={`R² ${fmt(bench?.forecast?.model?.r2_occupancy_ratio, 4)}`} tone="text-mint" />
          <Stat label="Triage macro-F1" value={fmt(bench?.triage?.model?.macro_f1, 4)} sub={`accuracy ${fmt(bench?.triage?.model?.accuracy, 4)}`} tone="text-sky" />
          <Stat label="Dedupe pair-F1" value={fmt(bench?.dedupe?.semantic_gate?.pair_f1, 4)} sub={`${bench?.dedupe?.merged_reports ?? "—"} reports merged`} tone="text-violet-300" />
          <Stat label="Night risk cut" value={`${fmt(bench?.routing?.mean_risk_reduction_pct, 1)}%`} sub={`cart ETA -${fmt(bench?.routing?.dispatch?.eta_reduction_pct, 1)}%`} tone="text-amber" />
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <BenchTable title="Crowd forecast · MAE / R²" rows={benchRows.forecast} />
          <BenchTable title="Triage · macro-F1 / accuracy" rows={benchRows.triage} />
          <BenchTable title="Mess · head MAE / MAPE %" rows={benchRows.mess} />
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <Card className="p-5">
            <div className="mb-3 text-sm font-medium text-white">Ablations and latency</div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-line/70 p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Remove spatial features</div>
                <div className="mono mt-1 text-lg text-amber">+{fmt(bench?.ablations?.delta_pct?.spatial, 1)}% MAE</div>
              </div>
              <div className="rounded-xl border border-line/70 p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Remove temporal features</div>
                <div className="mono mt-1 text-lg text-amber">+{fmt(bench?.ablations?.delta_pct?.temporal, 1)}% MAE</div>
              </div>
              <div className="rounded-xl border border-line/70 p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Skip the refiner</div>
                <div className="mono mt-1 text-lg text-rose">+{fmt(bench?.ablations?.delta_pct?.refiner, 1)}% MAE</div>
              </div>
              <div className="rounded-xl border border-line/70 p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Route latency p95</div>
                <div className="mono mt-1 text-lg text-mint">{fmt(bench?.routing?.route_latency_ms_p95, 2)} ms</div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-[11px] sm:grid-cols-4">
              <div><div className="text-slate-500">forecast p95</div><div className="mono text-white">{fmt(bench?.latency?.forecast?.p95_ms, 1)} ms</div></div>
              <div><div className="text-slate-500">search p95</div><div className="mono text-white">{fmt(bench?.latency?.search?.p95_ms, 1)} ms</div></div>
              <div><div className="text-slate-500">triage p95</div><div className="mono text-white">{fmt(bench?.latency?.triage?.p95_ms, 1)} ms</div></div>
              <div><div className="text-slate-500">route p95</div><div className="mono text-white">{fmt(bench?.latency?.route?.p95_ms, 1)} ms</div></div>
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
              The refiner ablation is the most important number: training on unrepaired spikes and duplicate reports degrades the forecast materially,
              which is why every pillar consumes the same cleaned stream.
            </p>
          </Card>
          <Card className="p-5">
            <div className="mb-3 text-sm font-medium text-white">Reproducibility receipt</div>
            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between gap-3"><span className="text-slate-500">seed</span><span className="mono text-white">{bench?.seed ?? 42}</span></div>
              <div className="flex justify-between gap-3"><span className="text-slate-500">dataset sha256</span><span className="mono text-white">{bench?.dataset_sha256_16 ?? "—"}</span></div>
              <div className="flex justify-between gap-3"><span className="text-slate-500">embedder</span><span className="mono text-white">{bench?.environment?.embedder_backend ?? "hashing"}</span></div>
              <div className="flex justify-between gap-3"><span className="text-slate-500">lightgbm</span><span className="mono text-white">{bench?.environment?.lightgbm ?? "—"}</span></div>
              <div className="flex justify-between gap-3"><span className="text-slate-500">xgboost</span><span className="mono text-white">{bench?.environment?.xgboost ?? "—"}</span></div>
              <div className="flex justify-between gap-3"><span className="text-slate-500">eval wall clock</span><span className="mono text-white">{fmt(bench?.wall_clock_s, 1)} s</span></div>
            </div>
            <div className="mt-4 rounded-xl border border-line/70 bg-[#070d18] p-3">
              <div className="mono text-[9px] uppercase tracking-[0.18em] text-slate-500">regenerate everything</div>
              <pre className="mono mt-2 overflow-x-auto text-[10px] leading-relaxed text-mint">{`pip install -r requirements.txt
python -m src.train
python -m src.evaluate
python -m src.export_snapshot
pytest -q`}</pre>
            </div>
          </Card>
        </div>
      </section>

      <footer className="border-t border-line/60 px-4 py-8 md:px-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 text-[10px] text-slate-600 sm:flex-row sm:items-center sm:justify-between">
          <span className="mono uppercase tracking-[0.18em]">CampusPulse · one graph, five decisions</span>
          <span>FastAPI · LightGBM · XGBoost · MiniLM interface · Next.js · replay 06 Feb 2026, 20:30</span>
        </div>
      </footer>
    </div>
  );
}
