import uuid
from enum import Enum
from functools import reduce
from operator import add
from typing import Annotated, Any, Dict, List, Optional, Set

import commons
import config
import constants
from api_clients.wrappers import DeezerWrapper
from commons import str_to_values
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from items import ItemStore
from status import StatusManager
from tasks import TaskManager


class Tags(Enum):
    SESSION = "Session"
    CACHE = "Cache"
    ITEMS = "Items"
    TASKS = "Tasks"
    INTERACTIONS = "Interactions"
    TECHNICAL = "Technical"


dzg_api = FastAPI(
    title="Deezer Graph API",
    default_response_class=JSONResponse,
)

origins = [
    "http://localhost:8080",
    "http://192.168.1.155:8080",
    "http://localhost:8502",
    "https://tdambrin.github.io",
    # "*",
]

dzg_api.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
    ],
    allow_headers=["*"],
)


# --- Sessions ---


@dzg_api.get("/api/sessions/create", tags=[Tags.SESSION])
def get_session_params() -> Dict[str, str]:
    """
    Get new session id
    Returns:
        (str) uuid
    """
    return {"session_id": str(uuid.uuid4())}


@dzg_api.get("/api/sessions/restore", tags=[Tags.SESSION])
def restore_session(
    session_id: Annotated[str, Header()],
) -> Dict[str, Any]:
    """
    Restore session
    Args:
        session_id (str): uuid

    Returns:
        {
            "graph_keys": List[str],
            "nodes": List[Dict[str, Any]],
            "edges": List[Dict[str, Any]]
        }
    """
    graphs = ItemStore().get_graphs(session_id=session_id)
    if not graphs:
        return {}
    return {
        "graph_keys": list(graphs.keys()),
        "nodes": reduce(
            add,
            [
                commons.nodes_edges_to_list_of_dict(
                    graph_, which=constants.NODES
                )
                for graph_ in graphs.values()
            ],
        ),
        "edges": reduce(
            add,
            [
                commons.nodes_edges_to_list_of_dict(
                    graph_, which=constants.EDGES, system_=constants.VIS_JS_SYS
                )
                for graph_ in graphs.values()
            ],
        ),
    }


# --- Graph Interactions ---


@dzg_api.get("/api/search/{keywords}", tags=[Tags.INTERACTIONS])
def search(
    keywords: str,
    selected_types: str,
    session_id: Annotated[str, Header()],
) -> Dict[str, Any]:
    """
    Start new search. Will override graphs with same keywords in same session.

    Args:
        keywords (str): '+' separated
        selected_types (str): '+' separated
        session_id (str): uuid

    Returns:
        {
            "task_id": uuid,
            "nodes": List[Dict[str, Any]],
            "edges": List[Dict[str, Any]]
        }
    """
    # Parse params
    keywords_: List[str] = commons.str_to_values(keywords, sep="+")
    selected_types_: List[str] = commons.str_to_values(selected_types, sep="+")

    # Start search
    ctrl = TaskManager(session_id=session_id, selected_types=selected_types_)
    return ctrl.search_task(keywords=keywords_, save=False)


