from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from catan_bots.mcts_bot import MCTSBot
from catan_bots.value_network import (
    DEFAULT_VALUE_NETWORK_PATH,
    FEATURE_NAMES,
    TrainingExample,
    ValueNetwork,
    extract_state_features,
    load_value_network,
    save_value_network,
)
from catan_engine.actions import IllegalActionError, Phase
from catan_engine.rules import apply_action, get_legal_actions, is_legal_action
from catan_engine.scoring import total_vp
from catan_engine.state import initialize_game

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINING_DIR = REPO_ROOT / "data" / "training"
DEFAULT_DATASET_PATH = TRAINING_DIR / "selfplay.jsonl"
DEFAULT_LEADERBOARD_PATH = TRAINING_DIR / "leaderboard.json"
DEFAULT_HISTORY_DIR = TRAINING_DIR / "checkpoints"
DEFAULT_LOG_PATH = TRAINING_DIR / "logs" / "train.out.log"
BOARD_RULE_VERSION = "random_start_balanced_board_random_ports_friendly_robber"
_LOG_FILE_PATH: Path | None = None

TRAINABLE_PHASES = {Phase.SETUP_SETTLEMENT, Phase.SETUP_ROAD, Phase.MOVE_ROBBER, Phase.MAIN}
PROFILE_DEFAULTS = {
    "quick": {
        "games": 1,
        "hidden_size": 32,
        "epochs": 1,
        "learning_rate": 0.02,
        "l2": 0.0001,
        "iterations": 1,
        "rollout_depth": 1,
        "branch_limit": 3,
        "max_turns": 120,
        "eval_games": 0,
        "buffer_samples": 0,
        "history_opponent_rate": 0.0,
        "history_opponents": 0,
    },
    "offline": {
        "games": 4,
        "hidden_size": 64,
        "epochs": 4,
        "learning_rate": 0.015,
        "l2": 0.0001,
        "iterations": 4,
        "rollout_depth": 4,
        "branch_limit": 6,
        "max_turns": 260,
        "eval_games": 2,
        "buffer_samples": 1000,
        "history_opponent_rate": 0.25,
        "history_opponents": 4,
    },
}


@dataclass
class RecordedPosition:
    features: list[float]
    player_id: int
    policy_target: str | None


@dataclass
class GameExamples:
    examples: list[TrainingExample]
    winner: int | None
    final_score: list[int]
    turn_count: int
    illegal_actions: int
    crashes: int


def _log_progress(enabled: bool, **payload: Any) -> None:
    if not enabled:
        return
    payload = {"time": int(time.time()), **payload}
    _emit_json(payload)


