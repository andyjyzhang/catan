from __future__ import annotations

import random

from catan_engine.actions import Action, ActionType, IllegalActionError, Phase, action_key
from catan_engine.board import hex_resource
from catan_engine.dev_cards import DevCard
from catan_engine.dice import roll_dice
from catan_engine.resources import ALL_RESOURCES, HexType, Resource, normalize_resources
from catan_engine.robber import can_place_robber_on_hex, eligible_steal_targets, robber_blocks_player
from catan_engine.scoring import total_vp, update_awards, visible_vp
from catan_engine.state import GameState, PlayerState

ROAD_COST = {Resource.LUMBER: 1, Resource.BRICK: 1}
SETTLEMENT_COST = {Resource.LUMBER: 1, Resource.BRICK: 1, Resource.WOOL: 1, Resource.GRAIN: 1}
CITY_COST = {Resource.GRAIN: 2, Resource.ORE: 3}
DEV_CARD_COST = {Resource.WOOL: 1, Resource.GRAIN: 1, Resource.ORE: 1}
SETUP_PHASES = [
    Phase.SETUP_SETTLEMENT,
    Phase.SETUP_ROAD,
    Phase.SETUP_SETTLEMENT,
    Phase.SETUP_ROAD,
    Phase.SETUP_SETTLEMENT,
    Phase.SETUP_ROAD,
    Phase.SETUP_SETTLEMENT,
    Phase.SETUP_ROAD,
]


def get_legal_actions(state: GameState) -> list[Action]:
    if state.phase == Phase.GAME_OVER:
        return []
    if state.phase == Phase.SETUP_SETTLEMENT:
        return [
            Action(ActionType.PLACE_SETTLEMENT, state.current_player, {"node_id": node_id})
            for node_id in sorted(state.board.nodes)
            if can_place_settlement(state, node_id, setup=True, player_id=state.current_player)
        ]
    if state.phase == Phase.SETUP_ROAD:
        return _setup_road_actions(state)
    if state.phase == Phase.ROLL:
        return [Action(ActionType.ROLL_DICE, state.current_player)]
    if state.phase == Phase.DISCARD:
        return _discard_actions(state)
    if state.phase == Phase.MOVE_ROBBER:
        return [
            Action(ActionType.MOVE_ROBBER, state.current_player, {"hex_id": hex_id})
            for hex_id in sorted(state.board.hexes)
            if can_place_robber_on_hex(state, hex_id, state.current_player)
        ]
    if state.phase == Phase.STEAL:
        return [
            Action(ActionType.STEAL_RESOURCE, state.current_player, {"target_player": target})
            for target in state.legal_steal_targets
        ]
    if state.phase == Phase.MAIN:
        return _main_actions(state)
    raise ValueError(f"unknown phase {state.phase}")


def is_legal_action(state: GameState, action: Action) -> bool:
    legal_actions = get_legal_actions(state)
    legal_keys = {action_key(legal_action) for legal_action in legal_actions}
    if action_key(action) in legal_keys:
        return True
    if action.action_type == ActionType.ROLL_DICE:
        return any(item.action_type == ActionType.ROLL_DICE and item.player_id == action.player_id for item in legal_actions)
    if action.action_type == ActionType.STEAL_RESOURCE:
        return any(
            item.action_type == ActionType.STEAL_RESOURCE
            and item.player_id == action.player_id
            and item.payload["target_player"] == action.payload.get("target_player")
            for item in legal_actions
        )
    return False


