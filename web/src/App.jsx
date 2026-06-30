import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Board from "./components/Board.jsx";
import ActionPanel from "./components/ActionPanel.jsx";
import ActionsPanel from "./components/ActionsPanel.jsx";
import ActionLog from "./components/ActionLog.jsx";
import PlayerPanel from "./components/PlayerPanel.jsx";
import BankPanel from "./components/BankPanel.jsx";
import LegendModal from "./components/LegendModal.jsx";
import * as api from "./api.js";
import { actionLabel, BOT_ID, HUMAN_ID, logLine, PLAYER_NAMES, resourceGainLines } from "./format.js";

const BOT_THINK_DELAY_MS = 900;
const BOT_REVEAL_DELAY_MS = 700;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Placement actions ask for a confirmation before being applied.
const PLACEMENT_PROMPT = {
  PLACE_SETTLEMENT: "Place your settlement here?",
  BUILD_SETTLEMENT: "Build a settlement here?",
  BUILD_CITY: "Upgrade to a city here?",
  PLACE_ROAD: "Place your road here?",
  BUILD_ROAD: "Build a road here?",
  MOVE_ROBBER: "Move the robber here?",
  PLAY_KNIGHT: "Play Knight & move robber here?",
  PLAY_ROAD_BUILDING: "Build road here?",
};

