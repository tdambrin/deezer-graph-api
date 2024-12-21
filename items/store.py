"""
Result items store - Singleton

Contains:
    - items cached to avoid parsing again
    - graphs for each query
"""

from typing import Dict, List, Optional, Set

import commons
import config
import constants
import networkx as nx  # type: ignore
from commons.metaclasses import ThreadSafeSingleton
from items.item import DeezerResource, ResourceFactory
from status import StatusManager


class ItemStore(metaclass=ThreadSafeSingleton):
    def __init__(self):
        """
        _items: cache for DeezerItem, key is spotify foreign item id
        _graphs: per session, per graph_key
        """
        self._items: Dict[int, DeezerResource] = {}
        self._graphs: Dict[str, Dict[str, nx.DiGraph]] = dict()

    @property
    def session_ids(self) -> Set[str]:
        return set(self._graphs.keys())

    @property
    def graph_keys(self) -> Set[str]:
        return set(
            sum(
                [
                    list(session_graphs.keys())
                    for session_graphs in self._graphs.values()
                ],
                [],
            )
        )

    @staticmethod
    def _depth_node_size(depth: int):
        if depth <= 1:
            return 50
        if depth == 2:
            return 30
        return 20

    @staticmethod
    def _popularity_node_size(popularity: Optional[int] = None):
        if popularity is None or popularity <= 20:
            return 15
        return min(popularity, 50)

    @staticmethod
    def graph_key_from_keywords(keywords: List[str]):
        return commons.values_to_str(keywords, "+")

    def get(self, item_id: int) -> DeezerResource | None:
        return self._items.get(item_id)

    def get_all_items(self):
        return self._items

    def get_graphs(self, session_id: str) -> Optional[Dict[str, nx.DiGraph]]:
        """
        Get active graphs from session
        Args:
            session_id (str): uuid4

        Returns:
            dict of graphs with id of their query node as key
        """
        return self._graphs.get(session_id)

    def get_graph(
        self, session_id: str, graph_key: str
    ) -> Optional[nx.DiGraph]:
        return self._graphs.get(session_id, {}).get(graph_key)

    def init_session(self, session_id: str):
        """
        Initialize graph for a session

        Args:
            session_id (str): uuid4
        """
        if self._graphs.get(session_id) is not None:
            return
        self._graphs[session_id] = {}

    def init_graph(self, session_id: str, graph_key: str):
        """
        Initialize graph for a session

        Args:
            session_id (str): uuid4
            graph_key (str): id of query node
        """
        self.init_session(session_id=session_id)
        if self._graphs[session_id].get(graph_key) is not None:
            return
        self._graphs[session_id][graph_key] = nx.DiGraph()

    def delete_nodes(
        self, session_id: str, graph_key: str, nodes_ids: List[int]
    ):
        """
        Delete nodes from Graph

        Args:
            session_id (str): user session identifier
            graph_key (str): id of the graph to add item to
            nodes_ids (List[str]): list of nodes id to delete
        """
        if self.get_graph(session_id=session_id, graph_key=graph_key) is None:
            return
        self._graphs[session_id][graph_key].remove_nodes_from(nodes_ids)

    def _add_node(
        self,
        session_id: str,
        graph_key: str,
        item: DeezerResource,
        depth: int = 3,
        color: Optional[str] = None,
        **kwargs,
    ):
        """
        Add node to the graph

        Args:
            session_id (str): user session identifier
            graph_key (str): id of the graph to add item to
            item (DeezerResource): parsed item
            selected_types (list): item types to add to node
            depth (int): for size styling
            color (str): node color, if None will be item.node_color
        """

        # Because Vis JS error if present
        optional_kwargs = {}
        factory_ = ResourceFactory(resource=item)
        if factory_.image:
            optional_kwargs["image"] = factory_.image

        # Add node to graph
        self._graphs[session_id][graph_key].add_node(
            item.id,
            label=factory_.label,
            title=factory_.title,
            size=self._popularity_node_size(factory_.popularity),
            color=color or factory_.node_color,
            shape="dot" if not factory_.image else "circularImage",
            href=item.link or "_blank",
            preview_url=factory_.preview_url,
            expand_enabled=depth > 0,
            graph_key=graph_key,
            node_type=item.type,
            depth=depth,
            **optional_kwargs,
            **kwargs,
            # font="10px arial white",
        )

    def set_query_node(
        self,
        session_id: str,
        query_kw: List[str],
        task_id: str,
        override: bool = False,
        **kwargs,
    ) -> str:
        """
        Set graph central query node
        Args:
            session_id (str): user session identifier
            query_kw: keywords used for the search
            task_id: task id corresponding to the search
            override (bool): whether to override if graph already exists

        Returns:
            Graph key
        """
        query_key = ItemStore.graph_key_from_keywords(query_kw)
        if self._graphs.get(session_id, {}).get(query_key):
            if not override:
                return query_key
            self._graphs[session_id][query_key] = nx.DiGraph()
        self.init_graph(session_id=session_id, graph_key=query_key)
        self._graphs[session_id][query_key].add_node(
            hash(query_key),
            label=commons.values_to_str(query_kw, sep=" "),
            title="Query",
            size=50,
            color=config.NodeColor.PRIMARY.value,
            shape="circle",
            href=f"https://open.spotify.com/search/{'%20'.join(query_kw)}",
            task_id=task_id,
            graph_key=query_key,
            node_type="query",
            **kwargs,
        )
        return query_key

    def add_nodes(
        self,
        session_id: str,
        graph_key: str,
        items_: List[DeezerResource],
        depth: int,
        task_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Add list of items to nodes of a graph

        Args:
            session_id (str): user session identifier
            graph_key (str): id of the graph to add item to
            items_ (List[DeezerResource]): items to add to the graph
            depth (int): for styling when adding to the graph
            task_id (str): if provided, set intermediate results to task
        """
        self.init_graph(session_id=session_id, graph_key=graph_key)
        graph_ = self.get_graph(session_id=session_id, graph_key=graph_key)
        assert graph_ is not None, "Graph not in session"

        for item_ in items_:
            if item_.id not in self._items:
                self._items[item_.id] = item_
            if not graph_.nodes.get(item_.id):
                self._add_node(
                    session_id=session_id,
                    graph_key=graph_key,
                    item=item_,
                    depth=depth,
                    **kwargs,
                )
        if task_id is not None:
            self.__add_nodes_edges_to_task(
                session_id=session_id,
                graph_key=graph_key,
                task_id=task_id,
            )

    def relate(
        self,
        session_id: str,
        graph_key: str | int,
        parent_id: str | int,
        children_ids: Set[str],
        task_id: Optional[str] = None,
        no_doubles: bool = True,
        **kwargs,
    ):
        """
        Add edges between result/query nodes

        Args:
            session_id (str): user session identifier
            graph_key (str | int): id of the graph to relate item in
            parent_id (str | int): node id of the parent node to relate item with
            children_ids (List[str]): list of node ids relate parent item with
            task_id (str): if provided, set intermediate results to task
            no_doubles (bool): whether to prevent double edges between nodes
        """

        exclusion_unordered_ids = set()
        if no_doubles:
            exclusion_unordered_ids = {
                unordered_id
                for _, _, unordered_id in self._graphs[session_id][
                    graph_key
                ].edges(data="unordered_id")
            }
        for child_id in children_ids:
            if (
                edge_id := commons.commutative_hash(parent_id, child_id)
            ) in exclusion_unordered_ids:
                continue  # don't add if there is an existing edge (undirected) and no_doubles

            # children first for color
            self._graphs[session_id][graph_key].add_edge(
                parent_id,
                child_id,
                width=config.EDGE_WIDTH,
                id=f"{parent_id}_{child_id}",
                unordered_id=edge_id,
                **kwargs,
            )

        if task_id is not None:
            self.__add_nodes_edges_to_task(
                session_id=session_id, graph_key=graph_key, task_id=task_id
            )

    def add_and_relate(
        self,
        session_id: str,
        graph_key: str,
        children: List[DeezerResource],
        parent_id: int,
        depth: int,
        task_id: Optional[str] = None,
        no_doubles: bool = True,
        **kwargs,
    ):
        self.add_nodes(
            session_id=session_id,
            graph_key=graph_key,
            items_=children,
            depth=depth,
            task_id=task_id,
            **kwargs,
        )
        self.relate(
            session_id=session_id,
            graph_key=graph_key,
            parent_id=parent_id,
            children_ids={child.id for child in children},
            no_doubles=no_doubles,
            task_id=task_id,
            **kwargs,
        )

    def get_successors(
        self,
        session_id: str,
        graph_key: str,
        node_id: int,
        recursive: bool = True,
        exclusion_set: Optional[Set[int]] = None,
    ) -> Set[int]:
        """
        Get successors of a node in the directed graph

        Args:
            session_id (str): user session identifier
            graph_key (str): id of the graph to relate item in
            node_id (str): node identifier
            recursive (bool): whether to check for successors' successors
            exclusion_set (Set[str]): to avoid loops when recursive
        """
        exclusion_set = exclusion_set or set()
        graph = self.get_graph(session_id=session_id, graph_key=graph_key)
        if not graph or node_id not in graph.nodes:
            return set()
        current = {
            n for n in graph.successors(n=node_id) if n not in exclusion_set
        }

        if not recursive:
            return current

        exclusion_set.add(node_id)
        exclusion_set = exclusion_set.union(current)
        return current.union(
            *(
                self.get_successors(
                    session_id=session_id,
                    graph_key=graph_key,
                    node_id=s,
                    recursive=recursive,
                    exclusion_set=exclusion_set,
                )
                for s in current
            )
        )

    def get_predecessors(
        self,
        session_id: str,
        graph_key: str,
        node_id: int,
        recursive: bool = True,
        exclusion_set: Optional[Set[int]] = None,
    ) -> Set[int]:
        """
        Get predecessors of a node in the directed graph

        Args:
            session_id (str): user session identifier
            graph_key (str): id of the graph to relate item in
            node_id (str): node identifier
            recursive (bool): whether to check for predecessors' predecessors
            exclusion_set (Set[str]): to avoid loops when recursive
        """
        exclusion_set = exclusion_set or set()
        graph = self.get_graph(session_id=session_id, graph_key=graph_key)
        if not graph or node_id not in graph.nodes:
            return set()
        current = {
            n for n in graph.predecessors(n=node_id) if n not in exclusion_set
        }

        if not recursive:
            return current

        exclusion_set.add(node_id)
        exclusion_set = exclusion_set.union(current)
        return current.union(
            *(
                self.get_predecessors(
                    session_id=session_id,
                    graph_key=graph_key,
                    node_id=s,
                    recursive=recursive,
                    exclusion_set=exclusion_set,
                )
                for s in current
            )
        )

    def __add_nodes_edges_to_task(
        self, session_id: str, graph_key: str, task_id: str
    ):
        """
        Add nodes and edges to task result.
        Used to set intermediate (when task still running) results.

        Args:
            session_id (str): user session identifier
            graph_key (str): id of the graph to relate item in
            task_id (str): if provided, set intermediate results to task
        """
        current_graph = self.get_graph(
            session_id=session_id, graph_key=graph_key
        )
        nodes_and_edges = {
            "nodes": commons.nodes_edges_to_list_of_dict(
                current_graph, constants.NODES  # type: ignore
            ),
            "edges": commons.nodes_edges_to_list_of_dict(
                current_graph, constants.EDGES, system_=constants.VIS_JS_SYS  # type: ignore
            ),
        }
        StatusManager().set_intermediate_result(
            task_id=task_id,
            result=nodes_and_edges,
        )
