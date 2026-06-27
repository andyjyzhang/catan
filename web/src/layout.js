// Compute 2D positions for the board from the serialized engine board.
//
// The engine does not store coordinates, but the topology is fully determined:
//  - Hex ids follow axial coords (q, r) sorted by (r, q).
//  - Each hex's `node_ids` are listed in corner order k = 0..5, where corner k
//    sits at angle (60*k - 30) degrees around the hex center (pointy-top).
// We rebuild hex centers from the axial order and derive every node position
// from the corner it belongs to. Edge endpoints are then just node positions.

const SQRT3 = Math.sqrt(3);

function axialCoords() {
  const coords = [];
  for (let q = -2; q <= 2; q++) {
    for (let r = -2; r <= 2; r++) {
      if (Math.max(Math.abs(q), Math.abs(r), Math.abs(-q - r)) <= 2) {
        coords.push([q, r]);
      }
    }
  }
  // Engine sorts by (r, q).
  coords.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  return coords;
}

function hexCenter(q, r) {
  return { x: SQRT3 * (q + r / 2), y: 1.5 * r };
}

function corner(center, k) {
  const angle = ((60 * k - 30) * Math.PI) / 180;
  return { x: center.x + Math.cos(angle), y: center.y + Math.sin(angle) };
}

export function computeLayout(board, scale = 56, padding = 44) {
  const coords = axialCoords();
  const nodePos = {}; // node_id -> {x, y}

  const rawHexes = Object.values(board.hexes)
    .slice()
    .sort((a, b) => a.id - b.id)
    .map((hex) => {
      const [q, r] = coords[hex.id];
      const center = hexCenter(q, r);
      hex.node_ids.forEach((nodeId, k) => {
        nodePos[nodeId] = corner(center, k);
      });
      return { ...hex, center };
    });

  // Bounding box over node positions to build the SVG viewBox.
  const xs = Object.values(nodePos).map((p) => p.x);
  const ys = Object.values(nodePos).map((p) => p.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const tx = (x) => (x - minX) * scale + padding;
  const ty = (y) => (y - minY) * scale + padding;

  const hexes = rawHexes.map((hex) => ({
    id: hex.id,
    type: hex.hex_type,
    number: hex.number_token,
    x: tx(hex.center.x),
    y: ty(hex.center.y),
  }));

  const nodes = {};
  for (const [id, p] of Object.entries(nodePos)) {
    const node = board.nodes[id];
    nodes[id] = { id: Number(id), x: tx(p.x), y: ty(p.y), port: node?.port ?? null };
  }

  const edges = Object.values(board.edges).map((edge) => {
    const a = nodePos[edge.node_a];
    const b = nodePos[edge.node_b];
    return {
      id: edge.id,
      x1: tx(a.x),
      y1: ty(a.y),
      x2: tx(b.x),
      y2: ty(b.y),
      mx: tx((a.x + b.x) / 2),
      my: ty((a.y + b.y) / 2),
    };
  });

  const width = (Math.max(...xs) - minX) * scale + padding * 2;
  const height = (Math.max(...ys) - minY) * scale + padding * 2;

  return { hexes, nodes, edges, width, height };
}
