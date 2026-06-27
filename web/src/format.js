// Display helpers: resource styling, victory-point math, and human-readable
// labels for engine actions (used in the action panel and the action log).

export const HUMAN_ID = 0;
export const BOT_ID = 1;

export const PLAYER_NAMES = { 0: "You", 1: "Bot" };
export const PLAYER_COLORS = { 0: "#c1432f", 1: "#2d5f86" };

export const RESOURCE_META = {
  LUMBER: { label: "Lumber", color: "#2f7d3b", emoji: "🌲" },
  BRICK: { label: "Brick", color: "#b5562a", emoji: "🧱" },
  WOOL: { label: "Wool", color: "#7bc043", emoji: "🐑" },
  GRAIN: { label: "Grain", color: "#e0b13a", emoji: "🌾" },
  ORE: { label: "Ore", color: "#6b7280", emoji: "⛰️" },
};

export const HEX_META = {
  LUMBER: { color: "#3f9d4f", label: "Forest" },
  BRICK: { color: "#c4673a", label: "Hills" },
  WOOL: { color: "#8fcb55", label: "Pasture" },
  GRAIN: { color: "#e8c25a", label: "Field" },
  ORE: { color: "#8b93a1", label: "Mountains" },
  DESERT: { color: "#d8c89a", label: "Desert" },
};

export const RESOURCE_ORDER = ["LUMBER", "BRICK", "WOOL", "GRAIN", "ORE"];

export const PHASE_LABEL = {
  SETUP_SETTLEMENT: "Setup — place a settlement",
  SETUP_ROAD: "Setup — place a road",
  ROLL: "Roll the dice",
  DISCARD: "Discard cards (rolled a 7)",
  MOVE_ROBBER: "Move the robber",
  STEAL: "Steal a resource",
  MAIN: "Your move",
  GAME_OVER: "Game over",
};

export function visibleVp(state, playerId) {
  const p = state.players[playerId];
  let vp = p.settlements.length + 2 * p.cities.length;
  if (state.longest_road_owner === playerId) vp += 2;
  if (state.largest_army_owner === playerId) vp += 2;
  return vp;
}

function resourceSummary(resources) {
  const parts = [];
  for (const [res, count] of Object.entries(resources)) {
    if (count > 0) parts.push(`${count} ${RESOURCE_META[res]?.label ?? res}`);
  }
  return parts.join(", ") || "nothing";
}

// Short label for a single action (used on buttons).
export function actionLabel(action) {
  const p = action.payload ?? {};
  switch (action.action_type) {
    case "ROLL_DICE":
      return "🎲 Roll dice";
    case "END_TURN":
      return "End turn";
    case "BUY_DEV_CARD":
      return "Buy development card";
    case "STEAL_RESOURCE":
      return `Steal from ${PLAYER_NAMES[p.target_player] ?? `P${p.target_player}`}`;
    case "PLAY_KNIGHT":
      return p.target_player != null
        ? `Knight → hex ${p.robber_hex_id} (rob ${PLAYER_NAMES[p.target_player]})`
        : `Knight → hex ${p.robber_hex_id}`;
    case "PLAY_MONOPOLY":
      return `Monopoly: ${RESOURCE_META[p.resource]?.label ?? p.resource}`;
    case "PLAY_YEAR_OF_PLENTY":
      return `Year of Plenty: ${p.resources.map((r) => RESOURCE_META[r]?.label ?? r).join(" + ")}`;
    case "PLAY_ROAD_BUILDING":
      return `Road Building: edges ${(p.edge_ids ?? []).join(" & ")}`;
    case "MARITIME_TRADE":
      return `Trade ${p.give_count} ${RESOURCE_META[p.give]?.label ?? p.give} → 1 ${RESOURCE_META[p.receive]?.label ?? p.receive}`;
    case "BUILD_SETTLEMENT":
    case "PLACE_SETTLEMENT":
      return `Settlement @ node ${p.node_id}`;
    case "BUILD_CITY":
      return `City @ node ${p.node_id}`;
    case "BUILD_ROAD":
    case "PLACE_ROAD":
      return `Road @ edge ${p.edge_id}`;
    case "DISCARD":
      return `Discard ${resourceSummary(p.resources ?? {})}`;
    default:
      return action.action_type;
  }
}

// Sentence describing an applied action, for the action log.
export function logLine(action) {
  const who = PLAYER_NAMES[action.player_id] ?? `P${action.player_id}`;
  const p = action.payload ?? {};
  switch (action.action_type) {
    case "PLACE_SETTLEMENT":
    case "BUILD_SETTLEMENT":
      return `${who} built a settlement (node ${p.node_id}).`;
    case "BUILD_CITY":
      return `${who} upgraded to a city (node ${p.node_id}).`;
    case "PLACE_ROAD":
    case "BUILD_ROAD":
      return `${who} built a road (edge ${p.edge_id}).`;
    case "ROLL_DICE":
      return `${who} rolled the dice.`;
    case "DISCARD":
      return `${who} discarded ${resourceSummary(p.resources ?? {})}.`;
    case "MOVE_ROBBER":
      return `${who} moved the robber to hex ${p.hex_id}.`;
    case "STEAL_RESOURCE":
      return `${who} stole a card from ${PLAYER_NAMES[p.target_player] ?? `P${p.target_player}`}.`;
    case "BUY_DEV_CARD":
      return `${who} bought a development card.`;
    case "PLAY_KNIGHT":
      return `${who} played a Knight and moved the robber to hex ${p.robber_hex_id}.`;
    case "PLAY_MONOPOLY":
      return `${who} played Monopoly on ${RESOURCE_META[p.resource]?.label ?? p.resource}.`;
    case "PLAY_YEAR_OF_PLENTY":
      return `${who} played Year of Plenty (${p.resources.map((r) => RESOURCE_META[r]?.label ?? r).join(", ")}).`;
    case "PLAY_ROAD_BUILDING":
      return `${who} played Road Building.`;
    case "MARITIME_TRADE":
      return `${who} traded ${p.give_count} ${RESOURCE_META[p.give]?.label ?? p.give} for 1 ${RESOURCE_META[p.receive]?.label ?? p.receive}.`;
    case "END_TURN":
      return `${who} ended their turn.`;
    default:
      return `${who}: ${action.action_type}`;
  }
}
