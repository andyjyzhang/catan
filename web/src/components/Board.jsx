import React, { useMemo } from "react";
import { computeLayout } from "../layout.js";
import { HEX_META, PLAYER_COLORS, RESOURCE_META } from "../format.js";

const NUMBER_DOTS = { 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1 };
const SIZE = 56; // matches layout scale

function hexPoints(cx, cy, size) {
  const pts = [];
  for (let k = 0; k < 6; k++) {
    const a = ((60 * k - 30) * Math.PI) / 180;
    pts.push(`${cx + size * Math.cos(a)},${cy + size * Math.sin(a)}`);
  }
  return pts.join(" ");
}

// A port spans the two coastal nodes that share a port marker. We place its
// badge on the water side (pushed outward from the board centroid) and draw a
// short dock line to each of the two nodes it serves.
function buildPorts(board, nodes) {
  const cx = Object.values(nodes).reduce((s, n) => s + n.x, 0) / Object.keys(nodes).length;
  const cy = Object.values(nodes).reduce((s, n) => s + n.y, 0) / Object.keys(nodes).length;
  const ports = [];
  const seen = new Set();
  for (const edge of Object.values(board.edges)) {
    const a = board.nodes[edge.node_a];
    const b = board.nodes[edge.node_b];
    if (!a?.port || !b?.port) continue;
    const key = [edge.node_a, edge.node_b].sort((x, y) => x - y).join("-");
    if (seen.has(key)) continue;
    seen.add(key);
    const pa = nodes[edge.node_a];
    const pb = nodes[edge.node_b];
    const mx = (pa.x + pb.x) / 2;
    const my = (pa.y + pb.y) / 2;
    let dx = mx - cx;
    let dy = my - cy;
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    const bx = mx + dx * 40;
    const by = my + dy * 40;
    ports.push({ key, port: a.port, bx, by, anchors: [pa, pb] });
  }
  return ports;
}

