from __future__ import annotations

from catan_engine.scoring import visible_vp
from catan_engine.state import GameState


def is_friendly_robber_protected(state: GameState, player_id: int) -> bool:
    return state.config.friendly_robber and visible_vp(state, player_id) <= 2


def robber_blocks_player(state: GameState, player_id: int) -> bool:
    return not is_friendly_robber_protected(state, player_id)


def can_place_robber_on_hex(state: GameState, robber_hex_id: int, thief_id: int) -> bool:
    if robber_hex_id == state.board.robber_hex_id:
        return False
    occupied = state.occupied_nodes()
    for node_id in state.board.hexes[robber_hex_id].node_ids:
        owner = occupied.get(node_id)
        if owner is None:
            continue
        if is_friendly_robber_protected(state, owner):
            return False
    return True


def eligible_steal_targets(state: GameState, robber_hex_id: int, thief_id: int) -> list[int]:
    occupied = state.occupied_nodes()
    targets: set[int] = set()
    for node_id in state.board.hexes[robber_hex_id].node_ids:
        owner = occupied.get(node_id)
        if owner is None or owner == thief_id:
            continue
        if is_friendly_robber_protected(state, owner):
            continue
        if state.players[owner].total_resources() > 0:
            targets.add(owner)
    return sorted(targets)
