"use client";

import type { Cart, GraphEdge, GraphNode, Place, RouteResult } from "@/lib/types";

const KIND_FILL: Record<string, string> = {
  academic: "#59c2ff",
  food: "#ffb545",
  residential: "#a78bfa",
  service: "#94a3b8",
  transit: "#35f0b0",
  safety: "#ff6b81",
  sports: "#bef264",
  landmark: "#fde68a",
};

type Props = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  route: RouteResult | null;
  carts: Cart[];
  places: Place[];
  selectedNode: string | null;
  onPickNode: (nodeId: string, placeId: string) => void;
};

export default function CampusMap({ nodes, edges, route, carts, places, selectedNode, onPickNode }: Props) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const routePoints = (route?.path ?? [])
    .map((id) => byId.get(id))
    .filter((node): node is GraphNode => Boolean(node))
    .map((node) => `${node.x},${node.y}`)
    .join(" ");
  const routeColor = route?.mode === "safest" ? "#35f0b0" : "#59c2ff";
  const cartCount = new Map<string, number>();

  return (
    <div>
      <div className="relative overflow-hidden rounded-xl border border-line/70 bg-[#070d18]">
        <svg viewBox="0 0 1000 640" className="h-auto w-full" role="img" aria-label="Campus graph map">
          <defs>
            <pattern id="dots" width="28" height="28" patternUnits="userSpaceOnUse">
              <circle cx="2" cy="2" r="1" fill="#1b2740" />
            </pattern>
            <linearGradient id="mapGlow" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0c1626" />
              <stop offset="100%" stopColor="#060a12" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect width="1000" height="640" fill="url(#mapGlow)" />
          <rect width="1000" height="640" fill="url(#dots)" opacity="0.8" />
          <text x="34" y="52" fill="#33415e" fontSize="13" fontFamily="monospace">TIET CAMPUS GRAPH / 20 NODES / 35 EDGES</text>
          <text x="930" y="52" fill="#59c2ff" fontSize="13" fontFamily="monospace">N</text>

          {edges.map((edge) => {
            const a = byId.get(edge.u);
            const b = byId.get(edge.v);
            if (!a || !b) return null;
            const onRoute = route ? route.path.includes(edge.u) && route.path.includes(edge.v) : false;
            const risky = edge.risk > 0.62 || !edge.lit;
            return (
              <line
                key={edge.id}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={onRoute ? routeColor : risky ? "#6b3a50" : edge.lit ? "#26364f" : "#3b3350"}
                strokeWidth={onRoute ? 3.5 : 2.4}
                strokeDasharray={edge.lit ? undefined : "5 5"}
                opacity={onRoute ? 0.95 : 0.8}
              />
            );
          })}

          {routePoints ? (
            <>
              <polyline
                points={routePoints}
                fill="none"
                stroke={routeColor}
                strokeWidth={13}
                strokeOpacity={0.14}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <polyline
                points={routePoints}
                fill="none"
                stroke={routeColor}
                strokeWidth={5}
                strokeLinecap="round"
                strokeLinejoin="round"
                filter="url(#glow)"
              />
            </>
          ) : null}

          {nodes.map((node) => {
            const fill = KIND_FILL[node.kind] ?? "#94a3b8";
            const isSelected = node.id === selectedNode;
            const isRoute = route?.path.includes(node.id);
            return (
              <g
                key={node.id}
                onClick={() => {
                  const place = places.find((item) => item.node_id === node.id);
                  if (place) onPickNode(node.id, place.id);
                }}
                className="cursor-pointer"
              >
                {isSelected ? (
                  <circle cx={node.x} cy={node.y} r={17} fill="none" stroke="#35f0b0" strokeWidth={2} opacity={0.75} className="animate-pulse" />
                ) : null}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isSelected ? 8 : isRoute ? 7 : 5.5}
                  fill={fill}
                  stroke="#060a12"
                  strokeWidth={2}
                  opacity={node.kind === "landmark" ? 0.85 : 1}
                />
                <text
                  x={node.x + 10}
                  y={node.y - 9}
                  fill={isSelected ? "#e7eefb" : "#7d8aa3"}
                  fontSize={isSelected ? 11.5 : 10}
                  fontFamily="ui-sans-serif, system-ui"
                  fontWeight={isSelected ? 600 : 400}
                >
                  {node.label}
                </text>
              </g>
            );
          })}

          {carts.map((cart) => {
            const node = byId.get(cart.node_id);
            if (!node) return null;
            const seen = cartCount.get(node.id) ?? 0;
            cartCount.set(node.id, seen + 1);
            const x = node.x + 12 + seen * 16;
            const y = node.y + 12 + seen * 13;
            return (
              <g key={cart.id}>
                <rect x={x} y={y} width={15} height={11} rx={2.5} fill={cart.status === "available" ? "#f8fafc" : cart.status === "charging" ? "#38bdf8" : "#f59e0b"} opacity={0.9} />
                <text x={x + 2} y={y + 8.5} fontSize={7} fill="#06121f" fontFamily="monospace" fontWeight={700}>
                  {cart.label.slice(-1)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] text-slate-500">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-mint" /> safe route</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-sky" /> fastest route</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber" /> food</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-rose" /> unlit / risky edge</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2 rounded-sm bg-white" /> golf cart</span>
        <span className="ml-auto mono">tap a node to route</span>
      </div>
    </div>
  );
}
