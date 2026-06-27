# Engine Backend

Standalone 1v1 Catan-style rules engine, bot framework, simulator, replay writer,
and FastAPI backend. This project does not automate, scrape, reverse engineer, or
interact with any external game site.

## Architecture

- `packages/engine/catan_engine/`
  - `board.py`: standard 19-hex board graph with explicit hexes, nodes, edges, and ports.
  - `state.py`: cloneable game config/state/player models and serialization.
  - `rules.py`: legal action generation and validated state transitions.
  - `scoring.py`: visible VP, total VP, Longest Road, and Largest Army.
  - `robber.py`: friendly robber protection and steal target logic.
  - `simulator.py`: bot-vs-bot runner and CLI.
  - `replay.py`: JSON replay persistence under `data/replays/`.
- `packages/bots/catan_bots/`
  - `MCTSBot` and `create_bot()`. `mcts` is the only supported bot.
- `packages/api/catan_api/`
  - FastAPI app and routes for games, bots, and replays.

Core public engine API:

```python
initialize_game(config=None, seed=0)
get_legal_actions(state)
apply_action(state, action, rng=None)
create_observation(state, player_id)
visible_vp(state, player_id)
total_vp(state, player_id)
run_game(bot_a, bot_b, config=None, seed=0, max_turns=1000)
run_many_games(bot_a, bot_b, n, seed=0)
save_replay(result, path=None)
```

## Setup

From the repository root:

```powershell
python -m pip install fastapi uvicorn httpx2
$env:PYTHONPATH='packages/engine;packages/bots;packages/api'
```

`httpx2` is only needed for in-process FastAPI `TestClient` smoke checks with
the currently installed FastAPI/Starlette stack.

## Run Simulations

```powershell
python -m catan_engine.simulator --bot-a mcts --bot-b mcts --games 1 --seed 0
```

The simulator prints:

- games played
- wins by player
- average turns
- average final VP
- illegal action count
- crash count
- replay path

Replay JSON files are written to `data/replays/`.

## Run API Server

```powershell
uvicorn catan_api.app:app --host 127.0.0.1 --port 8000
```

Useful endpoints:

- `GET /health`
- `POST /games/new`
- `POST /games/action`
- `POST /games/bot-match`
- `GET /bots`
- `GET /replays`
- `GET /replays/{filename}`

## Smoke Checks

No pytest suite is currently included, per project direction. Use these backend
smoke checks instead:

```powershell
python -c "from catan_engine import initialize_game, get_legal_actions; s=initialize_game(seed=0); print(s.phase.name, len(get_legal_actions(s)))"
python -c "from catan_bots import MCTSBot; from catan_engine.simulator import run_many_games; s=run_many_games(MCTSBot(), MCTSBot(), 1, seed=0); print(s['games_played'], s['illegal_action_count'], s['crash_count'])"
python -c "from fastapi.testclient import TestClient; from catan_api.app import app; c=TestClient(app); print(c.get('/health').json())"
```