export default function Board({
  state,
  highlight = { nodes: new Set(), cities: new Set(), edges: new Set(), hexes: new Set() },
  onNode,
  onEdge,
  onHex,
}) {
  const board = state.board;
  const layout = useMemo(() => computeLayout(board), [board]);
  const ports = useMemo(() => buildPorts(board, layout.nodes), [board, layout]);

  const nodeOwner = {};
  const nodeKind = {};
  const edgeOwner = {};
  state.players.forEach((player, pid) => {
    player.settlements.forEach((n) => {
      nodeOwner[n] = pid;
      nodeKind[n] = "settlement";
    });
    player.cities.forEach((n) => {
      nodeOwner[n] = pid;
      nodeKind[n] = "city";
    });
    player.roads.forEach((e) => {
      edgeOwner[e] = pid;
    });
  });

  return (
    <svg
      className="board"
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <filter id="islandShadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="6" stdDeviation="9" floodColor="#04161b" floodOpacity="0.45" />
        </filter>
        <filter id="tokenShadow" x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="1" stdDeviation="1" floodColor="#000" floodOpacity="0.3" />
        </filter>
      </defs>

      {/* Ports: dock lines + water-side badges */}
      {ports.map((p) => (
        <g key={`port-${p.key}`} className="port-group" pointerEvents="none">
          {p.anchors.map((n, i) => (
            <line key={i} className="port-dock" x1={p.bx} y1={p.by} x2={n.x} y2={n.y} />
          ))}
          <g transform={`translate(${p.bx}, ${p.by})`}>
            <rect className="port-badge" x={-19} y={-13} width={38} height={26} rx={13} />
            <text className="port-ratio" x={0} y={p.port.kind === "generic" ? 1 : -3} textAnchor="middle">
              {p.port.kind === "generic" ? "3:1" : "2:1"}
            </text>
            {p.port.kind !== "generic" && (
              <text className="port-res" x={0} y={9} textAnchor="middle">
                {RESOURCE_META[p.port.resource]?.emoji ?? ""}
              </text>
            )}
          </g>
        </g>
      ))}

      {/* Island tiles */}
      <g filter="url(#islandShadow)">
        {layout.hexes.map((hex) => {
          const meta = HEX_META[hex.type] ?? HEX_META.DESERT;
          const clickable = highlight.hexes.has(hex.id);
          return (
            <polygon
              key={`hexfill-${hex.id}`}
              points={hexPoints(hex.x, hex.y, SIZE * 0.985)}
              fill={meta.color}
              stroke={clickable ? "#f4ecd8" : "#00000022"}
              strokeWidth={clickable ? 3.5 : 1}
              className={clickable ? "hex clickable" : "hex"}
              onClick={clickable ? () => onHex?.(hex.id) : undefined}
            />
          );
        })}
      </g>

      {/* Number tokens + robber (above tiles, no shadow group so text stays crisp) */}
      {layout.hexes.map((hex) => {
        const isRobber = board.robber_hex_id === hex.id;
        const hot = hex.number === 6 || hex.number === 8;
        return (
          <g key={`tok-${hex.id}`} pointerEvents="none">
            {hex.number != null && (
              <g filter="url(#tokenShadow)">
                <circle cx={hex.x} cy={hex.y} r={SIZE * 0.3} className="token-disc" />
                <text x={hex.x} y={hex.y - 3} textAnchor="middle" dominantBaseline="middle" className={hot ? "token hot" : "token"}>
                  {hex.number}
                </text>
                <text x={hex.x} y={hex.y + SIZE * 0.17} textAnchor="middle" dominantBaseline="middle" className={hot ? "token-dots hot" : "token-dots"}>
                  {"•".repeat(NUMBER_DOTS[hex.number] ?? 0)}
                </text>
              </g>
            )}
            {isRobber && (
              <g>
                <circle cx={hex.x} cy={hex.y} r={SIZE * 0.34} className="robber-ring" />
                <text x={hex.x} y={hex.y + 1} textAnchor="middle" dominantBaseline="middle" fontSize={SIZE * 0.42}>
                  🥷
                </text>
              </g>
            )}
          </g>
        );
      })}

      {/* Roads */}
      {layout.edges.map((edge) => {
        const owner = edgeOwner[edge.id];
        const clickable = highlight.edges.has(edge.id);
        if (owner == null && !clickable) return null;
        return (
          <g key={`edge-${edge.id}`}>
            {owner != null && (
              <line x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2} className="road-base" />
            )}
            <line
              x1={edge.x1}
              y1={edge.y1}
              x2={edge.x2}
              y2={edge.y2}
              stroke={owner != null ? PLAYER_COLORS[owner] : undefined}
              className={
                owner != null ? "road" : clickable ? "road-target clickable" : "road"
              }
              onClick={clickable ? () => onEdge?.(edge.id) : undefined}
            />
          </g>
        );
      })}

      {/* Nodes */}
      {Object.values(layout.nodes).map((node) => {
        const owner = nodeOwner[node.id];
        const kind = nodeKind[node.id];
        const placeable = highlight.nodes.has(node.id);
        const upgradeable = highlight.cities.has(node.id);
        if (owner == null && !placeable) return null;

        if (owner != null) {
          const color = PLAYER_COLORS[owner];
          if (kind === "city") {
            return (
              <g key={`node-${node.id}`} className={upgradeable ? "piece clickable" : "piece"} onClick={upgradeable ? () => onNode?.(node.id) : undefined}>
                <rect x={node.x - 12} y={node.y - 12} width={24} height={24} rx={5} fill={color} stroke={upgradeable ? "#f4ecd8" : "#fbf6ea"} strokeWidth={upgradeable ? 3 : 2.5} />
                <rect x={node.x - 5} y={node.y - 5} width={10} height={10} rx={2} fill="#ffffff55" />
              </g>
            );
          }
          return (
            <circle
              key={`node-${node.id}`}
              cx={node.x}
              cy={node.y}
              r={11}
              fill={color}
              stroke={upgradeable ? "#f4ecd8" : "#fbf6ea"}
              strokeWidth={upgradeable ? 3 : 2.5}
              className={upgradeable ? "piece clickable" : "piece"}
              onClick={upgradeable ? () => onNode?.(node.id) : undefined}
            />
          );
        }

        return (
          <circle
            key={`node-${node.id}`}
            cx={node.x}
            cy={node.y}
            r={9}
            className="node-target clickable"
            onClick={() => onNode?.(node.id)}
          />
        );
      })}
    </svg>
  );
}
