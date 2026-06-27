import React, { useState } from "react";
import { RESOURCE_META, RESOURCE_ORDER } from "../format.js";

// On a 7, a player over the limit must discard floor(hand/2) cards. We let the
// user pick counts and submit a DISCARD action; the engine validates it.
export default function DiscardPanel({ state, onSubmit }) {
  const playerId = state.current_player;
  const hand = state.players[playerId].resources;
  const handSize = Object.values(hand).reduce((a, b) => a + b, 0);
  const required = Math.floor(handSize / 2);

  const [picked, setPicked] = useState(() =>
    Object.fromEntries(RESOURCE_ORDER.map((r) => [r, 0]))
  );
  const total = Object.values(picked).reduce((a, b) => a + b, 0);

  const adjust = (res, delta) => {
    setPicked((prev) => {
      const next = Math.max(0, Math.min(hand[res] ?? 0, (prev[res] ?? 0) + delta));
      return { ...prev, [res]: next };
    });
  };

  const submit = () => {
    const payload = { resources: {} };
    for (const [res, count] of Object.entries(picked)) {
      if (count > 0) payload.resources[res] = count;
    }
    onSubmit({ action_type: "DISCARD", player_id: playerId, payload });
  };

  return (
    <div className="discard-panel">
      <p>
        You rolled into a discard: choose <strong>{required}</strong> cards to discard.
      </p>
      <div className="discard-rows">
        {RESOURCE_ORDER.map((res) => (
          <div className="discard-row" key={res}>
            <span className="discard-name">
              {RESOURCE_META[res].emoji} {RESOURCE_META[res].label}
            </span>
            <span className="muted">have {hand[res] ?? 0}</span>
            <div className="stepper">
              <button onClick={() => adjust(res, -1)} disabled={picked[res] === 0}>
                −
              </button>
              <span className="stepper-value">{picked[res]}</span>
              <button onClick={() => adjust(res, 1)} disabled={picked[res] >= (hand[res] ?? 0)}>
                +
              </button>
            </div>
          </div>
        ))}
      </div>
      <button
        className="btn-primary"
        disabled={total !== required}
        onClick={submit}
      >
        Discard {total}/{required}
      </button>
    </div>
  );
}
