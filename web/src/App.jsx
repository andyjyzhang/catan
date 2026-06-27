import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Board from "./components/Board.jsx";
import ActionPanel from "./components/ActionPanel.jsx";
import ActionLog from "./components/ActionLog.jsx";
import PlayerPanel from "./components/PlayerPanel.jsx";
import * as api from "./api.js";
import { BOT_ID, HUMAN_ID, logLine, PLAYER_NAMES } from "./format.js";

const BOT_MOVE_DELAY_MS = 450;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Placement actions ask for a confirmation before being applied.
const PLACEMENT_PROMPT = {
  PLACE_SETTLEMENT: "Place your settlement here?",
  BUILD_SETTLEMENT: "Build a settlement here?",
  BUILD_CITY: "Upgrade to a city here?",
  PLACE_ROAD: "Place your road here?",
  BUILD_ROAD: "Build a road here?",
  MOVE_ROBBER: "Move the robber here?",
};

export default function App() {
  const [game, setGame] = useState(null); // { state, legal_actions, winner }
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null); // placement action awaiting confirmation

  const startedRef = useRef(false);
  const botRunningRef = useRef(false);

  const appendLog = useCallback((action) => {
    const text = logLine(action);
    if (text == null) return; // skipped actions (dice rolls, end turn)
    setLog((prev) => [...prev, { text, player: action.player_id }]);
  }, []);

  // Drive the bot until it is the human's turn again (or the game ends).
  const driveBot = useCallback(
    async (startState, startWinner) => {
      if (botRunningRef.current) return;
      botRunningRef.current = true;
      let state = startState;
      let winner = startWinner;
      try {
        while (winner == null && state.current_player !== HUMAN_ID) {
          await sleep(BOT_MOVE_DELAY_MS);
          const resp = await api.botStep(state);
          if (resp.action) appendLog(resp.action);
          state = resp.state;
          winner = resp.winner;
          setGame({ state, legal_actions: resp.legal_actions, winner });
        }
      } catch (err) {
        setError(String(err.message ?? err));
      } finally {
        botRunningRef.current = false;
      }
    },
    [appendLog]
  );

  const startNewGame = useCallback(async () => {
    setBusy(true);
    setError(null);
    setPending(null);
    try {
      const seed = Math.floor(Math.random() * 1_000_000);
      const resp = await api.newGame(seed);
      setLog([]);
      setGame({ state: resp.state, legal_actions: resp.legal_actions, winner: resp.winner });
      // Human (player 0) always starts setup, so no bot turn to drive yet.
    } catch (err) {
      setError(String(err.message ?? err));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    startNewGame();
  }, [startNewGame]);

  const handleAction = useCallback(
    async (action) => {
      if (!game || busy || botRunningRef.current) return;
      setBusy(true);
      setError(null);
      try {
        const resp = await api.applyAction(game.state, action);
        appendLog(action);
        setGame({ state: resp.state, legal_actions: resp.legal_actions, winner: resp.winner });
        if (resp.winner == null && resp.state.current_player !== HUMAN_ID) {
          await driveBot(resp.state, resp.winner);
        }
      } catch (err) {
        setError(String(err.message ?? err));
      } finally {
        setBusy(false);
      }
    },
    [game, busy, appendLog, driveBot]
  );

  // Highlight sets + click resolution for board-driven actions.
  const { highlight, resolveNode, resolveEdge, resolveHex } = useMemo(() => {
    const nodes = new Set();
    const cities = new Set();
    const edges = new Set();
    const hexes = new Set();
    const empty = { highlight: { nodes, cities, edges, hexes } };
    if (!game || game.winner != null || game.state.current_player !== HUMAN_ID) {
      return { ...empty, resolveNode: () => null, resolveEdge: () => null, resolveHex: () => null };
    }
    for (const a of game.legal_actions) {
      const p = a.payload ?? {};
      switch (a.action_type) {
        case "PLACE_SETTLEMENT":
        case "BUILD_SETTLEMENT":
          nodes.add(p.node_id);
          break;
        case "BUILD_CITY":
          cities.add(p.node_id);
          break;
        case "PLACE_ROAD":
        case "BUILD_ROAD":
          edges.add(p.edge_id);
          break;
        case "MOVE_ROBBER":
          hexes.add(p.hex_id);
          break;
        default:
          break;
      }
    }
    const find = (pred) => game.legal_actions.find(pred) ?? null;
    return {
      highlight: { nodes, cities, edges, hexes },
      resolveNode: (id) =>
        cities.has(id)
          ? find((a) => a.action_type === "BUILD_CITY" && a.payload.node_id === id)
          : find(
              (a) =>
                (a.action_type === "PLACE_SETTLEMENT" || a.action_type === "BUILD_SETTLEMENT") &&
                a.payload.node_id === id
            ),
      resolveEdge: (id) =>
        find(
          (a) => (a.action_type === "PLACE_ROAD" || a.action_type === "BUILD_ROAD") && a.payload.edge_id === id
        ),
      resolveHex: (id) => find((a) => a.action_type === "MOVE_ROBBER" && a.payload.hex_id === id),
    };
  }, [game]);

  const onNode = useCallback((id) => { const a = resolveNode(id); if (a) setPending(a); }, [resolveNode]);
  const onEdge = useCallback((id) => { const a = resolveEdge(id); if (a) setPending(a); }, [resolveEdge]);
  const onHex = useCallback((id) => { const a = resolveHex(id); if (a) setPending(a); }, [resolveHex]);

  const confirmPending = useCallback(() => {
    if (!pending) return;
    const action = pending;
    setPending(null);
    handleAction(action);
  }, [pending, handleAction]);

  // The board spot currently awaiting confirmation (for highlighting).
  const pendingMark = useMemo(() => {
    if (!pending) return null;
    const p = pending.payload ?? {};
    switch (pending.action_type) {
      case "PLACE_SETTLEMENT":
      case "BUILD_SETTLEMENT":
      case "BUILD_CITY":
        return { kind: "node", id: p.node_id };
      case "PLACE_ROAD":
      case "BUILD_ROAD":
        return { kind: "edge", id: p.edge_id };
      case "MOVE_ROBBER":
        return { kind: "hex", id: p.hex_id };
      default:
        return null;
    }
  }, [pending]);

  if (!game) {
    return (
      <div className="app loading">
        <p>{error ? `Error: ${error}` : "Loading…"}</p>
      </div>
    );
  }

  const { state, winner } = game;

  return (
    <div className="app">
      <div className="sea-bg">
        <Board
          state={state}
          highlight={highlight}
          pendingMark={pendingMark}
          pendingPrompt={
            pending ? PLACEMENT_PROMPT[pending.action_type] ?? "Confirm this action?" : null
          }
          onConfirm={confirmPending}
          onCancel={() => setPending(null)}
          confirmDisabled={busy}
          onNode={onNode}
          onEdge={onEdge}
          onHex={onHex}
        />
      </div>

      <div className="hud">
        <aside className="left-col">
          <div className="panel topbar">
            <span className="turn-indicator">
              <strong>{PLAYER_NAMES[state.current_player]}</strong> to move
            </span>
            <button className="btn-secondary" onClick={startNewGame} disabled={busy}>
              New game
            </button>
          </div>
          <PlayerPanel state={state} playerId={HUMAN_ID} targetVp={state.config.target_vp} />
          <PlayerPanel state={state} playerId={BOT_ID} targetVp={state.config.target_vp} />
          <ActionPanel
            state={state}
            legalActions={game.legal_actions}
            onAction={handleAction}
            busy={busy}
            winner={winner}
          />
        </aside>

        <aside className="right-col">
          <ActionLog entries={log} />
        </aside>

        <div className="banners">
          {error && <div className="error-banner">{error}</div>}
          {winner != null && (
            <div className={`winner-banner ${winner === HUMAN_ID ? "win" : "lose"}`}>
              {winner === HUMAN_ID ? "🎉 You won!" : "🤖 The bot won."} — start a new game to play again.
            </div>
          )}
        </div>
      </div>

      <footer className="credits">
        Licensed under MIT ·{" "}
        <a href="https://github.com/andyjyzhang/catan" target="_blank" rel="noopener noreferrer">
          GitHub
        </a>
      </footer>
    </div>
  );
}