def apply_action(state: GameState, action: Action, rng: random.Random | None = None) -> GameState:
    rng = rng or random.Random(state.rng_seed)
    if not is_legal_action(state, action):
        raise IllegalActionError(f"illegal action: {action}")
    new_state = state.clone()
    action = Action(action.action_type, action.player_id, dict(action.payload))

    if action.action_type == ActionType.PLACE_SETTLEMENT:
        _apply_place_settlement(new_state, action)
    elif action.action_type == ActionType.PLACE_ROAD:
        _apply_place_setup_road(new_state, action)
    elif action.action_type == ActionType.ROLL_DICE:
        _apply_roll_dice(new_state, action, rng)
    elif action.action_type == ActionType.DISCARD:
        _apply_discard(new_state, action)
    elif action.action_type == ActionType.MOVE_ROBBER:
        _apply_move_robber(new_state, action)
    elif action.action_type == ActionType.STEAL_RESOURCE:
        _apply_steal(new_state, action, rng)
    elif action.action_type == ActionType.BUILD_ROAD:
        _apply_build_road(new_state, action, free=new_state.pending_road_building > 0)
    elif action.action_type == ActionType.BUILD_SETTLEMENT:
        _apply_build_settlement(new_state, action)
    elif action.action_type == ActionType.BUILD_CITY:
        _apply_build_city(new_state, action)
    elif action.action_type == ActionType.BUY_DEV_CARD:
        _apply_buy_dev_card(new_state, action)
    elif action.action_type == ActionType.PLAY_KNIGHT:
        _apply_play_knight(new_state, action, rng)
    elif action.action_type == ActionType.PLAY_ROAD_BUILDING:
        _apply_play_road_building(new_state, action)
    elif action.action_type == ActionType.PLAY_YEAR_OF_PLENTY:
        _apply_play_year_of_plenty(new_state, action)
    elif action.action_type == ActionType.PLAY_MONOPOLY:
        _apply_play_monopoly(new_state, action)
    elif action.action_type == ActionType.MARITIME_TRADE:
        _apply_maritime_trade(new_state, action)
    elif action.action_type == ActionType.END_TURN:
        _apply_end_turn(new_state)
    else:
        raise ValueError(f"unhandled action {action.action_type}")

    new_state.action_log.append(action.to_dict())
    if new_state.phase != Phase.GAME_OVER:
        _maybe_win(new_state, action.player_id)
    return new_state


def can_place_settlement(state: GameState, node_id: int, *, setup: bool, player_id: int) -> bool:
    if node_id in state.occupied_nodes():
        return False
    for adjacent in state.board.get_adjacent_nodes(node_id):
        if adjacent in state.occupied_nodes():
            return False
    if setup:
        return True
    player = state.players[player_id]
    return any(edge_id in player.roads for edge_id in state.board.get_edges_for_node(node_id))


def can_build_road(state: GameState, player_id: int, edge_id: int) -> bool:
    if edge_id in state.occupied_edges():
        return False
    player = state.players[player_id]
    edge = state.board.edges[edge_id]
    occupied_nodes = state.occupied_nodes()
    for node_id in (edge.node_a, edge.node_b):
        owner = occupied_nodes.get(node_id)
        if owner == player_id:
            return True
        if owner is not None and owner != player_id:
            continue
        if any(adjacent_edge in player.roads for adjacent_edge in state.board.get_edges_for_node(node_id)):
            return True
    return False


def maritime_trade_ratio(state: GameState, player_id: int, resource: Resource) -> int:
    ratio = 4
    player = state.players[player_id]
    for node_id in player.settlements | player.cities:
        port = state.board.nodes[node_id].port
        if port is None:
            continue
        if port.kind == "generic":
            ratio = min(ratio, port.ratio)
        elif port.resource == resource:
            ratio = min(ratio, port.ratio)
    return ratio


def _setup_road_actions(state: GameState) -> list[Action]:
    if state.pending_setup_node is None:
        return []
    return [
        Action(ActionType.PLACE_ROAD, state.current_player, {"edge_id": edge_id})
        for edge_id in state.board.get_edges_for_node(state.pending_setup_node)
        if edge_id not in state.occupied_edges()
    ]


def _discard_actions(state: GameState) -> list[Action]:
    if not state.pending_discards:
        return []
    player_id = min(state.pending_discards)
    player = state.players[player_id]
    amount = player.total_resources() // 2
    return [
        Action(ActionType.DISCARD, player_id, {"resources": {resource.name: count for resource, count in combo.items() if count}})
        for combo in _discard_combinations(player, amount)
    ]


def _main_actions(state: GameState) -> list[Action]:
    if state.pending_road_building > 0:
        road_actions = _build_road_actions(state, free=True)
        if road_actions:
            return road_actions
        return [Action(ActionType.END_TURN, state.current_player)]

    actions: list[Action] = []
    actions.extend(_build_city_actions(state))
    actions.extend(_build_settlement_actions(state))
    actions.extend(_build_road_actions(state, free=False))
    actions.extend(_buy_dev_card_actions(state))
    actions.extend(_dev_card_actions(state))
    actions.extend(_maritime_trade_actions(state))
    actions.append(Action(ActionType.END_TURN, state.current_player))
    return actions


