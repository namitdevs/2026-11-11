"use client";

import { useMemo, useState } from "react";

import CampusPhotoMap from "@/components/CampusPhotoMap";
import type { Department, Place, ServiceStatus, Snapshot, Verification } from "@/lib/types";

type Tab = "find" | "explore" | "navigate";

const CATEGORY_ORDER = ["academic", "residential", "food", "service", "sports", "transit", "landmark"] as const;

const CATEGORY_LABEL: Record<string, string> = {
  academic: "Academic & study",
  residential: "Hostels",
  food: "Food & mess",
  service: "Campus facilities",
  sports: "Sports",
  transit: "Gates & transport",
  landmark: "Landmarks",
};

const CATEGORY_BLURB: Record<string, string> = {
  academic: "Blocks, lecture halls, library, dean office",
  residential: "Prithvi, Vyom and Vahni Hall",
  food: "Canteen, Aahar, Streat Cafe, Food Court",
  service: "Admin, ATM, stationery, TAN Block, staff quarters",
  sports: "Sports Complex and grounds",
  transit: "Main Entrance, North Gate, golf cart stops",
  landmark: "Open Air Theatre (OAT)",
};

const VERIFICATION_LABEL: Record<Verification, string> = {
  map: "Campus map",
  official: "Official source",
  "third-party": "Third-party",
  unverified: "Unverified",
  demo: "Simulated",
};

const VERIFICATION_STYLE: Record<Verification, string> = {
  map: "border-emerald-200 bg-emerald-50 text-emerald-800",
  official: "border-sky-200 bg-sky-50 text-sky-800",
  "third-party": "border-amber-200 bg-amber-50 text-amber-800",
  unverified: "border-slate-200 bg-slate-100 text-slate-600",
  demo: "border-violet-200 bg-violet-50 text-violet-800",
};

const SERVICE_STYLE: Record<string, string> = {
  connected: "border-emerald-200 bg-emerald-50 text-emerald-800",
  partial: "border-sky-200 bg-sky-50 text-sky-800",
  demo: "border-amber-200 bg-amber-50 text-amber-800",
  not_connected: "border-slate-200 bg-slate-100 text-slate-600",
};

const SERVICE_LABEL: Record<string, string> = {
  connected: "Connected",
  partial: "Partial",
  demo: "Simulated",
  not_connected: "Not connected",
};

const ORIGIN_LABEL: Record<string, string> = {
  gate_main: "Main Entrance",
  gate_north: "North Gate",
  hostel_g1: "Vahni Hall",
};

function scorePlace(place: Place, query: string): number {
  const name = place.name.toLowerCase();
  const aliases = place.aliases.map((alias) => alias.toLowerCase());
  if (["hostel", "hostels", "residence", "residential"].includes(query)) {
    return place.category === "residential" ? 90 : 0;
  }
  if (name === query || aliases.includes(query)) return 100;
  if ([name, ...aliases].some((candidate) => candidate.startsWith(query))) return 85;
  if ([name, ...aliases].some((candidate) => candidate.length >= 5 && query.includes(candidate))) return 75;
  const document = `${name} ${aliases.join(" ")} ${place.category} ${place.description.toLowerCase()} ${place.landmark.toLowerCase()}`;
  if (document.includes(query)) return 68;
  const tokens = query.split(/\s+/).filter((token) => token.length > 2);
  if (!tokens.length) return 0;
  const overlap = tokens.filter((token) => document.includes(token)).length / tokens.length;
  return overlap * 45;
}

