"""
Task Manager to instantiate and handle tasks
"""

import uuid
from typing import Any, Dict, List, Optional

import commons
import constants
from api_clients.wrappers import DeezerWrapper
from config import OUTPUT_DIR
from items.item import ValidItem
from items.store import ItemStore
from tasks.task import Task

import networkx as nx  # type: ignore # isort: skip


class TaskManager:

    ALL_TYPES = [
        ValidItem.ALBUM.value,
        ValidItem.ARTIST.value,
        ValidItem.TRACK.value,
    ]

    def __init__(
        self,
        session_id: str,
        graph_key: Optional[str] = None,
        selected_types: Optional[List[str]] = None,
    ):
        """
        Args:
            session_id (str): user session id
            graph_key (str): id of the graph to focus on, optional
            selected_types (list): to restrict result types, optional
        """
        self._session_id = session_id
        self._graph_key = graph_key
        self._selected_types: List[str] = (
            selected_types or TaskManager.ALL_TYPES
        )

    def search_task(self, keywords: List[str], save: bool = False):
        """
        Search task, returns query node and expand in split thread

        Args:
            keywords: Search keywords
            save: whether to write result to local fs

        Returns:
            graph summary
        """
        task_id = str(uuid.uuid4())
        self._graph_key = self._init_query_graph(
            keywords=keywords, task_id=task_id
        )
        task = Task(
            target=self.expand_from_query_node,
            task_uuid=task_id,
            use_threading=True,
            keywords=keywords,
            task_id=task_id,
        )
        task.run()
        graph_ = ItemStore().get_graph(
            session_id=self._session_id, graph_key=self._graph_key
        )
        return {
            "task_id": task_id,
            "nodes": commons.nodes_edges_to_list_of_dict(
                graph_, which=constants.NODES
            ),
            "edges": commons.nodes_edges_to_list_of_dict(
                graph_, which=constants.EDGES, system_=constants.VIS_JS_SYS
            ),
        }

    def expand_from_query_node(
        self,
        keywords: List[str],
        task_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Expand with search from query node

        Args:
            keywords: list of keywords to search
            task_id (str): if provided, set intermediate results to task
        """
        assert (
            self._graph_key is not None
        ), "Graph not properly initialized for search. Graph key is None"
        DeezerWrapper().search(
            keywords=keywords,
            session_id=self._session_id,
            graph_key=self._graph_key,
            max_depth=3,
            restricted_types=self._selected_types,
            task_id=task_id,
        )
        current_graph = ItemStore().get_graph(
            session_id=self._session_id, graph_key=self._graph_key
        )

        res = {
            "nodes": commons.nodes_edges_to_list_of_dict(
                current_graph, constants.NODES
            ),
            "edges": commons.nodes_edges_to_list_of_dict(
                current_graph, constants.EDGES, system_=constants.VIS_JS_SYS
            ),
        }
        return res

    def _init_query_graph(self, keywords: List[str], task_id: str) -> str:
        """
        Initialize query graph with a query node

        Args:
            keywords (list): list of search keywords
            task_id (str): search task id

        Returns:
            graph key
        """
        graph_key = ItemStore().set_query_node(
            query_kw=keywords,
            session_id=self._session_id,
            task_id=task_id,
            override=True,
        )
        return graph_key

    def start_expand_task(
        self, node_id: int, item_type: Optional[str] = None, save: bool = False
    ):
        """
        Start the task in a thread and return task id
        Args:
            node_id (int): node from which to expand
            item_type (str): to retrieve from spotify if not in cache
            save (bool): whether to save the html graph as a result (default false)

        Returns:
            task id
        """
        task_id = str(uuid.uuid4())
        task = Task(
            target=self.expand_from_node,
            task_uuid=task_id,
            use_threading=True,
            node_id=node_id,
            item_type=item_type,
            save=save,
        )
        task.run()
        return task_id

    def expand_from_node(
        self, node_id: int, item_type: Optional[str] = None, save: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Expand the graph from one node

        Args:
            node_id (int): node from which to expand
            item_type (str): to retrieve from spotify if not in cache
            save (bool): whether to save the html graph as a result (default false)

        Returns:
            nodes and edges as dict
        """

        store = ItemStore()
        item_ = store.get(item_id=node_id)
        if item_ is None:
            if item_type is None or item_type not in [
                valid_.value for valid_ in ValidItem
            ]:
                raise ValueError(
                    f"""
                    [task_manager.expand_from_node] item {node_id} not in cache and
                    item type {item_type or 'None'} is invalid.
                    """
                )

            item_ = DeezerWrapper().find(
                item_id=node_id,
                item_type=ValidItem(item_type),
            )
        assert self._graph_key is not None, "Graph key not provided for expand"

        # Fill and Explore
        #  Same color group
        nodes_color = commons.random_color_generator()
        #  Fill first
        DeezerWrapper.fill(
            session_id=self._session_id,
            graph_key=self._graph_key,
            item_=item_,
            restricted_types=self._selected_types,
            depth=1,
            color=nodes_color,
        )
        #  Then explore
        DeezerWrapper.find_related(
            session_id=self._session_id,
            graph_key=self._graph_key,
            item_=item_,
            depth=1,  # activate expand enabled
            max_depth=1,
            backbone_type=DeezerWrapper().get_backbone_type(
                self._selected_types
            ),
            star_types=self._selected_types,
            exploration_mode=True,
            color=nodes_color,
        )
        current_graph = ItemStore().get_graph(
            session_id=self._session_id, graph_key=self._graph_key
        )

        if save:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            filename = OUTPUT_DIR / (
                "_".join([self._graph_key, "0", "4"]) + ".gml"
            )
            nx.write_gml(current_graph, filename)

        return {
            "nodes": commons.nodes_edges_to_list_of_dict(
                current_graph, constants.NODES
            ),
            "edges": commons.nodes_edges_to_list_of_dict(
                current_graph, constants.EDGES
            ),
        }
