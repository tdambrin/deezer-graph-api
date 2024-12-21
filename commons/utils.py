import hashlib
import random
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import constants
import networkx as nx  # type: ignore
import numpy as np
import yaml


def random_color_generator():
    color = random.choice(list(constants.CSS4_COLORS.values())).lower()
    return color


def load_from_yml(path: Union[str, Path]) -> Dict[str, Any]:
    if not Path(path).exists():
        return {}
    with open(path, "r") as f:
        content = yaml.safe_load(f)
    return content


def values_to_str(
    values: Union[List[str], str],
    sep: str = ",",
) -> str:
    if isinstance(values, str):
        return values
    return sep.join([value.strip() for value in values])


def str_to_values(values: str, sep: str = ",") -> List[str]:
    return [value.strip() for value in values.split(sep)]


def order_words(s: str, sep: str = " ", fixed_len: int = 0):
    """
    Return input string with sorted words
    e.g. 'bob and alice' -> 'alice and bob'

    Args:
        s (str): string to order
        sep (str): words separator
        fixed_len (int): if pos, will right fill res string with spaces

    Returns:
        (str)
    """
    ordered = sep.join(sorted(s.split(sep)))
    if fixed_len <= 0:
        return ordered
    return ordered.ljust(fixed_len)


def dict_extend(*args) -> Dict[Any, Any]:
    """
    same as {**d1, **d2} but add overlapping values instead of overriding
    """
    d: Dict[Any, Any] = {}
    for entry in args:
        for key in entry:
            if d.get(key):
                d[key] += deepcopy(entry)[key]
            else:
                d[key] = deepcopy(entry)[key]
    return d


def scale_weights(
    relative_weights: List[int],
    target_sum: int,
    include_all: bool = True,
):
    """
    Scale list of weights for total sum. Puts at least one of initial weights.
    e.g. ([1, 2], 2) => [1, 1] because target sum smaller than weights and at least one each
    e.g. ([1, 2], 3) => [1, 2] because target sum == total weights
    e.g. ([1, 2], 5) => [2, 3] because target sum > total weights, at least one of each and tries to respect initial weights
    Args:
        relative_weights: weights of each index
        target_sum: sum(res) should be this
        include_all: bool whether every bin should have at least 1

    Returns:
        list of weights adjusted summing up to target_sum
    """  # noqa: E501
    if target_sum < len(relative_weights) and include_all:
        raise ValueError(
            "[Error: utils.scale_weights] "
            "Target sum smaller than number of bins, would result in bins deletion "
            f"target_sum={target_sum}, relative_weights: {relative_weights}"
        )  # noqa: E501
    n = len(relative_weights)
    res = [1] * n if include_all else [0] * n
    remaining = (
        [w - 1 for w in relative_weights]
        if include_all
        else relative_weights.copy()
    )
    used = n if include_all else 0
    _next = np.argmax(remaining)
    while used < target_sum and remaining[_next] > 0:
        remaining[_next] -= 1
        res[_next] += 1
        used += 1
        _next = np.argmax(remaining)

    if used < target_sum:
        res = [
            sum(weights)
            for weights in zip(
                res,
                scale_weights(
                    relative_weights, target_sum - used, include_all=False
                ),
            )
        ]

    return res


def nodes_edges_to_list_of_dict(
    g: nx.DiGraph,
    which: str,
    system_: str = constants.VIS_JS_SYS,
) -> List[Dict[str, Any]]:
    """
    Convert graph nodes/edges to a list of dicts

    Args:
        g: graph to extract nodes or edges
        which: 'nodes' or 'edges'
        system_: 'python' or 'vis.js' to define serialization api keys

    Returns:
        list of [{'id': node/edge id, **properties}]
    """

    assert which in (constants.NODES, constants.EDGES)

    if which == constants.NODES:
        nodes_ = g.nodes(data=True)
        return [{"id": i_id, **i_props} for i_id, i_props in nodes_]

    assert system_ in (constants.VIS_JS_SYS, constants.PYTHON_SYS)
    from_key_name = "u_of_edge" if system_ == constants.PYTHON_SYS else "from"
    to_key_name = "v_of_edge" if system_ == constants.PYTHON_SYS else "to"
    edges_ = g.edges(data=True)
    return [
        {from_key_name: source_id, to_key_name: to_id, **i_props}
        for source_id, to_id, i_props in edges_
    ]


def di_graph_from_list_of_dict(
    nodes: List[Dict[str, Any]], edges: Optional[List[Dict[str, Any]]] = None
) -> nx.DiGraph:
    """
    Create a nx.DiGraph from nodes and edges as list of props with their ids
    Args:
        nodes: [{'id': node/edge id, **properties}]
        edges (optional): [{'id': node/edge id, **properties}]

    Returns:
        nx.DiGraph filled
    """
    g_ = nx.DiGraph()
    for node in nodes:
        g_.add_node(
            node_for_adding=node["id"],
            **{key: value for key, value in node.items() if key != "id"},
        )
    if edges is None:
        return g_
    for edge in edges:
        g_.add_edge(
            u_of_edge=edge.get("u_of_edge") or edge.get("from"),
            v_of_edge=edge.get("v_of_edge") or edge.get("to"),
            **{
                key: value
                for key, value in edge.items()
                if key
                not in (
                    "from",
                    "to",
                    "u_of_edge",
                    "v_of_edge",
                )
            },
        )
    return g_


def is_uuid(candidate: str) -> bool:
    """
    Check if candidate is uuid format string
    Args:
        candidate (str)

    Returns:
        (bool)
    """
    try:
        uuid.UUID(candidate)
    except ValueError:
        return False
    return True


def commutative_hash(*args):
    """
    Hash function for list of strings where order of letter/words doesn't matter
    Higher collision proba as f('ab', 'ba') == f('aabb')
    Args:
        *args: list of strings. will be converted to strings if not

    Returns:
        hash of ordered join of all letters (with duplicates)
    """
    ordered_ = "".join(sorted(list("".join([str(arg) for arg in args]))))
    return hashlib.shake_128(ordered_.encode("utf-8")).hexdigest(4)