function badge(verification: Verification) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${VERIFICATION_STYLE[verification]}`}
    >
      {VERIFICATION_LABEL[verification]}
    </span>
  );
}

function SourceLine({ source }: { source: string }) {
  if (!source) return <span className="text-slate-400">No public source connected</span>;
  if (source.startsWith("http")) {
    return (
      <a href={source} target="_blank" rel="noreferrer" className="underline decoration-slate-300 underline-offset-2 hover:text-slate-900">
        {source.replace(/^https?:\/\//, "")}
      </a>
    );
  }
  return <span>{source}</span>;
}

export default function CampusApp({ snapshot }: { snapshot: Snapshot }) {
  const [tab, setTab] = useState<Tab>("find");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string>("central-library");
  const [origin, setOrigin] = useState<string>("gate_main");
  const [mode, setMode] = useState<"safest" | "fastest">("safest");

  const places = snapshot.places;
  const selected = places.find((place) => place.id === selectedId) ?? places[0];
  const trimmed = query.trim().toLowerCase();

  const results = useMemo(() => {
    if (!trimmed) return [];
    return places
      .map((place) => ({ place, score: scorePlace(place, trimmed) }))
      .filter((hit) => hit.score >= 20)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
  }, [places, trimmed]);

  const popular = useMemo(() => places.filter((place) => place.popular), [places]);
  const grouped = useMemo(
    () =>
      CATEGORY_ORDER.map((category) => ({
        category,
        items: places.filter((place) => place.category === category),
      })).filter((group) => group.items.length > 0),
    [places],
  );

  const directoryHits: Department[] = useMemo(() => {
    if (trimmed.length < 3) return [];
    const stop = new Set(["professor", "faculty", "teacher", "department", "engineering", "science", "cabin"]);
    const tokens = trimmed.split(/\s+/).filter((token) => token.length > 3 && !stop.has(token));
    if (!tokens.length) return snapshot.departments.slice(0, 4);
    return snapshot.departments
      .filter((department) => {
        const document = `${department.name} ${department.school}`.toLowerCase();
        return tokens.some((token) => document.includes(token));
      })
      .slice(0, 4);
  }, [snapshot.departments, trimmed]);

  const serviceHits: ServiceStatus[] = useMemo(() => {
    if (trimmed.length < 3) return [];
    const tokens = trimmed.split(/\s+/).filter((token) => token.length > 3);
    return snapshot.services
      .filter((service) => {
        const document = `${service.name} ${service.capability} ${service.detail}`.toLowerCase();
        return tokens.some((token) => document.includes(token));
      })
      .slice(0, 4);
  }, [snapshot.services, trimmed]);

  const routeBundle = snapshot.routes[origin]?.[selected.id];
  const availableOrigins = Object.keys(snapshot.routes);
  const destinationPlace = places.find((place) => place.node_id === selected.node_id) ?? selected;

  function go(placeId: string) {
    setSelectedId(placeId);
    setTab("navigate");
  }

  function pickSearchResult(placeId: string) {
    setSelectedId(placeId);
    setQuery("");
  }

  return (
    <div className="min-h-screen bg-[#f5f7fb] text-slate-900 [color-scheme:light]">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-slate-900 text-sm font-semibold text-white">
              CP
            </span>
            <div>
              <div className="text-sm font-semibold tracking-tight">CampusPulse</div>
              <div className="text-xs text-slate-500">TIET Patiala campus wayfinding</div>
            </div>
          </div>
          <nav className="flex items-center gap-1 text-sm">
            {(["find", "explore", "navigate"] as Tab[]).map((item) => (
              <button
                key={item}
                onClick={() => setTab(item)}
                className={`rounded-full px-3 py-1.5 capitalize transition ${
                  tab === item ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {item}
              </button>
            ))}
            <a
              href="/ops"
              className="ml-2 rounded-full border border-slate-200 px-3 py-1.5 text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
            >
              Ops view
            </a>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-16">
        {tab === "find" ? (
          <>
            <section className="py-10 sm:py-14">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
                Verified campus map, not a guess
              </p>
              <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
                Find any place on campus. Know how to get there.
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-600">
                Search the names students actually use, see where the place sits on the TIET map, and follow a
                walking route with a last-50-metre landmark cue.
              </p>

              <div className="mt-7 max-w-2xl">
                <div className="flex items-center gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-slate-900">
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && results[0]) pickSearchResult(results[0].place.id);
                    }}
                    placeholder="Try cold coffee, Vahni, print, or OAT"
                    aria-label="Search campus places"
                    className="w-full bg-transparent px-3 py-2 text-base outline-none placeholder:text-slate-400"
                  />
                  <button
                    onClick={() => results[0] && pickSearchResult(results[0].place.id)}
                    className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
                  >
                    Search
                  </button>
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  Every result names its source. Names and landmarks come from the shared TIET campus map.
                </p>
                {trimmed ? (
                  <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    {results.length ? (
                      <ul className="divide-y divide-slate-100">
                        {results.map(({ place, score }) => (
                          <li key={place.id}>
                            <button
                              onClick={() => pickSearchResult(place.id)}
                              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-slate-50"
                            >
                              <span>
                                <span className="flex flex-wrap items-center gap-2">
                                  <span className="font-medium">{place.name}</span>
                                  {badge(place.verification)}
                                </span>
                                <span className="mt-0.5 block text-xs text-slate-500">
                                  {CATEGORY_LABEL[place.category] ?? place.category} · {place.landmark}
                                </span>
                              </span>
                              <span className="mono text-xs text-slate-400">{Math.round(score)}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="px-4 py-4 text-sm text-slate-500">
                        No verified campus label matched. Try a name printed on the map, or a common alias such as
                        canteen, OAT or Vahni.
                      </p>
                    )}
                    {directoryHits.length ? (
                      <div className="border-t border-slate-100 bg-slate-50 px-4 py-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                          Departments published by TIET
                        </div>
                        <ul className="mt-1 space-y-1 text-sm text-slate-700">
                          {directoryHits.map((department) => (
                            <li key={department.name}>{department.name}</li>
                          ))}
                        </ul>
                        <p className="mt-1 text-xs text-slate-500">
                          Individual faculty cabins are not published, so no professor-to-office mapping is shown.
                        </p>
                      </div>
                    ) : null}
                    {serviceHits.length ? (
                      <div className="border-t border-slate-100 px-4 py-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                          Capability status
                        </div>
                        <ul className="mt-1 space-y-2">
                          {serviceHits.map((service) => (
                            <li key={service.id} className="text-sm">
                              <span className={`mr-2 inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${SERVICE_STYLE[service.status]}`}>
                                {SERVICE_LABEL[service.status]}
                              </span>
                              <span className="font-medium">{service.name}</span>
                              <div className="mt-0.5 text-xs text-slate-500">{service.detail}</div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              <article className="rounded-2xl border border-slate-200 bg-white p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold tracking-tight">{selected.name}</h2>
                  {badge(selected.verification)}
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {CATEGORY_LABEL[selected.category] ?? selected.category} · {selected.floor}
                </p>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">{selected.description}</p>
                <dl className="mt-4 space-y-2 text-sm">
                  <div>
                    <dt className="text-[11px] uppercase tracking-wider text-slate-400">Last 50 metres</dt>
                    <dd className="text-slate-700">{selected.landmark}</dd>
                  </div>
                  <div>
                    <dt className="text-[11px] uppercase tracking-wider text-slate-400">Source</dt>
                    <dd className="break-words text-slate-700">
                      <SourceLine source={selected.source} />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] uppercase tracking-wider text-slate-400">Open hours</dt>
                    <dd className="text-slate-700">{selected.open_hours}</dd>
                  </div>
                </dl>
                <button
                  onClick={() => go(selected.id)}
                  className="mt-5 w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
                >
                  Show walking route
                </button>
              </article>

              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h2 className="text-lg font-semibold tracking-tight">Popular with students</h2>
                <p className="mt-1 text-sm text-slate-500">Ground truth from the campus map, not engagement tracking.</p>
                <ul className="mt-4 grid gap-2 sm:grid-cols-2">
                  {popular.map((place) => (
                    <li key={place.id}>
                      <button
                        onClick={() => pickSearchResult(place.id)}
                        className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-left transition hover:border-slate-900"
                      >
                        <div className="text-sm font-medium">{place.name}</div>
                        <div className="mt-0.5 text-xs text-slate-500">{CATEGORY_LABEL[place.category]}</div>
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="mt-5 rounded-xl bg-slate-50 p-3 text-xs leading-relaxed text-slate-600">
                  Live seat counts, course-to-room schedules and shuttle GPS are not published by TIET. Where that data
                  is missing, this app says so instead of inventing a number.
                </div>
              </div>
            </section>
          </>
        ) : null}

        {tab === "explore" ? (
          <section className="py-10">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Explore the whole campus</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
              {places.length} locations grouped by what a fresher is looking for. Labels follow the shared TIET campus
              map, including the names printed at each building.
            </p>

            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {grouped.slice(0, 4).map((group) => (
                <div key={group.category} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                    {CATEGORY_LABEL[group.category]}
                  </div>
                  <div className="mt-2 text-3xl font-semibold tracking-tight">{group.items.length}</div>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">{CATEGORY_BLURB[group.category]}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 space-y-6">
              {grouped.map((group) => (
                <div key={group.category}>
                  <div className="flex items-baseline justify-between gap-3">
                    <h2 className="text-lg font-semibold tracking-tight">{CATEGORY_LABEL[group.category]}</h2>
                    <span className="text-xs text-slate-400">{group.items.length} places</span>
                  </div>
                  <ul className="mt-2 divide-y divide-slate-200 overflow-hidden rounded-2xl border border-slate-200 bg-white">
                    {group.items.map((place) => (
                      <li key={place.id}>
                        <button
                          onClick={() => pickSearchResult(place.id)}
                          className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition hover:bg-slate-50"
                        >
                          <span>
                            <span className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-medium">{place.name}</span>
                              {badge(place.verification)}
                            </span>
                            <span className="mt-0.5 block text-xs text-slate-500">{place.landmark}</span>
                          </span>
                          <span className="mt-0.5 text-xs text-slate-400">{place.floor}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <div className="mt-10">
              <h2 className="text-lg font-semibold tracking-tight">What this app can and cannot show</h2>
              <p className="mt-1 text-sm text-slate-500">
                Capabilities are labelled by how they are wired, so a demo is never mistaken for live data.
              </p>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {snapshot.services.map((service) => (
                  <div key={service.id} className="rounded-xl border border-slate-200 bg-white p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${SERVICE_STYLE[service.status]}`}>
                        {SERVICE_LABEL[service.status]}
                      </span>
                      <span className="text-sm font-medium">{service.name}</span>
                      <span className="text-[11px] uppercase tracking-wider text-slate-400">{service.capability}</span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-500">{service.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {tab === "navigate" ? (
          <section className="py-10">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Navigate to {selected.name}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
              Walking routes are computed on the campus graph with night risk weighting, then projected onto the TIET
              map. Distances are modelled, not surveyed.
            </p>

            <div className="mt-5 grid gap-4 lg:grid-cols-[320px_1fr]">
              <div className="space-y-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Destination
                  </label>
                  <select
                    value={selected.id}
                    onChange={(event) => setSelectedId(event.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900"
                  >
                    {places.map((place) => (
                      <option key={place.id} value={place.id}>
                        {place.name}
                      </option>
                    ))}
                  </select>

                  <label className="mt-4 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Start from
                  </label>
                  <select
                    value={origin}
                    onChange={(event) => setOrigin(event.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900"
                  >
                    {availableOrigins.map((nodeId) => (
                      <option key={nodeId} value={nodeId}>
                        {ORIGIN_LABEL[nodeId] ?? nodeId}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Only map-verified origins are offered. No GPS location is requested or invented.
                  </p>

                  <div className="mt-4 grid grid-cols-2 gap-2">
                    <button
                      onClick={() => setMode("safest")}
                      className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${
                        mode === "safest"
                          ? "border-emerald-600 bg-emerald-50 text-emerald-800"
                          : "border-slate-200 text-slate-600 hover:border-slate-400"
                      }`}
                    >
                      Lowest risk
                    </button>
                    <button
                      onClick={() => setMode("fastest")}
                      className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${
                        mode === "fastest"
                          ? "border-sky-600 bg-sky-50 text-sky-800"
                          : "border-slate-200 text-slate-600 hover:border-slate-400"
                      }`}
                    >
                      Shortest
                    </button>
                  </div>
                  <p className="mt-2 text-[11px] text-slate-400">
                    Routes are computed with night-mode risk weighting.
                  </p>
                </div>

                {routeBundle ? (
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-baseline justify-between">
                      <div className="text-sm font-semibold">Route summary</div>
                      <span className="text-xs text-slate-400">{mode === "safest" ? "lowest risk" : "shortest"}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                      <div className="rounded-xl bg-slate-50 p-2">
                        <div className="text-lg font-semibold">{routeBundle[mode].distance_m}</div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-400">metres</div>
                      </div>
                      <div className="rounded-xl bg-slate-50 p-2">
                        <div className="text-lg font-semibold">{Math.round(routeBundle[mode].eta_min)}</div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-400">minutes</div>
                      </div>
                      <div className="rounded-xl bg-slate-50 p-2">
                        <div className="text-lg font-semibold">{routeBundle[mode].risk_index}</div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-400">risk</div>
                      </div>
                    </div>

                    <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                      <div className="text-[11px] font-semibold uppercase tracking-wider">Last 50 metres</div>
                      <div className="mt-0.5">{destinationPlace.landmark}</div>
                    </div>

                    <ol className="mt-3 space-y-2">
                      {routeBundle[mode].steps.map((step, index) => (
                        <li key={`${step.from_node}-${step.to_node}-${index}`} className="flex gap-2 text-sm">
                          <span className="mono mt-0.5 w-5 text-[11px] text-slate-400">{index + 1}</span>
                          <span>
                            <span className="text-slate-800">{step.instruction}</span>
                            <span className="ml-1 text-xs text-slate-400">{Math.round(step.distance_m)} m</span>
                          </span>
                        </li>
                      ))}
                    </ol>

                    <div className="mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-relaxed text-slate-500">
                      Golf cart demo: nearest simulated cart ETA {snapshot.dispatches[origin]?.eta_min ?? "-"} min.
                      This is simulated, not a live vehicle feed.
                    </div>
                  </div>
                ) : (
                  <p className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
                    No route table is available for this origin in the offline snapshot.
                  </p>
                )}
              </div>

              <div className="space-y-3">
                <CampusPhotoMap
                  nodes={snapshot.graph.nodes}
                  places={places}
                  carts={snapshot.carts}
                  fastest={routeBundle?.fastest ?? null}
                  safest={routeBundle?.safest ?? null}
                  mode={mode}
                  origin={origin}
                  selectedNode={selected.node_id}
                  onPickNode={(_nodeId, placeId) => setSelectedId(placeId)}
                />
                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-emerald-400" /> lowest-risk route
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-sky-400" /> shortest route
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-amber-400" /> simulated cart
                  </span>
                  <span className="ml-auto">Click a pin to open that place.</span>
                </div>
              </div>
            </div>
          </section>
        ) : null}
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex rounded-full border px-2 py-0.5 font-medium ${SERVICE_STYLE.connected}`}>
              Place data: campus map
            </span>
            <span className={`inline-flex rounded-full border px-2 py-0.5 font-medium ${SERVICE_STYLE.demo}`}>
              Carts & crowd: simulated
            </span>
            <span className={`inline-flex rounded-full border px-2 py-0.5 font-medium ${SERVICE_STYLE.not_connected}`}>
              Live seats & GPS: not connected
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span>
              Snapshot {new Date(snapshot.generated_at).toLocaleDateString()} · {places.length} locations ·{" "}
              {snapshot.graph.nodes.length} graph nodes
            </span>
            <a href="/ops" className="font-medium text-slate-700 underline underline-offset-2">
              Model evidence
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
