import React from "react";
import {
  HUMAN_ID,
  PLAYER_COLORS,
  PLAYER_NAMES,
  RESOURCE_META,
  RESOURCE_ORDER,
  visibleVp,
} from "../format.js";

function totalResources(resources) {
  return Object.values(resources).reduce((a, b) => a + b, 0);
}

function totalDev(player) {
  const sum = (obj) => Object.values(obj).reduce((a, b) => a + b, 0);
  return sum(player.dev_cards) + sum(player.new_dev_cards);
}

export default function PlayerPanel({ state, playerId, targetVp }) {
  const player = state.players[playerId];
  const isHuman = playerId === HUMAN_ID;
  const isTurn = state.current_player === playerId;
  const vp = visibleVp(state, playerId);

  return (
    <div className={`panel player-panel ${isTurn ? "active-turn" : ""}`}>
      <div className="player-head">
        <span className="player-chip" style={{ background: PLAYER_COLORS[playerId] }} />
        <h2>{PLAYER_NAMES[playerId]}</h2>
        {isTurn && <span className="turn-tag">to move</span>}
        <span className="vp-badge">
          {vp}/{targetVp} VP
        </span>
      </div>

      <div className="badges">
        {state.longest_road_owner === playerId && <span className="badge">Longest Road</span>}
        {state.largest_army_owner === playerId && <span className="badge">Largest Army ({player.played_knights}⚔)</span>}
      </div>

      {isHuman ? (
        <div className="resources">
          {RESOURCE_ORDER.map((res) => (
            <div className="resource" key={res} title={RESOURCE_META[res].label}>
              <span className="resource-emoji">{RESOURCE_META[res].emoji}</span>
              <span className="resource-count">{player.resources[res] ?? 0}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="hidden-hand">
          🂠 {totalResources(player.resources)} resource cards · {totalDev(player)} dev cards
        </div>
      )}

      <div className="stockpile">
        <span>🏠 {5 - player.settlements_remaining}/5</span>
        <span>🏛️ {4 - player.cities_remaining}/4</span>
        <span>🛣️ {15 - player.roads_remaining}/15</span>
        {isHuman && <span>🃏 {totalDev(player)} dev</span>}
      </div>
    </div>
  );
}