def _build_road_actions(state: GameState, *, free: bool) -> list[Action]:
    player = state.players[state.current_player]
    if player.roads_remaining <= 0:
        return []
    if not free and not player.has_resources(ROAD_COST):
        return []
    return [
        Action(ActionType.BUILD_ROAD, state.current_player, {"edge_id": edge_id})
        for edge_id in sorted(state.board.edges)
        if can_build_road(state, state.current_player, edge_id)
    ]


def _build_settlement_actions(state: GameState) -> list[Action]:
    player = state.players[state.current_player]
    if player.settlements_remaining <= 0 or not player.has_resources(SETTLEMENT_COST):
        return []
    return [
        Action(ActionType.BUILD_SETTLEMENT, state.current_player, {"node_id": node_id})
        for node_id in sorted(state.board.nodes)
        if can_place_settlement(state, node_id, setup=False, player_id=state.current_player)
    ]


def _build_city_actions(state: GameState) -> list[Action]:
    player = state.players[state.current_player]
    if player.cities_remaining <= 0 or not player.has_resources(CITY_COST):
        return []
    return [
        Action(ActionType.BUILD_CITY, state.current_player, {"node_id": node_id})
        for node_id in sorted(player.settlements)
    ]


def _buy_dev_card_actions(state: GameState) -> list[Action]:
    player = state.players[state.current_player]
    if state.dev_card_deck and player.has_resources(DEV_CARD_COST):
        return [Action(ActionType.BUY_DEV_CARD, state.current_player)]
    return []


def _dev_card_actions(state: GameState) -> list[Action]:
    player = state.players[state.current_player]
    if player.played_dev_card_this_turn:
        return []
    actions: list[Action] = []
    if player.dev_cards[DevCard.KNIGHT] > 0:
        for hex_id in sorted(state.board.hexes):
            if not can_place_robber_on_hex(state, hex_id, state.current_player):
                continue
            targets = eligible_steal_targets(state, hex_id, state.current_player)
            if targets:
                for target in targets:
                    actions.append(Action(ActionType.PLAY_KNIGHT, state.current_player, {"robber_hex_id": hex_id, "target_player": target}))
            else:
                actions.append(Action(ActionType.PLAY_KNIGHT, state.current_player, {"robber_hex_id": hex_id}))
    if player.dev_cards[DevCard.ROAD_BUILDING] > 0:
        actions.extend(_road_building_dev_actions(state))
    if player.dev_cards[DevCard.YEAR_OF_PLENTY] > 0:
        for first in ALL_RESOURCES:
            for second in ALL_RESOURCES:
                actions.append(Action(ActionType.PLAY_YEAR_OF_PLENTY, state.current_player, {"resources": [first.name, second.name]}))
    if player.dev_cards[DevCard.MONOPOLY] > 0:
        for resource in ALL_RESOURCES:
            actions.append(Action(ActionType.PLAY_MONOPOLY, state.current_player, {"resource": resource.name}))
    return actions


def _road_building_dev_actions(state: GameState) -> list[Action]:
    first_roads = [action.payload["edge_id"] for action in _build_road_actions(state, free=True)]
    actions = [Action(ActionType.PLAY_ROAD_BUILDING, state.current_player, {"edge_ids": [edge_id]}) for edge_id in first_roads]
    for first in first_roads:
        temp = state.clone()
        _place_road_piece(temp, state.current_player, first)
        second_roads = [action.payload["edge_id"] for action in _build_road_actions(temp, free=True)]
        for second in second_roads:
            if second != first:
                actions.append(Action(ActionType.PLAY_ROAD_BUILDING, state.current_player, {"edge_ids": [first, second]}))
    return actions


def _maritime_trade_actions(state: GameState) -> list[Action]:
    player = state.players[state.current_player]
    actions: list[Action] = []
    for give in ALL_RESOURCES:
        ratio = maritime_trade_ratio(state, state.current_player, give)
        if player.resources[give] < ratio:
            continue
        for receive in ALL_RESOURCES:
            if receive == give:
                continue
            actions.append(
                Action(
                    ActionType.MARITIME_TRADE,
                    state.current_player,
                    {"give": give.name, "give_count": ratio, "receive": receive.name},
                )
            )
    return actions


def _apply_place_settlement(state: GameState, action: Action) -> None:
    node_id = int(action.payload["node_id"])
    player = state.players[action.player_id]
    player.settlements.add(node_id)
    player.settlements_remaining -= 1
    state.pending_setup_node = node_id
    if state.setup_step in (4, 6):
        player.add_resources(_starting_resources(state, node_id))
    _advance_setup(state)


