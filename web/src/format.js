// Display helpers: resource styling, victory-point math, and human-readable
// labels for engine actions (used in the action panel and the action log).

export const HUMAN_ID = 0;
export const BOT_ID = 1;

export const PLAYER_NAMES = { 0: "You", 1: "AlphaHex" };
export const PLAYER_COLORS = { 0: "#c1432f", 1: "#2d5f86" };

export const RESOURCE_META = {
  LUMBER: { label: "Lumber", color: "#2f7d3b", icon: "L" },
  BRICK: { label: "Brick", color: "#b5562a", icon: "B" },
  WOOL: { label: "Wool", color: "#7bc043", icon: "W" },
  GRAIN: { label: "Grain", color: "#e0b13a", icon: "G" },
  ORE: { label: "Ore", color: "#6b7280", icon: "O" },
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

export const DEV_CARD_META = {
  KNIGHT: { label: "Knight", icon: "K" },
  MONOPOLY: { label: "Monopoly", icon: "M" },
  YEAR_OF_PLENTY: { label: "Year of Plenty", icon: "Y" },
  ROAD_BUILDING: { label: "Road Building", icon: "R" },
  VICTORY_POINT: { label: "Victory Point", icon: "VP" },
};

export const DEV_CARD_ORDER = ["KNIGHT", "MONOPOLY", "YEAR_OF_PLENTY", "ROAD_BUILDING", "VICTORY_POINT"];

// Build costs (as lists of resource keys, for showing compact resource icons).
export const BUILD_COST = {
  ROAD: ["LUMBER", "BRICK"],
  SETTLEMENT: ["LUMBER", "BRICK", "WOOL", "GRAIN"],
  CITY: ["GRAIN", "GRAIN", "ORE", "ORE", "ORE"],
  DEV: ["WOOL", "GRAIN", "ORE"],
};

export const PHASE_LABEL = {
  SETUP_SETTLEMENT: "Setup - place a settlement",
  SETUP_ROAD: "Setup - place a road",
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

// Hidden Victory Point dev cards (only counted for your own actual total).
export function victoryPointCards(player) {
  return (player.dev_cards?.VICTORY_POINT || 0) + (player.new_dev_cards?.VICTORY_POINT || 0);
}

function resourceSummary(resources) {
  const parts = [];
  for (const [res, count] of Object.entries(resources)) {
    if (count > 0) parts.push(`${count} ${RESOURCE_META[res]?.label ?? res}`);
  }
  return parts.join(", ") || "nothing";
}

export function resourceGainLines(beforeState, afterState, action = null) {
  if (!beforeState || !afterState) return [];
  const stealLine = resourceStealLine(beforeState, afterState, action);
  if (stealLine) return [stealLine];
  const lines = [];
  for (const playerId of [0, 1]) {
    const before = beforeState.players?.[playerId]?.resources ?? {};
    const after = afterState.players?.[playerId]?.resources ?? {};
    const gained = {};
    for (const res of RESOURCE_ORDER) {
      const delta = (after[res] ?? 0) - (before[res] ?? 0);
      if (delta > 0) gained[res] = delta;
    }
    if (Object.keys(gained).length > 0) {
      lines.push({
        player: playerId,
        text: `${PLAYER_NAMES[playerId] ?? `P${playerId}`} gained ${resourceSummary(gained)}.`,
        kind: "gain",
      });
    }
  }
  return lines;
}

function resourceStealLine(beforeState, afterState, action) {
  if (!action || !["STEAL_RESOURCE", "PLAY_KNIGHT"].includes(action.action_type)) return null;
  const targetId = action.payload?.target_player;
  if (targetId == null) return null;
  const thiefId = action.player_id;
  const thiefBefore = beforeState.players?.[thiefId]?.resources ?? {};
  const thiefAfter = afterState.players?.[thiefId]?.resources ?? {};
  const targetBefore = beforeState.players?.[targetId]?.resources ?? {};
  const targetAfter = afterState.players?.[targetId]?.resources ?? {};
  let stolen = action.payload?.stolen_resource ?? null;
  if (!stolen) {
    stolen = RESOURCE_ORDER.find((res) => {
      const thiefGain = (thiefAfter[res] ?? 0) - (thiefBefore[res] ?? 0);
      const targetLoss = (targetBefore[res] ?? 0) - (targetAfter[res] ?? 0);
      return thiefGain > 0 && targetLoss > 0;
    });
  }
  if (!stolen) return null;
  return {
    player: thiefId,
    text: `${PLAYER_NAMES[thiefId] ?? `P${thiefId}`} stole 1 ${RESOURCE_META[stolen]?.label ?? stolen} from ${PLAYER_NAMES[targetId] ?? `P${targetId}`}.`,
    kind: "steal",
  };
}

// Short label for a single action (used on buttons).
export function actionLabel(action) {
  const p = action.payload ?? {};
  switch (action.action_type) {
    case "ROLL_DICE":
      return "Roll dice";
    case "END_TURN":
      return "End turn";
    case "BUY_DEV_CARD":
      return "Buy development card";
    case "STEAL_RESOURCE":
      return `Steal from ${PLAYER_NAMES[p.target_player] ?? `P${p.target_player}`}`;
    case "PLAY_KNIGHT":
      return p.target_player != null
        ? `Knight -> hex ${p.robber_hex_id} (rob ${PLAYER_NAMES[p.target_player]})`
        : `Knight -> hex ${p.robber_hex_id}`;
    case "PLAY_MONOPOLY":
      return `Monopoly: ${RESOURCE_META[p.resource]?.label ?? p.resource}`;
    case "PLAY_YEAR_OF_PLENTY":
      return `Year of Plenty: ${p.resources.map((r) => RESOURCE_META[r]?.label ?? r).join(" + ")}`;
    case "PLAY_ROAD_BUILDING":
      return `Road Building: edges ${(p.edge_ids ?? []).join(" & ")}`;
    case "MARITIME_TRADE":
      return `Trade ${p.give_count} ${RESOURCE_META[p.give]?.label ?? p.give} -> 1 ${RESOURCE_META[p.receive]?.label ?? p.receive}`;
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

// Sentence describing an applied action, for the action log. Returns null for
// actions that shouldn't appear in the log (dice rolls, end of turn).
export function logLine(action) {
  const who = PLAYER_NAMES[action.player_id] ?? `P${action.player_id}`;
  const p = action.payload ?? {};
  switch (action.action_type) {
    case "PLACE_SETTLEMENT":
    case "BUILD_SETTLEMENT":
      return `${who} built a settlement.`;
    case "BUILD_CITY":
      return `${who} upgraded to a city.`;
    case "PLACE_ROAD":
    case "BUILD_ROAD":
      return `${who} built a road.`;
    case "ROLL_DICE":
      return null;
    case "END_TURN":
      return null;
    case "DISCARD":
      return `${who} discarded ${resourceSummary(p.resources ?? {})}.`;
    case "MOVE_ROBBER":
      return `${who} moved the robber.`;
    case "STEAL_RESOURCE":
      return `${who} stole a card from ${PLAYER_NAMES[p.target_player] ?? `P${p.target_player}`}.`;
    case "BUY_DEV_CARD":
      return `${who} bought a development card.`;
    case "PLAY_KNIGHT":
      return `${who} played a Knight and moved the robber.`;
    case "PLAY_MONOPOLY":
      return `${who} played Monopoly on ${RESOURCE_META[p.resource]?.label ?? p.resource}.`;
    case "PLAY_YEAR_OF_PLENTY":
      return `${who} played Year of Plenty (${p.resources.map((r) => RESOURCE_META[r]?.label ?? r).join(", ")}).`;
    case "PLAY_ROAD_BUILDING":
      return `${who} played Road Building.`;
    case "MARITIME_TRADE":
      return `${who} traded ${p.give_count} ${RESOURCE_META[p.give]?.label ?? p.give} for 1 ${RESOURCE_META[p.receive]?.label ?? p.receive}.`;
    default:
      return `${who}: ${action.action_type}`;
  }
}
