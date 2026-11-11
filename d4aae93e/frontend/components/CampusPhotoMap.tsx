"use client";

import type { Cart, GraphNode, Place, RouteResult } from "@/lib/types";
import { CAMPUS_MAP_HEIGHT, CAMPUS_MAP_WIDTH, MAP_POSITIONS } from "@/lib/campusMap";

type Props = {
  nodes: GraphNode[];
  places: Place[];
  carts: Cart[];
  fastest: RouteResult | null;
  safest: RouteResult | null;
  mode: "fastest" | "safest";
  origin: string;
  selectedNode: string | null;
  onPickNode: (nodeId: string, placeId: string) => void;
};

const ACTIVE = {
  safest: "#35f0b0",
  fastest: "#59c2ff",
} as const;

export default function CampusPhotoMap({
  nodes,
  places,
  carts,
  fastest,
  safest,
  mode,
  origin,
  selectedNode,
  onPickNode,
}: Props) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const placeByNode = new Map<string, Place>();
  for (const place of places) {
    if (!placeByNode.has(place.node_id)) placeByNode.set(place.node_id, place);
  }
  const active = mode === "safest" ? safest : fastest;
  const inactive = mode === "safest" ? fastest : safest;
  const destination = active?.path[active.path.length - 1] ?? null;
  const destinationPlace = destination ? placeByNode.get(destination) : undefined;
  const originPlace = placeByNode.get(origin);
  const points = (route: RouteResult | null) =>
    (route?.path ?? [])
      .map((id) => MAP_POSITIONS[id])
      .filter((point): point is [number, number] => Boolean(point));

  return (
    <div className="relative overflow-hidden rounded-xl border border-line/70 bg-[#dfeaf5]">
      <svg
        viewBox={`0 0 ${CAMPUS_MAP_WIDTH} ${CAMPUS_MAP_HEIGHT}`}
        className="h-auto w-full"
        role="img"
        aria-label="TIET campus map with the selected walking route"
      >
        <defs>
          <filter id="routeGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="pinShadow" x="-60%" y="-60%" width="220%" height="220%">
            <feDropShadow dx="0" dy="2" stdDeviation="2.4" floodColor="#02101d" floodOpacity="0.55" />
          </filter>
        </defs>
        <image
          href="/campus-map.jpg"
          x="0"
          y="0"
          width={CAMPUS_MAP_WIDTH}
          height={CAMPUS_MAP_HEIGHT}
          preserveAspectRatio="xMidYMid meet"
        />

        {inactive && inactive.path.join("|") !== active?.path.join("|") ? (
          <polyline
            points={points(inactive).map(([x, y]) => `${x},${y}`).join(" ")}
            fill="none"
            stroke="#dbe7f3"
            strokeWidth="9"
            strokeOpacity="0.85"
            strokeDasharray="14 12"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : null}

        {active ? (
          <>
            <polyline
              points={points(active).map(([x, y]) => `${x},${y}`).join(" ")}
              fill="none"
              stroke="#02101d"
              strokeWidth="13"
              strokeOpacity="0.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <polyline
              className="route-flow"
              points={points(active).map(([x, y]) => `${x},${y}`).join(" ")}
              fill="none"
              stroke={ACTIVE[mode]}
              strokeWidth="7"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray="18 12"
              filter="url(#routeGlow)"
            />
          </>
        ) : null}

        {nodes.map((node) => {
          const point = MAP_POSITIONS[node.id];
          if (!point) return null;
          const place = placeByNode.get(node.id);
          const selected = node.id === selectedNode;
          const isOrigin = node.id === origin;
          const [x, y] = point;
          return (
            <g
              key={node.id}
              role={place ? "button" : undefined}
              tabIndex={place ? 0 : undefined}
              onClick={() => place && onPickNode(node.id, place.id)}
              onKeyDown={(event) => {
                if (place && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  onPickNode(node.id, place.id);
                }
              }}
              className={place ? "cursor-pointer" : undefined}
            >
              <title>{node.label}</title>
              <circle
                cx={x}
                cy={y}
                r={selected ? 10 : isOrigin ? 7 : 4.5}
                fill={selected ? ACTIVE[mode] : isOrigin ? "#f8fafc" : "#0b2035"}
                stroke={selected || isOrigin ? "#02101d" : "#dbe7f3"}
                strokeWidth={selected || isOrigin ? 3 : 1.5}
                opacity={selected || isOrigin ? 1 : 0.72}
              />
              {selected ? <circle cx={x} cy={y} r="17" fill="none" stroke={ACTIVE[mode]} strokeWidth="2" opacity="0.7" /> : null}
            </g>
          );
        })}

        {carts.map((cart) => {
          const point = MAP_POSITIONS[cart.node_id];
          if (!point) return null;
          const [x, y] = point;
          return (
            <g key={cart.id} filter="url(#pinShadow)">
              <circle cx={x - 14} cy={y - 14} r="8" fill="#59c2ff" stroke="#02101d" strokeWidth="2" />
              <text x={x - 14} y={y - 10.5} textAnchor="middle" fontSize="9" fontWeight="700" fill="#02101d">
                C
              </text>
              <title>{`${cart.label} · ${cart.status}`}</title>
            </g>
          );
        })}

        {origin && MAP_POSITIONS[origin] ? (
          <g filter="url(#pinShadow)">
            <circle cx={MAP_POSITIONS[origin][0]} cy={MAP_POSITIONS[origin][1]} r="12" fill="#f8fafc" stroke="#02101d" strokeWidth="3" />
            <text
              x={MAP_POSITIONS[origin][0]}
              y={MAP_POSITIONS[origin][1] + 4}
              textAnchor="middle"
              fontSize="11"
              fontWeight="800"
              fill="#02101d"
            >
              A
            </text>
            <text
              x={MAP_POSITIONS[origin][0] + 17}
              y={MAP_POSITIONS[origin][1] + 4}
              fontSize="11"
              fontWeight="700"
              fill="#f8fafc"
              stroke="#02101d"
              strokeWidth="3.5"
              paintOrder="stroke"
            >
              {originPlace?.name ?? nodeById.get(origin)?.label ?? "Start"}
            </text>
          </g>
        ) : null}

        {destination && MAP_POSITIONS[destination] ? (
          <g filter="url(#pinShadow)">
            <circle cx={MAP_POSITIONS[destination][0]} cy={MAP_POSITIONS[destination][1]} r="13" fill={ACTIVE[mode]} stroke="#02101d" strokeWidth="3" />
            <text
              x={MAP_POSITIONS[destination][0]}
              y={MAP_POSITIONS[destination][1] + 4.5}
              textAnchor="middle"
              fontSize="11"
              fontWeight="800"
              fill="#02101d"
            >
              B
            </text>
            <text
              x={MAP_POSITIONS[destination][0] + 18}
              y={MAP_POSITIONS[destination][1] + 4}
              fontSize="11"
              fontWeight="700"
              fill="#f8fafc"
              stroke="#02101d"
              strokeWidth="3.5"
              paintOrder="stroke"
            >
              {destinationPlace?.name ?? nodeById.get(destination)?.label ?? "Destination"}
            </text>
          </g>
        ) : null}
      </svg>

      <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-white/15 bg-[#04121f]/80 px-2.5 py-1.5 backdrop-blur">
        <div className="mono text-[9px] uppercase tracking-[0.18em] text-mint">TIET campus · image view</div>
        <div className="mt-0.5 text-[9px] text-slate-400">route geometry projected from the campus graph</div>
      </div>

      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-2 rounded-lg border border-white/15 bg-[#04121f]/80 px-2.5 py-1.5 text-[9px] text-slate-300 backdrop-blur">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 rounded bg-mint" /> {mode} route
        </span>
        {inactive && inactive.path.join("|") !== active?.path.join("|") ? (
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded border-t border-dashed border-slate-300" /> {mode === "safest" ? "fastest" : "safest"} alternative
          </span>
        ) : null}
        <span className="flex items-center gap-1.5">
          <span className="grid h-3.5 w-3.5 place-items-center rounded-full bg-sky text-[8px] font-bold text-[#04121f]">C</span> golf cart
        </span>
        <span className="text-slate-500">tap a dot to inspect</span>
      </div>
    </div>
  );
}
