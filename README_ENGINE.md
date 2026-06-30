# Catan Engine Backend

## Setup

```powershell
cd "C:\Users\Andy Zhang\Downloads\catan"
python -m pip install -r requirements.txt
$env:PYTHONPATH='packages/engine;packages/bots;packages/api'
```

## Smoke Checks

```powershell
python -c "from catan_engine import initialize_game, get_legal_actions; s=initialize_game(seed=0); print(s.phase.name, len(get_legal_actions(s)))"
python -m catan_engine.simulator --bot-a mcts --bot-b mcts --games 1 --seed 0 --no-replay
python -c "from fastapi.testclient import TestClient; from catan_api.app import app; c=TestClient(app); print(c.get('/health').json())"
```

## Train Baseline MCTS Weights

The supported bot is `mcts`. Baseline training mutates the MCTS evaluation
weights, runs self-play matches against the current checkpoint, and saves
accepted weights to:

```text
packages/bots/catan_bots/mcts_weights.json
```

Quick local run:

```powershell
python -m catan_bots.train_mcts --seed 0
```

Longer run:

```powershell
python -m catan_bots.train_mcts --generations 20 --candidates 6 --games-per-candidate 6 --iterations 6 --rollout-depth 8 --branch-limit 6 --seed 0
```

Start fresh instead of resuming from the saved checkpoint:

```powershell
python -m catan_bots.train_mcts --fresh --generations 10 --candidates 4 --games-per-candidate 4 --seed 0
```

Train continuously until the process is stopped:

```powershell
python -m catan_bots.train_mcts --continuous --seed 0
```

Training does not write replay JSON files. Normal simulator/API runs still write
replays under `data/replays/`.

Games are initialized with seeded randomized standard boards. A valid board has
the standard 19-hex geometry, standard resource and number-token counts, one
desert with the robber, no number on the desert, no adjacent 6/8 number tokens,
and no adjacent matching number tokens. Board generation also randomizes the
starting player and port order/rotation, then keeps the best fair layout from
random attempts by reducing same-resource clustering and resource production
imbalance.

## Train MCTS-NN

The MCTS-NN layer is a small neural value/policy network. The value head predicts
win probability from encoded game-state features. The policy head predicts the
chosen legal action type and MCTS uses it as a move-ordering prior while still
only selecting from `get_legal_actions(state)`. Its live checkpoint is:

```text
packages/bots/catan_bots/mcts_value_network.json
```

Quick local run:

```powershell
python -m catan_bots.train_mcts_nn --profile quick --seed 0
```

Random-board plus MCTS-NN regression smoke:

```powershell
python -m catan_bots.train_mcts_nn --profile quick --smoke --seed 0
```

Continuous offline neural training:

```powershell
python -m catan_bots.train_mcts_nn --profile offline --continuous --seed 0
```

Continuous training writes JSON progress logs to:

```text
data/training/logs/train.out.log
```

Watch progress with:

```powershell
Get-Content data\training\logs\train.out.log -Tail 30 -Wait
```

Start a fresh value/policy network:

```powershell
python -m catan_bots.train_mcts_nn --profile offline --fresh --seed 0
```

Evaluate a candidate checkpoint against the current live checkpoint:

```powershell
python -m catan_bots.train_mcts_nn --profile quick --evaluate-candidate data\training\checkpoints\value_network_123.json
```

Neural self-play appends a JSONL replay dataset to `data/training/selfplay.jsonl`,
samples old examples from that replay buffer, and stores accepted checkpoint
history under `data/training/checkpoints/`. `data/training/leaderboard.json`
keeps the latest evaluation summaries.
