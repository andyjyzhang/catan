import React, { useState } from "react";
import { actionLabel, HUMAN_ID, PHASE_LABEL } from "../format.js";
import DiscardPanel from "./DiscardPanel.jsx";
import Dice from "./Dice.jsx";

// Action types the player performs by clicking the board.
const BOARD_DRIVEN = new Set([
  "PLACE_SETTLEMENT",
  "BUILD_SETTLEMENT",
  "BUILD_CITY",
  "PLACE_ROAD",
  "BUILD_ROAD",
  "MOVE_ROBBER",
]);

const BOARD_HINT = {
  PLACE_SETTLEMENT: "Click a highlighted intersection to place your settlement.",
  BUILD_SETTLEMENT: "Click a highlighted intersection to build a settlement.",
  BUILD_CITY: "Click one of your settlements to upgrade it to a city.",
  PLACE_ROAD: "Click a highlighted edge to place your road.",
  BUILD_ROAD: "Click a highlighted edge to build a road.",
  MOVE_ROBBER: "Click a hex to move the robber there.",
};

// Order and friendly headers for the non-spatial action groups.
const GROUPS = [
  { type: "ROLL_DICE", title: null },
  { type: "STEAL_RESOURCE", title: "Steal from" },
  { type: "BUY_DEV_CARD", title: null },
  { type: "PLAY_KNIGHT", title: "Play Knight" },
  { type: "PLAY_MONOPOLY", title: "Play Monopoly" },
  { type: "PLAY_YEAR_OF_PLENTY", title: "Play Year of Plenty" },
  { type: "PLAY_ROAD_BUILDING", title: "Play Road Building" },
  { type: "MARITIME_TRADE", title: "Maritime trade" },
  { type: "END_TURN", title: null },
];

function Group({ title, actions, onAction }) {
  const collapsible = actions.length > 6;
  const [open, setOpen] = useState(false);
  const shown = collapsible && !open ? [] : actions;

  return (
    <div className="action-group">
      {title && (
        <div className="action-group-head">
          <span>{title}</span>
          {collapsible && (
            <button className="link-btn" onClick={() => setOpen((o) => !o)}>
              {open ? "hide" : `show ${actions.length}`}
            </button>
          )}
        </div>
      )}
      <div className="action-buttons">
        {shown.map((action, i) => (
          <button
            key={i}
            className={action.action_type === "END_TURN" ? "btn-secondary" : action.action_type === "ROLL_DICE" ? "btn-primary" : "btn"}
            onClick={() => onAction(action)}
          >
            {actionLabel(action)}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ActionPanel({ state, legalActions, onAction, busy, winner }) {
  const isHumanTurn = state.current_player === HUMAN_ID && winner == null;
  const phase = state.phase;

  if (winner != null) {
    return (
      <div className="panel action-panel">
        <h2>Controls</h2>
        <p className="muted">The game is over. Start a new game to play again.</p>
      </div>
    );
  }

  if (!isHumanTurn) {
    return (
      <div className="panel action-panel">
        <h2>Controls</h2>
        <p className="thinking">
          <span className="thinking-dot" />
          The bot is plotting its move
        </p>
        {state.dice_roll != null && (
          <div className="dice-tray">
            <Dice total={state.dice_roll} salt={state.turn_number} />
          </div>
        )}
      </div>
    );
  }

  const byType = {};
  for (const a of legalActions) {
    (byType[a.action_type] ??= []).push(a);
  }

  const boardTypes = Object.keys(byType).filter((t) => BOARD_DRIVEN.has(t));

  return (
    <div className="panel action-panel">
      <h2>Controls</h2>
      <p className="phase-label">{PHASE_LABEL[phase] ?? phase}</p>
      {state.dice_roll != null && (
        <div className="dice-tray">
          <Dice total={state.dice_roll} salt={state.turn_number} />
        </div>
      )}

      {phase === "DISCARD" ? (
        <DiscardPanel state={state} onSubmit={onAction} />
      ) : (
        <>
          {boardTypes.map((t) => (
            <p className="board-hint" key={t}>
              {BOARD_HINT[t]}
            </p>
          ))}
          {GROUPS.map((g) =>
            byType[g.type] ? (
              <Group key={g.type} title={g.title} actions={byType[g.type]} onAction={onAction} />
            ) : null
          )}
        </>
      )}
    </div>
  );
}
