from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from catan_bots.base import Bot
from catan_engine.actions import Action, ActionType, Phase
from catan_engine.resources import Resource
from catan_engine.rules import apply_action, can_place_settlement, get_legal_actions, maritime_trade_ratio
from catan_engine.scoring import calculate_longest_road, total_vp, visible_vp
from catan_engine.state import GameState


class MCTSBot(Bot):
    name = "mcts"

    def __init__(
        self,
        iterations: int = 18,
        rollout_depth: int = 22,
        exploration: float = 1.35,
        branch_limit: int = 10,
    ) -> None:
        self.iterations = iterations
        self.rollout_depth = rollout_depth
        self.exploration = exploration
        self.branch_limit = branch_limit

    def choose_action(self, observation: dict, legal_actions: list[Action], rng: random.Random) -> Action:
        if len(legal_actions) == 1:
            return legal_actions[0]

        state = observation.get("_state")
        if state is None and "state" in observation:
            state = GameState.from_dict(observation["state"])
        if state is None:
            return rng.choice(legal_actions)

        player_id = observation["player_id"]
        state = state.clone()
        state.action_log = []
        if state.phase == Phase.DISCARD:
            return _least_valuable_discard(legal_actions)
        if state.phase in {Phase.ROLL, Phase.STEAL}:
            return legal_actions[0]

        root_actions = _candidate_actions(state, player_id, legal_actions, self.branch_limit, rng)
        if len(root_actions) == 1:
            return root_actions[0]

        root = _Node(state=state.clone(), player_id=player_id, untried_actions=list(root_actions))
        for _ in range(self.iterations):
            node = root
            search_state = state.clone()

            while not node.untried_actions and node.children:
                node = node.select_child(self.exploration, rng)
                search_state = apply_action(search_state, node.action, rng)

            if node.untried_actions and search_state.phase != Phase.GAME_OVER:
                action = node.untried_actions.pop(rng.randrange(len(node.untried_actions)))
                search_state = apply_action(search_state, action, rng)
                child_actions = _candidate_actions(
                    search_state,
                    player_id,
                    get_legal_actions(search_state),
                    self.branch_limit,
                    rng,
                )
                node = node.add_child(action, search_state, child_actions)

            reward = _rollout(search_state, player_id, self.rollout_depth, self.branch_limit, rng)
            while node is not None:
                node.visits += 1
                node.value += reward
                node = node.parent

        return max(root.children, key=lambda child: (child.visits, child.value / max(1, child.visits))).action


@dataclass
class _Node:
    state: GameState
    player_id: int
    action: Action | None = None
    parent: _Node | None = None
    untried_actions: list[Action] = field(default_factory=list)
    children: list[_Node] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0

    def add_child(self, action: Action, state: GameState, actions: list[Action]) -> _Node:
        child = _Node(
            state=state.clone(),
            player_id=self.player_id,
            action=action,
            parent=self,
            untried_actions=list(actions),
        )
        self.children.append(child)
        return child

    def select_child(self, exploration: float, rng: random.Random) -> _Node:
        log_parent = math.log(max(1, self.visits))
        best_score = -float("inf")
        best_children: list[_Node] = []
        for child in self.children:
            if child.visits == 0:
                score = float("inf")
            else:
                exploit = child.value / child.visits
                explore = exploration * math.sqrt(log_parent / child.visits)
                score = exploit + explore
            if score > best_score:
                best_score = score
                best_children = [child]
            elif score == best_score:
                best_children.append(child)
        return rng.choice(best_children)


def _rollout(
    state: GameState,
    player_id: int,
    depth: int,
    branch_limit: int,
    rng: random.Random,
) -> float:
    current = state
    for _ in range(depth):
        if current.phase == Phase.GAME_OVER:
            break
        legal_actions = get_legal_actions(current)
        if not legal_actions:
            break
        if current.phase == Phase.DISCARD:
            action = _least_valuable_discard(legal_actions)
        elif current.phase in {Phase.ROLL, Phase.STEAL}:
            action = legal_actions[0]
        else:
            candidates = _candidate_actions(current, current.current_player, legal_actions, branch_limit, rng)
            action = max(candidates, key=lambda item: _action_value(current, current.current_player, item, rng))
        current = apply_action(current, action, rng)
    return _reward(current, player_id)


def _reward(state: GameState, player_id: int) -> float:
    opponent_id = state.opponent_id(player_id)
    if state.winner == player_id:
        return 1.0
    if state.winner == opponent_id:
        return 0.0
    delta = _evaluate_state(state, player_id) - _evaluate_state(state, opponent_id)
    return 1.0 / (1.0 + math.exp(-delta / 25.0))