def _configure_log_file(path: Path | None) -> None:
    global _LOG_FILE_PATH
    _LOG_FILE_PATH = path
    if _LOG_FILE_PATH is not None:
        _LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _emit_json(payload: dict[str, Any]) -> None:
    payload = {"time": int(time.time()), **payload}
    line = json.dumps(payload, sort_keys=True)
    print(line, flush=True)
    if _LOG_FILE_PATH is not None:
        with _LOG_FILE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def train(
    *,
    games: int,
    seed: int,
    output: Path,
    hidden_size: int,
    epochs: int,
    learning_rate: float,
    l2: float,
    iterations: int,
    rollout_depth: int,
    branch_limit: int,
    max_turns: int,
    resume: bool,
    dataset_path: Path | None,
    buffer_samples: int,
    eval_games: int,
    history_dir: Path,
    leaderboard_path: Path,
    history_opponent_rate: float,
    history_opponents: int,
    accept_vp_margin: float,
    cycle: int | None = None,
    progress: bool = False,
) -> dict[str, Any]:
    rng = random.Random(seed)
    incumbent = load_value_network(output) if resume else None
    base_network = incumbent or ValueNetwork.create(len(FEATURE_NAMES), hidden_size, rng)
    history_networks = _load_history_networks(history_dir, limit=history_opponents)

    latest_examples: list[TrainingExample] = []
    illegal_actions = 0
    crashes = 0
    total_turns = 0
    wins = {0: 0, 1: 0, "draw": 0}

    for game_index in range(games):
        game_seed = seed + game_index
        _log_progress(
            progress,
            cycle=cycle,
            stage="selfplay",
            status="started",
            game=game_index + 1,
            games=games,
            seed=game_seed,
        )
        result = collect_game_examples(
            seed=game_seed,
            network=base_network,
            iterations=iterations,
            rollout_depth=rollout_depth,
            branch_limit=branch_limit,
            max_turns=max_turns,
            opponent_pool=history_networks,
            history_opponent_rate=history_opponent_rate,
        )
        latest_examples.extend(result.examples)
        illegal_actions += result.illegal_actions
        crashes += result.crashes
        total_turns += result.turn_count
        if result.winner in (0, 1):
            wins[result.winner] += 1
        else:
            wins["draw"] += 1
        if dataset_path is not None:
            _append_game_dataset(dataset_path, game_seed, result)
        _log_progress(
            progress,
            cycle=cycle,
            stage="selfplay",
            status="finished",
            game=game_index + 1,
            games=games,
            examples=len(result.examples),
            winner=result.winner,
            final_score=result.final_score,
            turn_count=result.turn_count,
            illegal_actions=result.illegal_actions,
            crashes=result.crashes,
        )

    buffer_examples = _load_replay_examples(dataset_path, rng, buffer_samples) if dataset_path is not None else []
    training_examples = latest_examples + buffer_examples

    candidate = ValueNetwork.from_dict(base_network.to_dict())
    _log_progress(
        progress,
        cycle=cycle,
        stage="sgd",
        status="started",
        latest_examples=len(latest_examples),
        buffer_examples=len(buffer_examples),
        total_examples=len(training_examples),
        epochs=epochs,
        learning_rate=learning_rate,
    )
    training_stats = candidate.train(
        training_examples,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
        rng=rng,
    )
    _log_progress(progress, cycle=cycle, stage="sgd", status="finished", **training_stats)

    _log_progress(progress, cycle=cycle, stage="evaluation", status="started", games=eval_games)
    evaluation = evaluate_candidate(
        candidate=candidate,
        current=incumbent,
        seed=seed + 500_000,
        games=eval_games,
        iterations=iterations,
        rollout_depth=rollout_depth,
        branch_limit=branch_limit,
        max_turns=max_turns,
    )
    _log_progress(progress, cycle=cycle, stage="evaluation", status="finished", evaluation=evaluation)
    _log_progress(
        progress,
        cycle=cycle,
        stage="history_evaluation",
        status="started",
        opponents=len(history_networks[:3]),
    )
    history_evaluations = _evaluate_history(
        candidate=candidate,
        history_networks=history_networks,
        seed=seed + 750_000,
        iterations=iterations,
        rollout_depth=rollout_depth,
        branch_limit=branch_limit,
        max_turns=max_turns,
    )
    _log_progress(
        progress,
        cycle=cycle,
        stage="history_evaluation",
        status="finished",
        evaluations=history_evaluations,
    )
    accepted = _should_accept_candidate(incumbent, evaluation, accept_vp_margin)
    network_to_save = candidate if accepted else base_network

    metadata = {
        "seed": seed,
        "games": games,
        "examples": len(training_examples),
        "latest_examples": len(latest_examples),
        "buffer_examples": len(buffer_examples),
        "hidden_size": network_to_save.hidden_size,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "l2": l2,
        "iterations": iterations,
        "rollout_depth": rollout_depth,
        "branch_limit": branch_limit,
        "max_turns": max_turns,
        "randomized_boards": True,
        "board_rule_version": BOARD_RULE_VERSION,
        "policy_head": True,
        "replay_dataset": str(dataset_path) if dataset_path is not None else None,
        "history_opponents": len(history_networks),
        "wins_by_player": {"0": wins[0], "1": wins[1], "draw": wins["draw"]},
        "average_turns": round(total_turns / games, 2) if games else 0.0,
        "illegal_actions": illegal_actions,
        "crashes": crashes,
        "accepted": accepted,
        "evaluation": evaluation,
        "history_evaluations": history_evaluations,
        **training_stats,
    }
    checkpoint = save_value_network(network_to_save, output, metadata=metadata)
    history_checkpoint = _save_history_checkpoint(candidate, history_dir, seed=seed, metadata=metadata) if accepted else None
    _update_leaderboard(
        leaderboard_path,
        {
            "time": int(time.time()),
            "checkpoint": str(history_checkpoint or checkpoint),
            "accepted": accepted,
            "score": _leaderboard_score(evaluation),
            "evaluation": evaluation,
            "examples": len(training_examples),
            "loss_after": metadata["loss_after"],
            "policy_loss_after": metadata.get("policy_loss_after", 0.0),
        },
    )
    _log_progress(
        progress,
        cycle=cycle,
        stage="checkpoint",
        status="saved",
        accepted=accepted,
        checkpoint=str(checkpoint),
        history_checkpoint=str(history_checkpoint) if history_checkpoint else None,
        wins_by_player=metadata["wins_by_player"],
    )
    return {"checkpoint": str(checkpoint), "history_checkpoint": str(history_checkpoint) if history_checkpoint else None, **metadata}


