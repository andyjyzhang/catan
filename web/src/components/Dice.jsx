import React from "react";

// The engine reports only the dice total, so we reconstruct a plausible pair of
// faces that sum to it (varied by `salt` so the same total isn't always shown
// the same way). Purely cosmetic — the total is what the game acts on.
function facePair(total, salt) {
  const opts = [];
  for (let d = Math.max(1, total - 6); d <= Math.min(6, total - 1); d++) opts.push(d);
  const d1 = opts[Math.abs(salt) % opts.length];
  return [d1, total - d1];
}

// Pip positions on a 3x3 grid for each face value.
const PIPS = {
  1: [4],
  2: [0, 8],
  3: [0, 4, 8],
  4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};

function Die({ value }) {
  const on = new Set(PIPS[value] ?? []);
  return (
    <div className="die" aria-label={`die showing ${value}`}>
      {Array.from({ length: 9 }, (_, i) => (
        <span key={i} className={on.has(i) ? "pip on" : "pip"} />
      ))}
    </div>
  );
}

export default function Dice({ total, salt = 0 }) {
  if (total == null) return null;
  const [a, b] = facePair(total, salt);
  return (
    <div className="dice" key={`${total}-${salt}`}>
      <Die value={a} />
      <Die value={b} />
      <span className={`dice-total${total === 7 ? " seven" : ""}`}>{total}</span>
    </div>
  );
}