def _apply_place_setup_road(state: GameState, action: Action) -> None:
    _place_road_piece(state, action.player_id, int(action.payload["edge_id"]))
    state.pending_setup_node = None
    _advance_setup(state)


def _advance_setup(state: GameState) -> None:
    state.setup_step += 1
    setup_order = _setup_order(state.config.starting_player)
    if state.setup_step >= len(setup_order):
        state.current_player = state.config.starting_player
        state.phase = Phase.ROLL
        return
    state.current_player, state.phase = setup_order[state.setup_step]


def _setup_order(starting_player: int) -> list[tuple[int, Phase]]:
    first = int(starting_player)
    second = 1 - first
    players = [first, first, second, second, second, second, first, first]
    return list(zip(players, SETUP_PHASES, strict=True))


def _apply_roll_dice(state: GameState, action: Action, rng: random.Random) -> None:
    value = int(action.payload.get("roll", roll_dice(action.player_id, rng, balanced=state.config.balanced_dice, seven_history=state.seven_roll_history)))
    state.dice_roll = value
    if value == 7:
        state.seven_roll_history.append(action.player_id)
        state.pending_discards = {player_id for player_id, player in enumerate(state.players) if player.total_resources() > state.config.discard_limit}
        state.pending_robber_player = action.player_id
        if state.pending_discards:
            state.current_player = min(state.pending_discards)
            state.phase = Phase.DISCARD
        else:
            state.current_player = action.player_id
            state.phase = Phase.MOVE_ROBBER
        return
    _distribute_resources(state, value)
    state.phase = Phase.MAIN
    state.current_player = action.player_id


def _apply_discard(state: GameState, action: Action) -> None:
    resources = normalize_resources(action.payload["resources"])
    state.players[action.player_id].subtract_resources(resources)
    state.pending_discards.discard(action.player_id)
    if state.pending_discards:
        state.current_player = min(state.pending_discards)
    else:
        state.current_player = int(state.pending_robber_player)
        state.phase = Phase.MOVE_ROBBER


def _apply_move_robber(state: GameState, action: Action) -> None:
    hex_id = int(action.payload["hex_id"])
    state.board.robber_hex_id = hex_id
    state.pending_robber_player = None
    state.legal_steal_targets = eligible_steal_targets(state, hex_id, action.player_id)
    state.current_player = action.player_id
    state.phase = Phase.STEAL if state.legal_steal_targets else Phase.MAIN


def _apply_steal(state: GameState, action: Action, rng: random.Random) -> None:
    stolen = _steal_random_resource(state, action.player_id, int(action.payload["target_player"]), rng)
    if stolen is not None:
        action.payload["stolen_resource"] = stolen.name
    state.legal_steal_targets = []
    state.phase = Phase.MAIN


def _apply_build_road(state: GameState, action: Action, *, free: bool) -> None:
    if not free:
        state.players[action.player_id].subtract_resources(ROAD_COST)
    _place_road_piece(state, action.player_id, int(action.payload["edge_id"]))
    if state.pending_road_building:
        state.pending_road_building -= 1
    update_awards(state)


def _apply_build_settlement(state: GameState, action: Action) -> None:
    player = state.players[action.player_id]
    player.subtract_resources(SETTLEMENT_COST)
    player.settlements.add(int(action.payload["node_id"]))
    player.settlements_remaining -= 1
    update_awards(state)


def _apply_build_city(state: GameState, action: Action) -> None:
    node_id = int(action.payload["node_id"])
    player = state.players[action.player_id]
    player.subtract_resources(CITY_COST)
    player.settlements.remove(node_id)
    player.cities.add(node_id)
    player.settlements_remaining += 1
    player.cities_remaining -= 1


def _apply_buy_dev_card(state: GameState, action: Action) -> None:
    player = state.players[action.player_id]
    player.subtract_resources(DEV_CARD_COST)
    player.add_dev_card(state.dev_card_deck.pop(0), new=True)


def _apply_play_knight(state: GameState, action: Action, rng: random.Random) -> None:
    player = state.players[action.player_id]
    player.remove_dev_card(DevCard.KNIGHT)
    player.played_dev_card_this_turn = True
    player.played_knights += 1
    state.board.robber_hex_id = int(action.payload["robber_hex_id"])
    update_awards(state)
    target = action.payload.get("target_player")
    if target is not None:
        stolen = _steal_random_resource(state, action.player_id, int(target), rng)
        if stolen is not None:
            action.payload["stolen_resource"] = stolen.name
    state.phase = Phase.MAIN