def train_continuously(
    *,
    games: int,
    seed: int,
    output: Path,
    hidden_size: int,
    epochs: int,
    learning_rate: float,
    l2: float,
    iterations: int,
    rollout_depth: int,
    branch_limit: int,
    max_turns: int,
    resume: bool,
    sleep_seconds: float,
    dataset_path: Path | None,
    buffer_samples: int,
    eval_games: int,
    history_dir: Path,
    leaderboard_path: Path,
    history_opponent_rate: float,
    history_opponents: int,
    accept_vp_margin: float,
) -> None:
    cycle = 0
    examples_total = 0
    try:
        while True:
            cycle += 1
            _emit_json(
                {
                    "cycle": cycle,
                    "status": "started",
                    "profile_games": games,
                    "iterations": iterations,
                    "rollout_depth": rollout_depth,
                    "branch_limit": branch_limit,
                    "eval_games": eval_games,
                }
            )
            summary = train(
                games=games,
                seed=seed + cycle * 1_000_000,
                output=output,
                hidden_size=hidden_size,
                epochs=epochs,
                learning_rate=learning_rate,
                l2=l2,
                iterations=iterations,
                rollout_depth=rollout_depth,
                branch_limit=branch_limit,
                max_turns=max_turns,
                resume=resume or cycle > 1,
                dataset_path=dataset_path,
                buffer_samples=buffer_samples,
                eval_games=eval_games,
                history_dir=history_dir,
                leaderboard_path=leaderboard_path,
                history_opponent_rate=history_opponent_rate,
                history_opponents=history_opponents,
                accept_vp_margin=accept_vp_margin,
                cycle=cycle,
                progress=True,
            )
            examples_total += int(summary["latest_examples"])
            _emit_json(
                {
                    "cycle": cycle,
                    "accepted": summary["accepted"],
                    "checkpoint": summary["checkpoint"],
                    "history_checkpoint": summary["history_checkpoint"],
                    "examples_total": examples_total,
                    "latest_examples": summary["latest_examples"],
                    "buffer_examples": summary["buffer_examples"],
                    "loss_before": summary["loss_before"],
                    "loss_after": summary["loss_after"],
                    "policy_loss_after": summary.get("policy_loss_after"),
                    "evaluation": summary["evaluation"],
                    "wins_by_player": summary["wins_by_player"],
                    "illegal_actions": summary["illegal_actions"],
                    "crashes": summary["crashes"],
                }
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        _emit_json({"stopped": True, "cycles": cycle, "examples_total": examples_total})


def collect_game_examples(
    *,
    seed: int,
    network: ValueNetwork,
    iterations: int,
    rollout_depth: int,
    branch_limit: int,
    max_turns: int,
    opponent_pool: list[ValueNetwork] | None = None,
    history_opponent_rate: float = 0.0,
) -> GameExamples:
    rng = random.Random(seed)
    state = initialize_game(seed=seed)
    networks: list[ValueNetwork] = [network, network]
    if opponent_pool and rng.random() < history_opponent_rate:
        history_player = rng.randrange(2)
        networks[history_player] = rng.choice(opponent_pool)
    bots = [
        MCTSBot(iterations=iterations, rollout_depth=rollout_depth, branch_limit=branch_limit, value_network=networks[0]),
        MCTSBot(iterations=iterations, rollout_depth=rollout_depth, branch_limit=branch_limit, value_network=networks[1]),
    ]
    positions: list[RecordedPosition] = []
    illegal_actions = 0
    crashes = 0
    max_actions = max_turns * 200
    action_count = 0

    while state.phase != Phase.GAME_OVER and state.turn_number <= max_turns and action_count <= max_actions:
        legal_actions = get_legal_actions(state)
        if not legal_actions:
            break
        player_id = state.current_player
        record_features = (
            extract_state_features(state, player_id)
            if state.phase in TRAINABLE_PHASES and networks[player_id] is network
            else None
        )
        try:
            observation = {"player_id": player_id, "phase": state.phase.name, "_state": state}
            action = bots[player_id].choose_action(observation, legal_actions, rng)
            if not is_legal_action(state, action):
                illegal_actions += 1
                action = rng.choice(legal_actions)
            if record_features is not None:
                positions.append(RecordedPosition(record_features, player_id, action.action_type.name))
            state = apply_action(state, action, rng)
        except Exception as exc:
            crashes += 1
            fallback = rng.choice(legal_actions)
            if record_features is not None:
                positions.append(RecordedPosition(record_features, player_id, fallback.action_type.name))
            try:
                state = apply_action(state, fallback, rng)
            except IllegalActionError:
                raise RuntimeError("fallback legal action failed") from exc
        action_count += 1

    final_score = [total_vp(state, 0), total_vp(state, 1)]
    winner = state.winner
    if state.phase != Phase.GAME_OVER:
        if final_score[0] > final_score[1]:
            winner = 0
        elif final_score[1] > final_score[0]:
            winner = 1
        else:
            winner = None

    examples: list[TrainingExample] = [
        (position.features, _target_for_position(winner, final_score, position.player_id), position.policy_target)
        for position in positions
    ]
    return GameExamples(
        examples=examples,
        winner=winner,
        final_score=final_score,
        turn_count=state.turn_number,
        illegal_actions=illegal_actions,
        crashes=crashes,
    )


def evaluate_candidate(
    *,
    candidate: ValueNetwork,
    current: ValueNetwork | None,
    seed: int,
    games: int,
    iterations: int,
    rollout_depth: int,
    branch_limit: int,
    max_turns: int,
) -> dict[str, Any]:
    if games <= 0:
        return {
            "games": 0,
            "candidate_wins": 0,
            "current_wins": 0,
            "draws": 0,
            "average_vp_margin": 0.0,
            "illegal_actions": 0,
            "crashes": 0,
            "average_turns": 0.0,
        }
    candidate_wins = 0
    current_wins = 0
    draws = 0
    illegal_actions = 0
    crashes = 0
    total_turns = 0
    total_margin = 0
    for game_index in range(games):
        candidate_player = game_index % 2
        result = _play_evaluation_game(
            seed=seed + game_index,
            candidate=candidate,
            current=current,
            candidate_player=candidate_player,
            iterations=iterations,
            rollout_depth=rollout_depth,
            branch_limit=branch_limit,
            max_turns=max_turns,
        )
        winner = result["winner"]
        if winner == candidate_player:
            candidate_wins += 1
        elif winner is None:
            draws += 1
        else:
            current_wins += 1
        score = result["final_score"]
        total_margin += score[candidate_player] - score[1 - candidate_player]
        illegal_actions += result["illegal_actions"]
        crashes += result["crashes"]
        total_turns += result["turn_count"]
    return {
        "games": games,
        "candidate_wins": candidate_wins,
        "current_wins": current_wins,
        "draws": draws,
        "average_vp_margin": round(total_margin / games, 3),
        "illegal_actions": illegal_actions,
        "crashes": crashes,
        "average_turns": round(total_turns / games, 2),
    }


def run_smoke(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    network = ValueNetwork.create(len(FEATURE_NAMES), 16, rng)
    for offset in range(5):
        initialize_game(seed=seed + offset).board.validate()
    result = collect_game_examples(
        seed=seed,
        network=network,
        iterations=1,
        rollout_depth=1,
        branch_limit=3,
        max_turns=80,
    )
    return {
        "boards_validated": 5,
        "examples": len(result.examples),
        "winner": result.winner,
        "final_score": result.final_score,
        "illegal_actions": result.illegal_actions,
        "crashes": result.crashes,
    }


def _play_evaluation_game(
    *,
    seed: int,
    candidate: ValueNetwork,
    current: ValueNetwork | None,
    candidate_player: int,
    iterations: int,
    rollout_depth: int,
    branch_limit: int,
    max_turns: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    state = initialize_game(seed=seed)
    bots = []
    for player_id in range(2):
        network = candidate if player_id == candidate_player else current
        bots.append(
            MCTSBot(
                iterations=iterations,
                rollout_depth=rollout_depth,
                branch_limit=branch_limit,
                value_network=network,
                use_value_network=network is not None,
            )
        )
    illegal_actions = 0
    crashes = 0
    max_actions = max_turns * 200
    action_count = 0
    while state.phase != Phase.GAME_OVER and state.turn_number <= max_turns and action_count <= max_actions:
        legal_actions = get_legal_actions(state)
        if not legal_actions:
            break
        player_id = state.current_player
        try:
            action = bots[player_id].choose_action({"player_id": player_id, "_state": state}, legal_actions, rng)
            if not is_legal_action(state, action):
                illegal_actions += 1
                action = rng.choice(legal_actions)
            state = apply_action(state, action, rng)
        except Exception:
            crashes += 1
            state = apply_action(state, rng.choice(legal_actions), rng)
        action_count += 1
    final_score = [total_vp(state, 0), total_vp(state, 1)]
    winner = state.winner
    if state.phase != Phase.GAME_OVER:
        if final_score[0] > final_score[1]:
            winner = 0
        elif final_score[1] > final_score[0]:
            winner = 1
        else:
            winner = None
    return {
        "winner": winner,
        "final_score": final_score,
        "turn_count": state.turn_number,
        "illegal_actions": illegal_actions,
        "crashes": crashes,
    }


def _target_for_position(winner: int | None, final_score: list[int], player_id: int) -> float:
    opponent_id = 1 - player_id
    if winner == player_id:
        return 1.0
    if winner == opponent_id:
        return 0.0
    margin = final_score[player_id] - final_score[opponent_id]
    return max(0.05, min(0.95, 0.5 + margin / 30.0))


def _should_accept_candidate(incumbent: ValueNetwork | None, evaluation: dict[str, Any], accept_vp_margin: float) -> bool:
    if incumbent is None or evaluation["games"] == 0:
        return True
    if evaluation["crashes"] > 0:
        return False
    if evaluation["candidate_wins"] > evaluation["current_wins"]:
        return True
    if evaluation["candidate_wins"] == evaluation["current_wins"]:
        return float(evaluation["average_vp_margin"]) >= accept_vp_margin
    return False


def _append_game_dataset(path: Path, seed: int, result: GameExamples) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "board_rule_version": BOARD_RULE_VERSION,
        "seed": seed,
        "winner": result.winner,
        "final_score": result.final_score,
        "turn_count": result.turn_count,
        "illegal_actions": result.illegal_actions,
        "crashes": result.crashes,
        "examples": [_example_to_json(example) for example in result.examples],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _example_to_json(example: TrainingExample) -> dict[str, Any]:
    features, target, policy_target = _unpack_example(example)
    return {"features": features, "target": target, "policy_target": policy_target}


def _load_replay_examples(path: Path, rng: random.Random, limit: int) -> list[TrainingExample]:
    if limit <= 0 or not path.exists():
        return []
    examples: list[TrainingExample] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get("board_rule_version") != BOARD_RULE_VERSION:
                    continue
                for item in payload.get("examples", []):
                    features = [float(value) for value in item.get("features", [])]
                    if len(features) != len(FEATURE_NAMES):
                        continue
                    examples.append((features, float(item.get("target", 0.5)), item.get("policy_target")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    if len(examples) <= limit:
        return examples
    return rng.sample(examples, limit)


def _unpack_example(example: TrainingExample) -> tuple[list[float], float, str | None]:
    if len(example) == 2:
        features, target = example
        return features, float(target), None
    features, target, policy_target = example
    return features, float(target), policy_target


def _load_history_networks(history_dir: Path, *, limit: int) -> list[ValueNetwork]:
    if limit <= 0 or not history_dir.exists():
        return []
    networks: list[ValueNetwork] = []
    for path in sorted(history_dir.glob("*.json"), reverse=True):
        if not _checkpoint_matches_board_rules(path):
            continue
        network = load_value_network(path)
        if network is not None:
            networks.append(network)
        if len(networks) >= limit:
            break
    return networks


def _checkpoint_matches_board_rules(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    training = data.get("training", {})
    return isinstance(training, dict) and training.get("board_rule_version") == BOARD_RULE_VERSION


def _save_history_checkpoint(network: ValueNetwork, history_dir: Path, *, seed: int, metadata: dict[str, Any]) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    target = history_dir / f"value_network_{int(time.time())}_{seed}.json"
    save_value_network(network, target, metadata=metadata)
    _trim_history(history_dir, keep=12)
    return target


def _trim_history(history_dir: Path, *, keep: int) -> None:
    checkpoints = sorted(history_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in checkpoints[keep:]:
        try:
            path.unlink()
        except OSError:
            pass


def _evaluate_history(
    *,
    candidate: ValueNetwork,
    history_networks: list[ValueNetwork],
    seed: int,
    iterations: int,
    rollout_depth: int,
    branch_limit: int,
    max_turns: int,
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for index, network in enumerate(history_networks[:3]):
        summary = evaluate_candidate(
            candidate=candidate,
            current=network,
            seed=seed + index * 100,
            games=1,
            iterations=iterations,
            rollout_depth=rollout_depth,
            branch_limit=branch_limit,
            max_turns=max_turns,
        )
        summary["history_index"] = index
        evaluations.append(summary)
    return evaluations


def _update_leaderboard(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(data, list):
            data = []
    except (OSError, json.JSONDecodeError):
        data = []
    data.append(entry)
    data = sorted(data, key=lambda item: int(item.get("time", 0)), reverse=True)[:20]
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _leaderboard_score(evaluation: dict[str, Any]) -> float:
    games = max(1, int(evaluation.get("games", 0)))
    win_delta = (int(evaluation.get("candidate_wins", 0)) - int(evaluation.get("current_wins", 0))) / games
    return round(win_delta + float(evaluation.get("average_vp_margin", 0.0)) / 15.0, 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the MCTS neural value/policy network from self-play.")
    parser.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="offline")
    parser.add_argument("--games", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=DEFAULT_VALUE_NETWORK_PATH)
    parser.add_argument("--hidden-size", type=int)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--l2", type=float)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--rollout-depth", type=int)
    parser.add_argument("--branch-limit", type=int)
    parser.add_argument("--max-turns", type=int)
    parser.add_argument("--eval-games", type=int)
    parser.add_argument("--buffer-samples", type=int)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--no-dataset", action="store_true", help="do not append or sample the self-play JSONL dataset")
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--leaderboard", type=Path, default=DEFAULT_LEADERBOARD_PATH)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_PATH, help="continuous-training JSON log path")
    parser.add_argument("--history-opponent-rate", type=float)
    parser.add_argument("--history-opponents", type=int)
    parser.add_argument("--accept-vp-margin", type=float, default=-0.25)
    parser.add_argument("--fresh", action="store_true", help="ignore the existing NN checkpoint and start a new network")
    parser.add_argument("--continuous", action="store_true", help="keep training and checkpointing until the process is stopped")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="pause between continuous training cycles")
    parser.add_argument("--evaluate-candidate", type=Path, help="evaluate this checkpoint against --output/current and exit")
    parser.add_argument("--smoke", action="store_true", help="run random-board plus MCTS-NN smoke checks and exit")
    args = parser.parse_args(argv)

    if args.smoke:
        print(json.dumps(run_smoke(args.seed), indent=2))
        return 0

    defaults = PROFILE_DEFAULTS[args.profile]
    settings = {
        "games": args.games if args.games is not None else defaults["games"],
        "hidden_size": args.hidden_size if args.hidden_size is not None else defaults["hidden_size"],
        "epochs": args.epochs if args.epochs is not None else defaults["epochs"],
        "learning_rate": args.learning_rate if args.learning_rate is not None else defaults["learning_rate"],
        "l2": args.l2 if args.l2 is not None else defaults["l2"],
        "iterations": args.iterations if args.iterations is not None else defaults["iterations"],
        "rollout_depth": args.rollout_depth if args.rollout_depth is not None else defaults["rollout_depth"],
        "branch_limit": args.branch_limit if args.branch_limit is not None else defaults["branch_limit"],
        "max_turns": args.max_turns if args.max_turns is not None else defaults["max_turns"],
        "eval_games": args.eval_games if args.eval_games is not None else defaults["eval_games"],
        "buffer_samples": args.buffer_samples if args.buffer_samples is not None else defaults["buffer_samples"],
        "history_opponent_rate": (
            args.history_opponent_rate
            if args.history_opponent_rate is not None
            else defaults["history_opponent_rate"]
        ),
        "history_opponents": args.history_opponents if args.history_opponents is not None else defaults["history_opponents"],
    }
    dataset_path = None if args.no_dataset else args.dataset

    if args.evaluate_candidate is not None:
        candidate = load_value_network(args.evaluate_candidate)
        if candidate is None:
            raise SystemExit(f"could not load candidate checkpoint: {args.evaluate_candidate}")
        current = load_value_network(args.output)
        summary = evaluate_candidate(
            candidate=candidate,
            current=current,
            seed=args.seed,
            games=settings["eval_games"] or 2,
            iterations=settings["iterations"],
            rollout_depth=settings["rollout_depth"],
            branch_limit=settings["branch_limit"],
            max_turns=settings["max_turns"],
        )
        print(json.dumps(summary, indent=2))
        return 0

    if args.continuous:
        _configure_log_file(args.log_file)
        train_continuously(
            seed=args.seed,
            output=args.output,
            resume=not args.fresh,
            sleep_seconds=args.sleep_seconds,
            dataset_path=dataset_path,
            history_dir=args.history_dir,
            leaderboard_path=args.leaderboard,
            accept_vp_margin=args.accept_vp_margin,
            **settings,
        )
        return 0

    summary = train(
        seed=args.seed,
        output=args.output,
        resume=not args.fresh,
        dataset_path=dataset_path,
        history_dir=args.history_dir,
        leaderboard_path=args.leaderboard,
        accept_vp_margin=args.accept_vp_margin,
        **settings,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