@dzg_api.get("/api/expand/{graph_key}/{node_id}", tags=[Tags.INTERACTIONS])
def start_expand(
    graph_key: str,
    node_id: int,
    selected_types: str,
    session_id: Annotated[str, Header()],
    item_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Expand graph from node.

    Args:
        graph_key (str): identifier of query node
        node_id (int): seed node id
        selected_types (str): subset of ['album', 'artist','track'], '+' sep
        session_id (str): uuid
        item_type: one of ['album', 'artist','track']

    Returns:
        {
            "task_id": uuid
        }
    """
    ctrl = TaskManager(
        session_id=session_id,
        graph_key=graph_key,
        selected_types=str_to_values(selected_types, sep="+"),
    )
    task_id = ctrl.start_expand_task(
        node_id=node_id, item_type=item_type, save=False
    )
    return {"task_id": task_id}


@dzg_api.get("/api/delete/{graph_key}/{node_id}", tags=[Tags.INTERACTIONS])
def delete(
    graph_key: str,
    node_id: int,
    session_id: Annotated[str, Header()],
    cascading: bool = True,
) -> Dict[str, Any]:
    """
    Delete node from graph.

    Args:
        graph_key (str): identifier of query node
        node_id (int): seed node id
        session_id (str): uuid
        cascading (bool): whether successors are deleted too

    Returns:
        Deleted nodes.
        {
            "nodes": List[Dict[str, Any]]
        }
    """
    nodes_to_delete = {node_id}
    if cascading:
        nodes_to_delete = nodes_to_delete.union(
            ItemStore().get_successors(
                session_id=session_id,
                graph_key=graph_key,
                node_id=node_id,
                recursive=True,
            )
        )
    ItemStore().delete_nodes(
        session_id=session_id,
        graph_key=graph_key,
        nodes_ids=list(nodes_to_delete),
    )
    return {
        "nodes": nodes_to_delete,
    }


# --- Tasks ---


@dzg_api.get("/api/tasks/{task_id}/status", tags=[Tags.TASKS])
def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get task status.

    Args:
        task_id (str): uuid

    Returns:
        {
            "status": one of (idle, running, created, failed, completed, not_found),
            "error": str if any,
            **task_result if task result is dict else "result": single result
        }
    """  # noqa: E501
    return StatusManager().get_status_and_result(task_id=task_id)


@dzg_api.get("/api/tasks", tags=[Tags.TASKS])
def get_all_tasks() -> List[Dict[str, Any]]:
    """
    Get all tasks and their status

    Returns:
        [{
            "status": one of (idle, running, created, failed, completed, not_found),
            "error": str if any,
            "result": task result
        }]
    """  # noqa: E501
    return StatusManager().all_tasks


@dzg_api.get("/api/cache/items", tags=[Tags.CACHE])
def get_cached_items() -> Dict[str, Dict[int, Any]]:
    """
    Get all items in store

    Returns:
        {
            "items": [{item}]
        }
    """
    all_items = ItemStore().get_all_items()
    return {
        "items": {item_.id: item_.as_dict() for item_ in all_items.values()}
    }


@dzg_api.get("/api/cache/items/{item_id}", tags=[Tags.CACHE])
def get_cached_item(item_id: int) -> Dict[str, Any]:
    """
    Get item in store

    Args:
        item_id (str): deezer id

    Returns:
        {
            "item": {item}
        }
    """
    return {"item": ItemStore().get(item_id)}


@dzg_api.get("/api/items/{item_id}/successors", tags=[Tags.ITEMS])
def get_item_successors(
    item_id: int,
    graph_key: str,
    session_id: Annotated[str, Header()],
    recursive: bool = True,
) -> Set[int]:
    """
    Get item successor in a session graph

    Args:
        graph_key (str): identifier of query node
        item_id (int): seed node id
        session_id (str): uuid
        recursive (bool): whether to get successors' successors

    Returns:
        list of node ids
    """
    return ItemStore().get_successors(
        session_id=session_id,
        graph_key=graph_key,
        node_id=item_id,
        recursive=recursive,
    )


@dzg_api.get("/api/items/{item_id}/predecessors", tags=[Tags.ITEMS])
def get_item_predecessors(
    item_id: int,
    graph_key: str,
    session_id: Annotated[str, Header()],
    recursive: bool = True,
) -> Set[int]:
    """
    Get item predecessors in a session graph

    Args:
        graph_key (str): identifier of query node
        item_id (int): seed node id
        session_id (str): uuid
        recursive (bool): whether to get predecessors' predecessors

    Returns:
        list of node ids
    """
    return ItemStore().get_predecessors(
        session_id=session_id,
        graph_key=graph_key,
        node_id=item_id,
        recursive=recursive,
    )


@dzg_api.get("/api/items/{item_id}", tags=[Tags.ITEMS])
def get_item_from_deezer(item_id: int, item_type: str) -> Dict[str, Any]:
    """
    Get item in store

    Args:
        item_id (int): deezer id
        item_type (str): one of ['album', 'artist','track']

    Returns:
        {
            "item": {item}
        }
    """
    return {
        "item": DeezerWrapper()
        .find(item_id=item_id, item_type=item_type)
        .as_dict()
    }


@dzg_api.get("/docs", include_in_schema=False, tags=[Tags.TECHNICAL])
async def get_documentation():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")


@dzg_api.get("/health", include_in_schema=False, tags=[Tags.TECHNICAL])
async def health():
    return {"state": "up"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(dzg_api, host="127.0.0.1", port=8502, log_level="info")

    # Thread version - not reached
    import threading

    threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": dzg_api,
            "host": config.API_HOST,
            "port": config.API_PORT,
            "log_level": "info",
        },
    ).start()