def _apply_play_road_building(state: GameState, action: Action) -> None:
    player = state.players[action.player_id]
    player.remove_dev_card(DevCard.ROAD_BUILDING)
    player.played_dev_card_this_turn = True
    for edge_id in action.payload.get("edge_ids", [])[:2]:
        _place_road_piece(state, action.player_id, int(edge_id))
    update_awards(state)


def _apply_play_year_of_plenty(state: GameState, action: Action) -> None:
    player = state.players[action.player_id]
    player.remove_dev_card(DevCard.YEAR_OF_PLENTY)
    player.played_dev_card_this_turn = True
    for resource_name in action.payload["resources"][:2]:
        player.resources[Resource[str(resource_name)]] += 1


def _apply_play_monopoly(state: GameState, action: Action) -> None:
    resource = Resource[str(action.payload["resource"])]
    player = state.players[action.player_id]
    opponent = state.players[state.opponent_id(action.player_id)]
    player.remove_dev_card(DevCard.MONOPOLY)
    player.played_dev_card_this_turn = True
    amount = opponent.resources[resource]
    opponent.resources[resource] = 0
    player.resources[resource] += amount


def _apply_maritime_trade(state: GameState, action: Action) -> None:
    give = Resource[str(action.payload["give"])]
    receive = Resource[str(action.payload["receive"])]
    give_count = int(action.payload["give_count"])
    player = state.players[action.player_id]
    player.subtract_resources({give: give_count})
    player.resources[receive] += 1


def _apply_end_turn(state: GameState) -> None:
    player = state.players[state.current_player]
    for card, amount in player.new_dev_cards.items():
        player.dev_cards[card] += amount
        player.new_dev_cards[card] = 0
    player.played_dev_card_this_turn = False
    state.current_player = state.opponent_id(state.current_player)
    state.turn_number += 1
    state.phase = Phase.ROLL
    state.dice_roll = None
    state.pending_road_building = 0


def _place_road_piece(state: GameState, player_id: int, edge_id: int) -> None:
    player = state.players[player_id]
    player.roads.add(edge_id)
    player.roads_remaining -= 1


def _starting_resources(state: GameState, node_id: int) -> dict[Resource, int]:
    resources: dict[Resource, int] = {}
    for hex_id in state.board.get_hexes_for_node(node_id):
        resource = hex_resource(state.board.hexes[hex_id].hex_type)
        if resource is not None:
            resources[resource] = resources.get(resource, 0) + 1
    return resources


def _distribute_resources(state: GameState, roll_value: int) -> None:
    for hex_tile in state.board.hexes.values():
        if hex_tile.number_token != roll_value or hex_tile.hex_type == HexType.DESERT:
            continue
        resource = hex_resource(hex_tile.hex_type)
        if resource is None:
            continue
        for player_id, player in enumerate(state.players):
            if hex_tile.id == state.board.robber_hex_id and robber_blocks_player(state, player_id):
                continue
            amount = 0
            for node_id in hex_tile.node_ids:
                if node_id in player.settlements:
                    amount += 1
                if node_id in player.cities:
                    amount += 2
            if amount:
                player.resources[resource] += amount


def _discard_combinations(player: PlayerState, amount: int) -> list[dict[Resource, int]]:
    combos: list[dict[Resource, int]] = []
    current: dict[Resource, int] = {}

    def search(index: int, remaining: int) -> None:
        if index == len(ALL_RESOURCES):
            if remaining == 0:
                combos.append(dict(current))
            return
        resource = ALL_RESOURCES[index]
        for count in range(min(player.resources[resource], remaining) + 1):
            current[resource] = count
            search(index + 1, remaining - count)
        current.pop(resource, None)

    search(0, amount)
    return combos


def _steal_random_resource(state: GameState, thief_id: int, target_id: int, rng: random.Random) -> Resource | None:
    target = state.players[target_id]
    pool = [resource for resource in ALL_RESOURCES for _ in range(target.resources[resource])]
    if not pool:
        return None
    resource = rng.choice(pool)
    target.resources[resource] -= 1
    state.players[thief_id].resources[resource] += 1
    return resource


def _maybe_win(state: GameState, player_id: int) -> None:
    if total_vp(state, player_id) >= state.config.target_vp:
        state.phase = Phase.GAME_OVER
        state.winner = player_id