def _candidate_actions(
    state: GameState,
    player_id: int,
    legal_actions: list[Action],
    branch_limit: int,
    rng: random.Random,
) -> list[Action]:
    if len(legal_actions) <= branch_limit:
        return legal_actions

    if state.phase == Phase.SETUP_SETTLEMENT:
        return sorted(legal_actions, key=lambda action: _node_score(state, action.payload["node_id"]), reverse=True)[:branch_limit]
    if state.phase == Phase.MOVE_ROBBER:
        return sorted(legal_actions, key=lambda action: _robber_score(state, player_id, action.payload["hex_id"]), reverse=True)[:branch_limit]

    priority_types = (
        ActionType.BUILD_CITY,
        ActionType.BUILD_SETTLEMENT,
        ActionType.PLAY_KNIGHT,
        ActionType.PLAY_MONOPOLY,
        ActionType.PLAY_YEAR_OF_PLENTY,
        ActionType.PLAY_ROAD_BUILDING,
        ActionType.BUY_DEV_CARD,
        ActionType.BUILD_ROAD,
        ActionType.MARITIME_TRADE,
        ActionType.END_TURN,
    )
    ordered: list[Action] = []
    for action_type in priority_types:
        typed = [action for action in legal_actions if action.action_type == action_type]
        if not typed:
            continue
        typed.sort(key=lambda action: _action_value(state, player_id, action, rng), reverse=True)
        ordered.extend(typed)
        if len(ordered) >= branch_limit:
            return ordered[:branch_limit]
    return legal_actions[:branch_limit]


def _action_value(state: GameState, player_id: int, action: Action, rng: random.Random) -> float:
    rng_state = rng.getstate()
    try:
        next_state = apply_action(state, action, rng)
    except Exception:
        return -float("inf")
    finally:
        rng.setstate(rng_state)
    return _evaluate_state(next_state, player_id)


def _evaluate_state(state: GameState, player_id: int) -> float:
    player = state.players[player_id]
    opponent_id = state.opponent_id(player_id)
    opponent = state.players[opponent_id]
    score = 18.0 * total_vp(state, player_id)
    score -= 13.0 * total_vp(state, opponent_id)
    score += 0.35 * player.total_resources()
    score -= 0.2 * opponent.total_resources()
    score += 1.2 * sum(1 for amount in player.resources.values() if amount > 0)
    score += _production_score(state, player_id)
    score += _port_score(state, player_id)
    score += 0.7 * _expansion_count(state, player_id)
    score += 0.9 * calculate_longest_road(state.board, state, player_id)
    score += 1.5 * player.played_knights
    score -= 1.1 * opponent.played_knights
    score += 0.7 * sum(player.dev_cards.values())
    score += 0.35 * sum(player.new_dev_cards.values())
    score -= 2.5 * max(0, visible_vp(state, opponent_id) - visible_vp(state, player_id))
    return score


def _production_score(state: GameState, player_id: int) -> float:
    weights = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
    score = 0.0
    player = state.players[player_id]
    for node_id in player.settlements | player.cities:
        multiplier = 2 if node_id in player.cities else 1
        score += multiplier * _node_score(state, node_id)
        for hex_id in state.board.get_hexes_for_node(node_id):
            hex_tile = state.board.hexes[hex_id]
            if hex_tile.hex_type.name in {"ORE", "GRAIN"} and hex_tile.number_token is not None:
                score += multiplier * weights.get(hex_tile.number_token, 0) * 0.25
    return score


def _node_score(state: GameState, node_id: int) -> float:
    weights = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
    score = 0.0
    resources: set[str] = set()
    for hex_id in state.board.get_hexes_for_node(node_id):
        hex_tile = state.board.hexes[hex_id]
        if hex_tile.number_token is None:
            continue
        score += weights.get(hex_tile.number_token, 0)
        resources.add(hex_tile.hex_type.name)
    port = state.board.nodes[node_id].port
    if port is not None:
        score += 1.5 if port.kind == "generic" else 2.0
    return score + 0.5 * len(resources)


def _port_score(state: GameState, player_id: int) -> float:
    score = 0.0
    for resource in Resource:
        ratio = maritime_trade_ratio(state, player_id, resource)
        if ratio == 2:
            score += 2.0
        elif ratio == 3:
            score += 0.8
    return score


def _expansion_count(state: GameState, player_id: int) -> int:
    return sum(
        1
        for node_id in state.board.nodes
        if can_place_settlement(state, node_id, setup=False, player_id=player_id)
    )


def _robber_score(state: GameState, player_id: int, hex_id: int) -> float:
    opponent_id = state.opponent_id(player_id)
    score = 0.0
    for node_id in state.board.get_nodes_for_hex(hex_id):
        if node_id in state.players[opponent_id].settlements:
            score += 2.0
        if node_id in state.players[opponent_id].cities:
            score += 4.0
        if node_id in state.players[player_id].settlements:
            score -= 2.0
        if node_id in state.players[player_id].cities:
            score -= 4.0
    return score


def _least_valuable_discard(legal_actions: list[Action]) -> Action:
    values = {"LUMBER": 0, "BRICK": 1, "WOOL": 2, "GRAIN": 3, "ORE": 4}
    return min(
        legal_actions,
        key=lambda action: sum(values[resource] * count for resource, count in action.payload["resources"].items()),
    )
