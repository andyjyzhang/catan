# TODO

This file tracks concrete work for the 1v1 Catan simulator, web client, and MCTS-NN bot.

## Gameplay UI

- [x] Show resource-gain events clearly in the action log.
- [x] Make the robber-blocked hex number easier to read.
- [x] Enforce friendly robber placement protection, not just friendly robber stealing/blocking protection.
- [x] Log exact stolen resource when the robber or a Knight steals.
- [x] During normal play, show hover/click targets for legal road, settlement, and city builds.
- [x] Show each player's total card count.
- [x] Warn when a player has 10 or more resource cards and may need to discard on a 7.
- [x] Replace remaining emoji UI with custom token-style icons.
- [x] Add visible delays/status messages between bot actions so players can follow the bot turn.
- [ ] Add board animations for dice payouts and robber movement.
- [ ] Add a compact game summary panel for VP, production, and longest-road pressure.

## Bot Strength Roadmap

- [x] Keep the current heuristic-weight MCTS as the baseline model.
- [x] Add checkpoint evaluation before accepting neural-network updates.
- [x] Train a policy head in addition to the value head.
- [x] Save a self-play replay dataset under `data/training/`.
- [x] Train from a replay buffer instead of only the latest self-play batch.
- [x] Evaluate candidate checkpoints against older checkpoint versions.
- [x] Sample self-play opponents from checkpoint history to reduce overfitting.
- [x] Use larger MCTS search budgets for training and evaluation.
- [x] Keep a capped search budget for the website bot so play remains responsive.
- [ ] Add richer exact-action policy targets, not only action-type policy targets.
- [ ] Add parallel self-play workers once single-process training is stable.

## Feature Engineering

- [x] Add per-resource production features.
- [x] Add settlement and city build-potential features.
- [x] Add road connectivity and longest-road threat features.
- [x] Add opponent expansion-blocking features.
- [x] Add development-card timing features.
- [x] Add resource scarcity and bank-pressure-style hand-risk features.
- [x] Add port usefulness features based on actual production.
- [x] Add robber-impact features for both players.
- [x] Add immediate tactical win/block features.
- [ ] Add action-specific tactical features for exact road, city, settlement, and robber targets.

## Training Quality

- [x] Track win rate, VP margin, illegal actions, crashes, and average turns for every candidate checkpoint.
- [x] Keep a small leaderboard of recent checkpoints.
- [x] Add a finite evaluation command for `candidate vs current`.
- [x] Add a stronger offline training profile separate from web-play defaults.
- [x] Add a quick regression smoke command for random valid boards plus MCTS-NN.
- [x] Enforce stricter valid boards with no adjacent matching number tokens.
- [x] Add live JSON progress logs for self-play games, SGD training, evaluation, and checkpoint saves.
- [x] Randomize first setup pick between player and bot.
- [x] Randomize port order/rotation during board generation.
- [x] Move continuous training logs under `data/training/logs/` instead of the temp folder.
- [x] Improve random board selection with a simple fairness score for resource clustering and production balance.
- [ ] Stop tracking generated training artifacts; keep `data/training/.gitkeep`, ignore `selfplay.jsonl`, `leaderboard.json`, and checkpoint history.
- [ ] Let the first stricter-board continuous training cycle finish and record whether the candidate checkpoint was accepted.
- [ ] Add a readable eval report/table for win rate, VP margin, average turns, illegal actions, crashes, and accepted/rejected checkpoints.
- [ ] Add chart-friendly CSV export for long training runs.
- [ ] Add periodic pruning/compaction for very large `data/training/selfplay.jsonl` files.

## Training Math

- The value head predicts win chance from state features. Its derivative is computed in `packages/bots/catan_bots/value_network.py` in `_train_one()` at `d_logit = (output - target) * output * (1.0 - output)`.
- The policy head predicts the chosen legal action type. Its gradient is `probability - label`, scaled by `policy_loss_weight`, and is applied in the same `_train_one()` method.
- `rng.shuffle(order)` randomizes training-example order each epoch so sequential positions from the same self-play game do not update the weights in the same repeated pattern.
