from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass

from catan_engine.resources import HEX_TO_RESOURCE, HexType, Resource

STANDARD_RESOURCE_TYPES = [
    HexType.LUMBER,
    HexType.LUMBER,
    HexType.LUMBER,
    HexType.LUMBER,
    HexType.BRICK,
    HexType.BRICK,
    HexType.BRICK,
    HexType.WOOL,
    HexType.WOOL,
    HexType.WOOL,
    HexType.WOOL,
    HexType.GRAIN,
    HexType.GRAIN,
    HexType.GRAIN,
    HexType.GRAIN,
    HexType.ORE,
    HexType.ORE,
    HexType.ORE,
    HexType.DESERT,
]
STANDARD_NUMBER_TOKENS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
RED_NUMBER_TOKENS = {6, 8}


@dataclass
class Port:
    kind: str
    resource: Resource | None
    ratio: int

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "resource": self.resource.name if self.resource else None,
            "ratio": self.ratio,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> Port | None:
        if data is None:
            return None
        resource = Resource[data["resource"]] if data.get("resource") else None
        return cls(kind=data["kind"], resource=resource, ratio=int(data["ratio"]))


@dataclass
class Hex:
    id: int
    hex_type: HexType
    number_token: int | None
    node_ids: tuple[int, ...]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hex_type": self.hex_type.name,
            "number_token": self.number_token,
            "node_ids": list(self.node_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Hex:
        return cls(
            id=int(data["id"]),
            hex_type=HexType[data["hex_type"]],
            number_token=data.get("number_token"),
            node_ids=tuple(int(node_id) for node_id in data["node_ids"]),
        )


@dataclass
class Node:
    id: int
    hex_ids: tuple[int, ...]
    edge_ids: tuple[int, ...]
    port: Port | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hex_ids": list(self.hex_ids),
            "edge_ids": list(self.edge_ids),
            "port": self.port.to_dict() if self.port else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        return cls(
            id=int(data["id"]),
            hex_ids=tuple(int(hex_id) for hex_id in data["hex_ids"]),
            edge_ids=tuple(int(edge_id) for edge_id in data["edge_ids"]),
            port=Port.from_dict(data.get("port")),
        )


@dataclass
class Edge:
    id: int
    node_a: int
    node_b: int
    hex_ids: tuple[int, ...]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "node_a": self.node_a,
            "node_b": self.node_b,
            "hex_ids": list(self.hex_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Edge:
        return cls(
            id=int(data["id"]),
            node_a=int(data["node_a"]),
            node_b=int(data["node_b"]),
            hex_ids=tuple(int(hex_id) for hex_id in data["hex_ids"]),
        )


@dataclass
class Board:
    hexes: dict[int, Hex]
    nodes: dict[int, Node]
    edges: dict[int, Edge]
    robber_hex_id: int

    def get_adjacent_nodes(self, node_id: int) -> tuple[int, ...]:
        return tuple(self.get_opposite_node(edge_id, node_id) for edge_id in self.nodes[node_id].edge_ids)

    def get_adjacent_edges(self, node_id: int) -> tuple[int, ...]:
        return self.nodes[node_id].edge_ids

    def get_edge_between(self, node_a: int, node_b: int) -> int | None:
        wanted = {node_a, node_b}
        for edge_id in self.nodes[node_a].edge_ids:
            edge = self.edges[edge_id]
            if {edge.node_a, edge.node_b} == wanted:
                return edge_id
        return None

    def get_nodes_for_hex(self, hex_id: int) -> tuple[int, ...]:
        return self.hexes[hex_id].node_ids

    def get_hexes_for_node(self, node_id: int) -> tuple[int, ...]:
        return self.nodes[node_id].hex_ids

    def get_edges_for_node(self, node_id: int) -> tuple[int, ...]:
        return self.nodes[node_id].edge_ids

    def get_opposite_node(self, edge_id: int, node_id: int) -> int:
        edge = self.edges[edge_id]
        if edge.node_a == node_id:
            return edge.node_b
        if edge.node_b == node_id:
            return edge.node_a
        raise ValueError(f"node {node_id} is not on edge {edge_id}")

    def validate(self) -> None:
        if self.robber_hex_id not in self.hexes:
            raise ValueError("robber hex does not exist")
        if self.hexes[self.robber_hex_id].hex_type != HexType.DESERT:
            raise ValueError("robber must start on desert")
        if len(self.hexes) != 19:
            raise ValueError("standard board must have 19 hexes")
        if len(self.nodes) != 54:
            raise ValueError("standard board must have 54 nodes")
        if len(self.edges) != 72:
            raise ValueError("standard board must have 72 edges")

        for edge in self.edges.values():
            if edge.node_a not in self.nodes or edge.node_b not in self.nodes:
                raise ValueError(f"edge {edge.id} references missing endpoint")
            if edge.id not in self.nodes[edge.node_a].edge_ids or edge.id not in self.nodes[edge.node_b].edge_ids:
                raise ValueError(f"edge {edge.id} missing symmetric node reference")
            for hex_id in edge.hex_ids:
                if hex_id not in self.hexes:
                    raise ValueError(f"edge {edge.id} references missing hex")

        for node in self.nodes.values():
            for edge_id in node.edge_ids:
                if edge_id not in self.edges:
                    raise ValueError(f"node {node.id} references missing edge")
                edge = self.edges[edge_id]
                if node.id not in (edge.node_a, edge.node_b):
                    raise ValueError(f"node {node.id} has asymmetric edge {edge_id}")
            for hex_id in node.hex_ids:
                if hex_id not in self.hexes:
                    raise ValueError(f"node {node.id} references missing hex")
                if node.id not in self.hexes[hex_id].node_ids:
                    raise ValueError(f"node {node.id} has asymmetric hex {hex_id}")

        for hex_tile in self.hexes.values():
            if len(hex_tile.node_ids) != 6:
                raise ValueError(f"hex {hex_tile.id} does not have six nodes")
            for node_id in hex_tile.node_ids:
                if node_id not in self.nodes:
                    raise ValueError(f"hex {hex_tile.id} references missing node")
                if hex_tile.id not in self.nodes[node_id].hex_ids:
                    raise ValueError(f"hex {hex_tile.id} has asymmetric node {node_id}")

        self._validate_standard_catan_setup()

    def _validate_standard_catan_setup(self) -> None:
        resource_counts = Counter(hex_tile.hex_type for hex_tile in self.hexes.values())
        expected_resource_counts = Counter(STANDARD_RESOURCE_TYPES)
        if resource_counts != expected_resource_counts:
            raise ValueError(f"invalid resource distribution: {resource_counts}")

        number_counts = Counter(
            hex_tile.number_token
            for hex_tile in self.hexes.values()
            if hex_tile.hex_type != HexType.DESERT
        )
        expected_number_counts = Counter(STANDARD_NUMBER_TOKENS)
        if number_counts != expected_number_counts:
            raise ValueError(f"invalid number token distribution: {number_counts}")

        desert_hexes = [hex_tile for hex_tile in self.hexes.values() if hex_tile.hex_type == HexType.DESERT]
        if len(desert_hexes) != 1:
            raise ValueError("standard board must have one desert")
        if desert_hexes[0].number_token is not None:
            raise ValueError("desert must not have a number token")
        if self.robber_hex_id != desert_hexes[0].id:
            raise ValueError("robber must start on the desert")

        for hex_tile in self.hexes.values():
            if hex_tile.hex_type != HexType.DESERT and hex_tile.number_token is None:
                raise ValueError(f"non-desert hex {hex_tile.id} is missing a number token")

        for left in self.hexes.values():
            if left.number_token is None:
                continue
            for right in self.hexes.values():
                if left.id >= right.id or right.number_token is None:
                    continue
                if len(set(left.node_ids).intersection(right.node_ids)) == 2:
                    if left.number_token == right.number_token:
                        raise ValueError("matching number tokens must not be adjacent")
                    if left.number_token in RED_NUMBER_TOKENS and right.number_token in RED_NUMBER_TOKENS:
                        raise ValueError("red number tokens must not be adjacent")

        port_nodes = [node for node in self.nodes.values() if node.port is not None]
        if len(port_nodes) != 18:
            raise ValueError("standard board must have 18 port nodes")
        generic_ports = [node for node in port_nodes if node.port and node.port.kind == "generic" and node.port.ratio == 3]
        if len(generic_ports) != 8:
            raise ValueError("standard board must have four generic 3:1 ports")
        for resource in Resource:
            resource_ports = [
                node
                for node in port_nodes
                if node.port and node.port.kind == "resource" and node.port.ratio == 2 and node.port.resource == resource
            ]
            if len(resource_ports) != 2:
                raise ValueError(f"standard board must have one {resource.name} 2:1 port")

    def to_dict(self) -> dict:
        return {
            "hexes": {str(key): hex_tile.to_dict() for key, hex_tile in self.hexes.items()},
            "nodes": {str(key): node.to_dict() for key, node in self.nodes.items()},
            "edges": {str(key): edge.to_dict() for key, edge in self.edges.items()},
            "robber_hex_id": self.robber_hex_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Board:
        return cls(
            hexes={int(key): Hex.from_dict(value) for key, value in data["hexes"].items()},
            nodes={int(key): Node.from_dict(value) for key, value in data["nodes"].items()},
            edges={int(key): Edge.from_dict(value) for key, value in data["edges"].items()},
            robber_hex_id=int(data["robber_hex_id"]),
        )

    @classmethod
    def create_standard_board(cls, seed: int | None = None) -> Board:
        return create_standard_board(seed=seed)


def create_standard_board(seed: int | None = None) -> Board:
    rng = random.Random(seed)
    coords = [
        (q, r)
        for q in range(-2, 3)
        for r in range(-2, 3)
        if max(abs(q), abs(r), abs(-q - r)) <= 2
    ]
    coords.sort(key=lambda item: (item[1], item[0]))

    fixed_resource_types = [
        HexType.LUMBER,
        HexType.BRICK,
        HexType.WOOL,
        HexType.WOOL,
        HexType.DESERT,
        HexType.ORE,
        HexType.BRICK,
        HexType.WOOL,
        HexType.GRAIN,
        HexType.LUMBER,
        HexType.ORE,
        HexType.ORE,
        HexType.LUMBER,
        HexType.WOOL,
        HexType.BRICK,
        HexType.GRAIN,
        HexType.LUMBER,
        HexType.GRAIN,
        HexType.GRAIN,
    ]
    fixed_number_tokens = [4, 8, 10, 3, 4, 12, 6, 10, 5, 11, 6, 9, 8, 2, 3, 11, 9, 5]
    if seed is None:
        hex_specs = _hex_specs_from_layout(coords, fixed_resource_types, fixed_number_tokens)
    else:
        hex_specs = _random_valid_hex_specs(coords, rng)
    robber_hex_id = next(index for index, (_q, _r, hex_type, _number) in enumerate(hex_specs) if hex_type == HexType.DESERT)

    corner_keys: dict[tuple[float, float], int] = {}
    hex_corner_keys: list[tuple[tuple[float, float], ...]] = []
    for q, r, _hex_type, _number in hex_specs:
        cx, cy = _hex_center(q, r)
        keys: list[tuple[float, float]] = []
        for corner in range(6):
            angle = math.radians(60 * corner - 30)
            key = (round(cx + math.cos(angle), 6), round(cy + math.sin(angle), 6))
            keys.append(key)
            corner_keys.setdefault(key, -1)
        hex_corner_keys.append(tuple(keys))

    sorted_corners = sorted(corner_keys)
    node_id_by_key = {key: index for index, key in enumerate(sorted_corners)}
    hex_node_ids = [tuple(node_id_by_key[key] for key in keys) for keys in hex_corner_keys]

    edge_hexes: dict[tuple[int, int], list[int]] = {}
    for hex_id, node_ids in enumerate(hex_node_ids):
        for index, node_id in enumerate(node_ids):
            other = node_ids[(index + 1) % 6]
            edge_hexes.setdefault(tuple(sorted((node_id, other))), []).append(hex_id)

    sorted_edges = sorted(edge_hexes)
    edge_id_by_nodes = {edge_nodes: edge_id for edge_id, edge_nodes in enumerate(sorted_edges)}
    edges = {
        edge_id: Edge(id=edge_id, node_a=edge_nodes[0], node_b=edge_nodes[1], hex_ids=tuple(sorted(edge_hexes[edge_nodes])))
        for edge_nodes, edge_id in edge_id_by_nodes.items()
    }

    node_hexes: dict[int, list[int]] = {node_id: [] for node_id in node_id_by_key.values()}
    node_edges: dict[int, list[int]] = {node_id: [] for node_id in node_id_by_key.values()}
    for hex_id, node_ids in enumerate(hex_node_ids):
        for node_id in node_ids:
            node_hexes[node_id].append(hex_id)
    for edge_id, edge in edges.items():
        node_edges[edge.node_a].append(edge_id)
        node_edges[edge.node_b].append(edge_id)

    ports = _assign_ports(edges, node_hexes, sorted_corners, rng if seed is not None else None)
    nodes = {
        node_id: Node(
            id=node_id,
            hex_ids=tuple(sorted(node_hexes[node_id])),
            edge_ids=tuple(sorted(node_edges[node_id])),
            port=ports.get(node_id),
        )
        for node_id in node_hexes
    }
    hexes = {
        hex_id: Hex(id=hex_id, hex_type=hex_type, number_token=number, node_ids=hex_node_ids[hex_id])
        for hex_id, (_q, _r, hex_type, number) in enumerate(hex_specs)
    }
    board = Board(hexes=hexes, nodes=nodes, edges=edges, robber_hex_id=robber_hex_id)
    board.validate()
    return board


def _hex_specs_from_layout(
    coords: list[tuple[int, int]],
    resource_types: list[HexType],
    number_tokens: list[int],
) -> list[tuple[int, int, HexType, int | None]]:
    numbers = iter(number_tokens)
    hex_specs: list[tuple[int, int, HexType, int | None]] = []
    for index, (q, r) in enumerate(coords):
        hex_type = resource_types[index]
        number = None if hex_type == HexType.DESERT else next(numbers)
        hex_specs.append((q, r, hex_type, number))
    return hex_specs


def _random_valid_hex_specs(
    coords: list[tuple[int, int]],
    rng: random.Random,
    max_attempts: int = 10_000,
) -> list[tuple[int, int, HexType, int | None]]:
    best_specs: list[tuple[int, int, HexType, int | None]] | None = None
    best_score = float("inf")
    for _attempt in range(max_attempts):
        resource_types = list(STANDARD_RESOURCE_TYPES)
        number_tokens = list(STANDARD_NUMBER_TOKENS)
        rng.shuffle(resource_types)
        rng.shuffle(number_tokens)
        hex_specs = _hex_specs_from_layout(coords, resource_types, number_tokens)
        if _numbers_have_invalid_adjacency(hex_specs):
            continue
        score = _layout_quality_score(hex_specs)
        if score < best_score:
            best_specs = hex_specs
            best_score = score
        if score <= 10.0:
            return hex_specs
    if best_specs is not None:
        return best_specs
    raise RuntimeError("failed to generate a valid randomized Catan board")


def _numbers_have_invalid_adjacency(hex_specs: list[tuple[int, int, HexType, int | None]]) -> bool:
    for left_index, (left_q, left_r, _left_type, left_number) in enumerate(hex_specs):
        if left_number is None:
            continue
        for right_q, right_r, _right_type, right_number in hex_specs[left_index + 1 :]:
            if right_number is None:
                continue
            if _hex_distance(left_q, left_r, right_q, right_r) == 1:
                if left_number == right_number:
                    return True
                if left_number in RED_NUMBER_TOKENS and right_number in RED_NUMBER_TOKENS:
                    return True
    return False


def _hex_distance(left_q: int, left_r: int, right_q: int, right_r: int) -> int:
    left_s = -left_q - left_r
    right_s = -right_q - right_r
    return max(abs(left_q - right_q), abs(left_r - right_r), abs(left_s - right_s))


def _layout_quality_score(hex_specs: list[tuple[int, int, HexType, int | None]]) -> float:
    token_weights = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
    resource_pips = {resource: 0.0 for resource in Resource}
    resource_counts = {resource: 0 for resource in Resource}
    total_pips = 0.0
    total_resource_hexes = 0
    score = 0.0

    for _q, _r, hex_type, number in hex_specs:
        resource = HEX_TO_RESOURCE.get(hex_type)
        if resource is None or number is None:
            continue
        pips = float(token_weights.get(number, 0))
        resource_pips[resource] += pips
        resource_counts[resource] += 1
        total_pips += pips
        total_resource_hexes += 1

    for resource in Resource:
        expected = total_pips * resource_counts[resource] / max(1, total_resource_hexes)
        score += abs(resource_pips[resource] - expected)

    for left_index, (left_q, left_r, left_type, left_number) in enumerate(hex_specs):
        left_resource = HEX_TO_RESOURCE.get(left_type)
        if left_resource is None:
            continue
        for right_q, right_r, right_type, right_number in hex_specs[left_index + 1 :]:
            if _hex_distance(left_q, left_r, right_q, right_r) != 1:
                continue
            right_resource = HEX_TO_RESOURCE.get(right_type)
            if right_resource != left_resource:
                continue
            score += 1.5
            if token_weights.get(left_number or 0, 0) >= 4 and token_weights.get(right_number or 0, 0) >= 4:
                score += 2.5
    return score


def _hex_center(q: int, r: int) -> tuple[float, float]:
    return (math.sqrt(3) * (q + r / 2), 1.5 * r)


def _assign_ports(
    edges: dict[int, Edge],
    node_hexes: dict[int, list[int]],
    sorted_corners: list[tuple[float, float]],
    rng: random.Random | None = None,
) -> dict[int, Port]:
    boundary_edges = [
        edge_id
        for edge_id, edge in edges.items()
        if len(set(node_hexes[edge.node_a]).intersection(node_hexes[edge.node_b])) == 1
    ]

    def edge_angle(edge_id: int) -> float:
        edge = edges[edge_id]
        ax, ay = sorted_corners[edge.node_a]
        bx, by = sorted_corners[edge.node_b]
        return math.atan2((ay + by) / 2, (ax + bx) / 2)

    boundary_edges.sort(key=edge_angle)
    specs = [
        Port("generic", None, 3),
        Port("resource", Resource.LUMBER, 2),
        Port("generic", None, 3),
        Port("resource", Resource.BRICK, 2),
        Port("resource", Resource.WOOL, 2),
        Port("generic", None, 3),
        Port("resource", Resource.GRAIN, 2),
        Port("resource", Resource.ORE, 2),
        Port("generic", None, 3),
    ]
    if rng is not None:
        specs = list(specs)
        rng.shuffle(specs)

    ports: dict[int, Port] = {}
    used_nodes: set[int] = set()
    start_indexes = [int(index * len(boundary_edges) / len(specs)) for index in range(len(specs))]
    rotation = rng.randrange(len(boundary_edges)) if rng is not None else 0
    for spec, start in zip(specs, start_indexes, strict=True):
        for probe in range(len(boundary_edges)):
            edge = edges[boundary_edges[(start + rotation + probe) % len(boundary_edges)]]
            if edge.node_a not in used_nodes and edge.node_b not in used_nodes:
                ports[edge.node_a] = spec
                ports[edge.node_b] = spec
                used_nodes.update({edge.node_a, edge.node_b})
                break
    return ports


def hex_resource(hex_type: HexType) -> Resource | None:
    return HEX_TO_RESOURCE.get(hex_type)