export default function App() {
  const [game, setGame] = useState(null); // { state, legal_actions, winner }
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null); // placement action awaiting confirmation
  const [showKey, setShowKey] = useState(false); // legend modal
  const [actionMode, setActionMode] = useState(null); // armed board action (build/knight/road-building)
  const [roadFirst, setRoadFirst] = useState(null); // first edge picked for Road Building
  const [botStatus, setBotStatus] = useState(null);

  const startedRef = useRef(false);
  const botRunningRef = useRef(false);
  const botRunIdRef = useRef(0);

  const appendLog = useCallback((action, beforeState = null, afterState = null) => {
    const text = logLine(action);
    const resourceLines = resourceGainLines(beforeState, afterState, action);
    const exactSteal = resourceLines.some((entry) => entry.kind === "steal");
    const entries = [];
    if (text != null && !(action.action_type === "STEAL_RESOURCE" && exactSteal)) {
      entries.push({ text, player: action.player_id, kind: "action" });
    }
    entries.push(...resourceLines);
    if (entries.length === 0) return;
    setLog((prev) => [...prev, ...entries]);
  }, []);

  // Drive the bot until it is the human's turn again (or the game ends).
  const driveBot = useCallback(
    async (startState, startWinner) => {
      if (botRunningRef.current) return;
      const runId = ++botRunIdRef.current;
      botRunningRef.current = true;
      let state = startState;
      let winner = startWinner;
      try {
        while (winner == null && state.current_player !== HUMAN_ID) {
          setBotStatus(`${PLAYER_NAMES[BOT_ID]} is thinking...`);
          await sleep(BOT_THINK_DELAY_MS);
          if (runId !== botRunIdRef.current) return;
          setBotStatus(`${PLAYER_NAMES[BOT_ID]} is choosing a move...`);
          const resp = await api.botStep(state);
          if (runId !== botRunIdRef.current) return;
          if (resp.action) {
            appendLog(resp.action, state, resp.state);
            setBotStatus(`${PLAYER_NAMES[BOT_ID]} chose ${actionLabel(resp.action)}.`);
          }
          state = resp.state;
          winner = resp.winner;
          setGame({ state, legal_actions: resp.legal_actions, winner });
          await sleep(BOT_REVEAL_DELAY_MS);
          if (runId !== botRunIdRef.current) return;
        }
      } catch (err) {
        setError(String(err.message ?? err));
      } finally {
        if (runId === botRunIdRef.current) {
          botRunningRef.current = false;
          setBotStatus(null);
        }
      }
    },
    [appendLog]
  );

  const resetTargeting = useCallback(() => {
    setPending(null);
    setActionMode(null);
    setRoadFirst(null);
  }, []);

  const startNewGame = useCallback(async () => {
    botRunIdRef.current += 1;
    botRunningRef.current = false;
    setBotStatus(null);
    setBusy(true);
    setError(null);
    resetTargeting();
    try {
      const seed = Math.floor(Math.random() * 1_000_000);
      const resp = await api.newGame(seed);
      setLog([]);
      setGame({ state: resp.state, legal_actions: resp.legal_actions, winner: resp.winner });
      if (resp.winner == null && resp.state.current_player !== HUMAN_ID) {
        await driveBot(resp.state, resp.winner);
      }
    } catch (err) {
      setError(String(err.message ?? err));
    } finally {
      setBusy(false);
    }
  }, [driveBot, resetTargeting]);

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
      resetTargeting();
      try {
        const resp = await api.applyAction(game.state, action);
        appendLog(action, game.state, resp.state);
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
    [game, busy, appendLog, driveBot, resetTargeting]
  );

  // Highlight sets + click resolution. Forced phases always show targets. In
  // MAIN, legal build targets also appear without opening the side menu first.
  const { highlight, resolveNode, resolveEdge, resolveHex } = useMemo(() => {
    const nodes = new Set();
    const cities = new Set();
    const edges = new Set();
    const hexes = new Set();
    const none = () => null;
    const wrap = (extra) => ({ highlight: { nodes, cities, edges, hexes }, resolveNode: none, resolveEdge: none, resolveHex: none, ...extra });
    if (!game || game.winner != null || game.state.current_player !== HUMAN_ID) {
      return wrap();
    }
    const la = game.legal_actions;
    const phase = game.state.phase;
    const each = (type, fn) => la.forEach((a) => a.action_type === type && fn(a.payload));
    const findBy = (type, key, id) => la.find((a) => a.action_type === type && a.payload[key] === id) ?? null;

    // ---- Forced sub-phases (no menu needed) ----
    if (phase === "SETUP_SETTLEMENT") {
      each("PLACE_SETTLEMENT", (p) => nodes.add(p.node_id));
      return wrap({ resolveNode: (id) => findBy("PLACE_SETTLEMENT", "node_id", id) });
    }
    if (phase === "SETUP_ROAD") {
      each("PLACE_ROAD", (p) => edges.add(p.edge_id));
      return wrap({ resolveEdge: (id) => findBy("PLACE_ROAD", "edge_id", id) });
    }
    if (phase === "MOVE_ROBBER") {
      each("MOVE_ROBBER", (p) => hexes.add(p.hex_id));
      return wrap({ resolveHex: (id) => findBy("MOVE_ROBBER", "hex_id", id) });
    }

    // ---- MAIN: only the armed action highlights its spots ----
    if (phase === "MAIN") {
      if (actionMode == null) {
        each("BUILD_SETTLEMENT", (p) => nodes.add(p.node_id));
        each("BUILD_CITY", (p) => cities.add(p.node_id));
        each("BUILD_ROAD", (p) => edges.add(p.edge_id));
        return wrap({
          resolveNode: (id) => findBy("BUILD_CITY", "node_id", id) ?? findBy("BUILD_SETTLEMENT", "node_id", id),
          resolveEdge: (id) => findBy("BUILD_ROAD", "edge_id", id),
        });
      }
      if (actionMode === "BUILD_SETTLEMENT") {
        each("BUILD_SETTLEMENT", (p) => nodes.add(p.node_id));
        return wrap({ resolveNode: (id) => findBy("BUILD_SETTLEMENT", "node_id", id) });
      }
      if (actionMode === "BUILD_CITY") {
        each("BUILD_CITY", (p) => cities.add(p.node_id));
        return wrap({ resolveNode: (id) => findBy("BUILD_CITY", "node_id", id) });
      }
      if (actionMode === "BUILD_ROAD") {
        each("BUILD_ROAD", (p) => edges.add(p.edge_id));
        return wrap({ resolveEdge: (id) => findBy("BUILD_ROAD", "edge_id", id) });
      }
      if (actionMode === "KNIGHT") {
        each("PLAY_KNIGHT", (p) => hexes.add(p.robber_hex_id));
        return wrap({ resolveHex: (id) => findBy("PLAY_KNIGHT", "robber_hex_id", id) });
      }
      if (actionMode === "ROAD_BUILDING") {
        const ra = la.filter((a) => a.action_type === "PLAY_ROAD_BUILDING");
        if (roadFirst == null) {
          ra.forEach((a) => a.payload.edge_ids.length === 1 && edges.add(a.payload.edge_ids[0]));
        } else {
          edges.add(roadFirst);
          ra.forEach((a) => {
            const e = a.payload.edge_ids;
            if (e.length === 2 && e.includes(roadFirst)) edges.add(e[0] === roadFirst ? e[1] : e[0]);
          });
        }
        return wrap(); // edge clicks handled in onEdge
      }
    }
    return wrap();
  }, [game, actionMode, roadFirst]);

  const onNode = useCallback((id) => { const a = resolveNode(id); if (a) setPending(a); }, [resolveNode]);
  const onHex = useCallback((id) => { const a = resolveHex(id); if (a) setPending(a); }, [resolveHex]);
  const onEdge = useCallback(
    (id) => {
      // Road Building takes up to two clicks to choose an edge pair.
      if (actionMode === "ROAD_BUILDING" && game) {
        const ra = game.legal_actions.filter((a) => a.action_type === "PLAY_ROAD_BUILDING");
        if (roadFirst == null) {
          const hasPair = ra.some((a) => a.payload.edge_ids.length === 2 && a.payload.edge_ids.includes(id));
          if (hasPair) {
            setRoadFirst(id);
            return;
          }
          const single = ra.find((a) => a.payload.edge_ids.length === 1 && a.payload.edge_ids[0] === id);
          if (single) setPending(single);
          return;
        }
        if (id === roadFirst) {
          setRoadFirst(null);
          return;
        }
        const pair = ra.find(
          (a) =>
            a.payload.edge_ids.length === 2 &&
            a.payload.edge_ids.includes(roadFirst) &&
            a.payload.edge_ids.includes(id)
        );
        if (pair) setPending(pair);
        return;
      }
      const a = resolveEdge(id);
      if (a) setPending(a);
    },
    [actionMode, roadFirst, game, resolveEdge]
  );

  const toggleMode = useCallback((mode) => {
    setPending(null);
    setRoadFirst(null);
    setActionMode((cur) => (cur === mode ? null : mode));
  }, []);

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
      case "PLAY_KNIGHT":
        return { kind: "hex", id: p.robber_hex_id };
      case "PLAY_ROAD_BUILDING":
        return { kind: "edge", id: p.edge_ids[p.edge_ids.length - 1] };
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

  const byType = {};
  for (const a of game.legal_actions) {
    (byType[a.action_type] ??= []).push(a);
  }

  return (
    <div className="app">
      <div className="sea-bg">
        <Board
          state={state}
          highlight={highlight}
          pendingMark={pendingMark}
          selectedEdgeId={roadFirst}
          pendingPrompt={
            pending ? PLACEMENT_PROMPT[pending.action_type] ?? "Confirm this action?" : null
          }
          onConfirm={confirmPending}
          onCancel={() => {
            setPending(null);
            setRoadFirst(null);
          }}
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
          <PlayerPanel
            state={state}
            playerId={HUMAN_ID}
            targetVp={state.config.target_vp}
            byType={byType}
            onAction={handleAction}
            onToggleMode={toggleMode}
            actionMode={actionMode}
          />
          <PlayerPanel state={state} playerId={BOT_ID} targetVp={state.config.target_vp} />
          <ActionsPanel
            byType={byType}
            onAction={handleAction}
            actionMode={actionMode}
            onToggleMode={toggleMode}
            isHumanTurn={winner == null && state.current_player === HUMAN_ID}
          />
          <ActionPanel
            state={state}
            legalActions={game.legal_actions}
            onAction={handleAction}
            busy={busy}
            winner={winner}
            botStatus={botStatus}
          />
        </aside>

        <aside className="right-col">
          <BankPanel state={state} />
          <ActionLog entries={log} />
        </aside>

        <div className="banners">
          {error && <div className="error-banner">{error}</div>}
          {winner != null && (
            <div className={`winner-banner ${winner === HUMAN_ID ? "win" : "lose"}`}>
              {winner === HUMAN_ID ? "You won." : "The bot won."} Start a new game to play again.
            </div>
          )}
        </div>
      </div>

      <footer className="credits">
        Licensed under MIT -{" "}
        <a href="https://github.com/andyjyzhang/catan" target="_blank" rel="noopener noreferrer">
          GitHub
        </a>
      </footer>

      <button className="key-button" onClick={() => setShowKey(true)} title="Key / legend">
        Key
      </button>

      <a
        className="help-button"
        href="https://www.catan.com/understand-catan/game-rules"
        target="_blank"
        rel="noopener noreferrer"
        title="Rules of Catan"
        aria-label="Rules of Catan"
      >
        ?
      </a>

      {showKey && <LegendModal onClose={() => setShowKey(false)} />}
    </div>
  );
}
