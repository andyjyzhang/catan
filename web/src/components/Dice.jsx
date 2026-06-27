import React, { useEffect, useState } from "react";

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

function Die({ value, rolling }) {
  const on = new Set(PIPS[value] ?? []);
  return (
    <div className={`die${rolling ? " rolling" : ""}`} aria-label={`die showing ${value}`}>
      {Array.from({ length: 9 }, (_, i) => (
        <span key={i} className={on.has(i) ? "pip on" : "pip"} />
      ))}
    </div>
  );
}

const rand6 = () => 1 + Math.floor(Math.random() * 6);
const ROLL_TICK_MS = 70;
const ROLL_TICKS = 11;

export default function Dice({ total, salt = 0 }) {
  const [a, b] = total == null ? [1, 1] : facePair(total, salt);
  const [faces, setFaces] = useState([a, b]);
  const [rolling, setRolling] = useState(false);

  // On each new roll (total/salt change) tumble through random faces, then
  // settle on the reconstructed pair that sums to the engine's total.
  useEffect(() => {
    if (total == null) return;
    setRolling(true);
    let tick = 0;
    const id = setInterval(() => {
      tick += 1;
      if (tick >= ROLL_TICKS) {
        clearInterval(id);
        setFaces([a, b]);
        setRolling(false);
      } else {
        setFaces([rand6(), rand6()]);
      }
    }, ROLL_TICK_MS);
    return () => clearInterval(id);
  }, [total, salt, a, b]);

  if (total == null) return null;
  return (
    <div className={`dice${rolling ? " is-rolling" : ""}`}>
      <Die value={faces[0]} rolling={rolling} />
      <Die value={faces[1]} rolling={rolling} />
      <span className={`dice-total${total === 7 ? " seven" : ""}`}>{rolling ? "·" : total}</span>
    </div>
  );
}
