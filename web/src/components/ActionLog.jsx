import React, { useEffect, useRef } from "react";
import { PLAYER_COLORS } from "../format.js";

export default function ActionLog({ entries }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  return (
    <div className="panel log-panel">
      <h2>Action Log</h2>
      <div className="log-list">
        {entries.length === 0 && <p className="muted">No actions yet. Place your first settlement to begin.</p>}
        {entries.map((entry, i) => (
          <div className="log-entry" key={i}>
            <span className="log-dot" style={{ background: PLAYER_COLORS[entry.player] ?? "#888" }} />
            <span className="log-text">{entry.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
