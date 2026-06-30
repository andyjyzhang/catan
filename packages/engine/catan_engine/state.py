from __future__ import annotations

import random
from dataclasses import dataclass, field

from catan_engine.actions import Phase
from catan_engine.board import Board, create_standard_board
from catan_engine.dev_cards import DevCard, dev_cards_to_json, normalize_dev_cards, shuffled_dev_card_deck
from catan_engine.resources import Resource, normalize_resources, resource_dict_from_json, resource_dict_to_json


@dataclass
class GameConfig:
    target_vp: int = 15
    discard_limit: int = 9
    friendly_robber: bool = True
    balanced_dice: bool = False
    starting_player: int = 0

    def to_dict(self) -> dict:
        return {
            "target_vp": self.target_vp,
            "discard_limit": self.discard_limit,
            "friendly_robber": self.friendly_robber,
            "balanced_dice": self.balanced_dice,
            "starting_player": self.starting_player,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> GameConfig:
        if data is None:
            return cls()
        return cls(
            target_vp=int(data.get("target_vp", 15)),
            discard_limit=int(data.get("discard_limit", 9)),
            friendly_robber=bool(data.get("friendly_robber", True)),
            balanced_dice=bool(data.get("balanced_dice", False)),
            starting_player=int(data.get("starting_player", 0)),
        )


@dataclass
class PlayerState:
    resources: dict[Resource, int] = field(default_factory=normalize_resources)
    dev_cards: dict[DevCard, int] = field(default_factory=normalize_dev_cards)
    new_dev_cards: dict[DevCard, int] = field(default_factory=normalize_dev_cards)
    played_dev_card_this_turn: bool = False
    settlements: set[int] = field(default_factory=set)
    cities: set[int] = field(default_factory=set)
    roads: set[int] = field(default_factory=set)
    played_knights: int = 0
    roads_remaining: int = 15
    settlements_remaining: int = 5
    cities_remaining: int = 4

    def __post_init__(self) -> None:
        self.resources = normalize_resources(self.resources)
        self.dev_cards = normalize_dev_cards(self.dev_cards)
        self.new_dev_cards = normalize_dev_cards(self.new_dev_cards)
        self.settlements = set(self.settlements)
        self.cities = set(self.cities)
        self.roads = set(self.roads)

    def has_resources(self, cost: dict[Resource, int]) -> bool:
        return all(self.resources.get(resource, 0) >= amount for resource, amount in cost.items())

    def add_resources(self, delta: dict[Resource, int]) -> None:
        for resource, amount in normalize_resources(delta).items():
            self.resources[resource] += amount

    def subtract_resources(self, cost: dict[Resource, int]) -> None:
        if not self.has_resources(cost):
            raise ValueError("insufficient resources")
        for resource, amount in normalize_resources(cost).items():
            self.resources[resource] -= amount

    def total_resources(self) -> int:
        return sum(self.resources.values())

    def clone(self) -> PlayerState:
        return PlayerState(
            resources=dict(self.resources),
            dev_cards=dict(self.dev_cards),
            new_dev_cards=dict(self.new_dev_cards),
            played_dev_card_this_turn=self.played_dev_card_this_turn,
            settlements=set(self.settlements),
            cities=set(self.cities),
            roads=set(self.roads),
            played_knights=self.played_knights,
            roads_remaining=self.roads_remaining,
            settlements_remaining=self.settlements_remaining,
            cities_remaining=self.cities_remaining,
        )

    def add_dev_card(self, card: DevCard, *, new: bool) -> None:
        target = self.new_dev_cards if new else self.dev_cards
        target[card] += 1

    def remove_dev_card(self, card: DevCard) -> None:
        if self.dev_cards.get(card, 0) <= 0:
            raise ValueError(f"no playable {card.name} card")
        self.dev_cards[card] -= 1

    def hidden_vp_cards(self) -> int:
        return self.dev_cards[DevCard.VICTORY_POINT] + self.new_dev_cards[DevCard.VICTORY_POINT]

    def to_dict(self) -> dict:
        return {
            "resources": resource_dict_to_json(self.resources),
            "dev_cards": dev_cards_to_json(self.dev_cards),
            "new_dev_cards": dev_cards_to_json(self.new_dev_cards),
            "played_dev_card_this_turn": self.played_dev_card_this_turn,
            "settlements": sorted(self.settlements),
            "cities": sorted(self.cities),
            "roads": sorted(self.roads),
            "played_knights": self.played_knights,
            "roads_remaining": self.roads_remaining,
            "settlements_remaining": self.settlements_remaining,
            "cities_remaining": self.cities_remaining,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlayerState:
        return cls(
            resources=resource_dict_from_json(data.get("resources")),
            dev_cards=normalize_dev_cards(data.get("dev_cards")),
            new_dev_cards=normalize_dev_cards(data.get("new_dev_cards")),
            played_dev_card_this_turn=bool(data.get("played_dev_card_this_turn", False)),
            settlements=set(int(item) for item in data.get("settlements", [])),
            cities=set(int(item) for item in data.get("cities", [])),
            roads=set(int(item) for item in data.get("roads", [])),
            played_knights=int(data.get("played_knights", 0)),
            roads_remaining=int(data.get("roads_remaining", 15)),
            settlements_remaining=int(data.get("settlements_remaining", 5)),
            cities_remaining=int(data.get("cities_remaining", 4)),
        )


@dataclass
class GameState:
    board: Board
    config: GameConfig
    players: list[PlayerState]
    current_player: int
    phase: Phase
    turn_number: int
    setup_step: int
    dice_roll: int | None
    pending_discards: set[int]
    pending_robber_player: int | None
    legal_steal_targets: list[int]
    longest_road_owner: int | None
    largest_army_owner: int | None
    winner: int | None
    dev_card_deck: list[DevCard]
    action_log: list[dict]
    rng_seed: int
    pending_setup_node: int | None = None
    pending_road_building: int = 0
    seven_roll_history: list[int] = field(default_factory=list)

    def clone(self) -> GameState:
        board = Board(
            hexes=self.board.hexes,
            nodes=self.board.nodes,
            edges=self.board.edges,
            robber_hex_id=self.board.robber_hex_id,
        )
        return GameState(
            board=board,
            config=GameConfig.from_dict(self.config.to_dict()),
            players=[player.clone() for player in self.players],
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            setup_step=self.setup_step,
            dice_roll=self.dice_roll,
            pending_discards=set(self.pending_discards),
            pending_robber_player=self.pending_robber_player,
            legal_steal_targets=list(self.legal_steal_targets),
            longest_road_owner=self.longest_road_owner,
            largest_army_owner=self.largest_army_owner,
            winner=self.winner,
            dev_card_deck=list(self.dev_card_deck),
            action_log=list(self.action_log),
            rng_seed=self.rng_seed,
            pending_setup_node=self.pending_setup_node,
            pending_road_building=self.pending_road_building,
            seven_roll_history=list(self.seven_roll_history),
        )

    def current_player_state(self) -> PlayerState:
        return self.players[self.current_player]

    def opponent_id(self, player_id: int) -> int:
        return 1 - player_id

    def hand_size(self, player_id: int) -> int:
        return self.players[player_id].total_resources()

    def occupied_nodes(self) -> dict[int, int]:
        occupied: dict[int, int] = {}
        for player_id, player in enumerate(self.players):
            for node_id in player.settlements | player.cities:
                occupied[node_id] = player_id
        return occupied

    def occupied_edges(self) -> dict[int, int]:
        occupied: dict[int, int] = {}
        for player_id, player in enumerate(self.players):
            for edge_id in player.roads:
                occupied[edge_id] = player_id
        return occupied

    def to_dict(self) -> dict:
        return {
            "board": self.board.to_dict(),
            "config": self.config.to_dict(),
            "players": [player.to_dict() for player in self.players],
            "current_player": self.current_player,
            "phase": self.phase.name,
            "turn_number": self.turn_number,
            "setup_step": self.setup_step,
            "dice_roll": self.dice_roll,
            "pending_discards": sorted(self.pending_discards),
            "pending_robber_player": self.pending_robber_player,
            "legal_steal_targets": list(self.legal_steal_targets),
            "longest_road_owner": self.longest_road_owner,
            "largest_army_owner": self.largest_army_owner,
            "winner": self.winner,
            "dev_card_deck": [card.name for card in self.dev_card_deck],
            "action_log": list(self.action_log),
            "rng_seed": self.rng_seed,
            "pending_setup_node": self.pending_setup_node,
            "pending_road_building": self.pending_road_building,
            "seven_roll_history": list(self.seven_roll_history),
        }

    @classmethod
    def from_dict(cls, data: dict) -> GameState:
        return cls(
            board=Board.from_dict(data["board"]),
            config=GameConfig.from_dict(data.get("config")),
            players=[PlayerState.from_dict(player) for player in data["players"]],
            current_player=int(data["current_player"]),
            phase=Phase[data["phase"]],
            turn_number=int(data["turn_number"]),
            setup_step=int(data["setup_step"]),
            dice_roll=data.get("dice_roll"),
            pending_discards=set(int(item) for item in data.get("pending_discards", [])),
            pending_robber_player=data.get("pending_robber_player"),
            legal_steal_targets=[int(item) for item in data.get("legal_steal_targets", [])],
            longest_road_owner=data.get("longest_road_owner"),
            largest_army_owner=data.get("largest_army_owner"),
            winner=data.get("winner"),
            dev_card_deck=[DevCard[item] for item in data.get("dev_card_deck", [])],
            action_log=list(data.get("action_log", [])),
            rng_seed=int(data.get("rng_seed", 0)),
            pending_setup_node=data.get("pending_setup_node"),
            pending_road_building=int(data.get("pending_road_building", 0)),
            seven_roll_history=[int(item) for item in data.get("seven_roll_history", [])],
        )


def initialize_game(config: GameConfig | None = None, seed: int = 0) -> GameState:
    rng = random.Random(seed)
    config = config or GameConfig(starting_player=rng.randrange(2))
    board = create_standard_board(seed=seed)
    return GameState(
        board=board,
        config=config,
        players=[PlayerState(), PlayerState()],
        current_player=config.starting_player,
        phase=Phase.SETUP_SETTLEMENT,
        turn_number=1,
        setup_step=0,
        dice_roll=None,
        pending_discards=set(),
        pending_robber_player=None,
        legal_steal_targets=[],
        longest_road_owner=None,
        largest_army_owner=None,
        winner=None,
        dev_card_deck=shuffled_dev_card_deck(rng),
        action_log=[],
        rng_seed=seed,
    )
