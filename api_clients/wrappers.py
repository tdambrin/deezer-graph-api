import functools
import json
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Union

import commons
import config
import deezer
from commons import utils
from items import DeezerResource, ItemStore, ResourceFactory, ValidItem

from .clients import deezer_client


class DeezerWrapper:
    REC_SIZE = 5  # Recommendation max size for one node

    ALL_TYPES: List[str] = [
        ValidItem.ALBUM.value,
        ValidItem.ARTIST.value,
        ValidItem.TRACK.value,
        # ValidItem.PLAYLIST.value,
        # ValidItem.SHOW.value, ValidItem.EPISODE.value, ValidItem.AUDIOBOOK.value,
    ]

    # Backbone type selector
    BACKBONE_PRIORITIES: Dict[str, int] = {
        ValidItem.ARTIST.value: 1,
        ValidItem.ALBUM.value: 2,
        ValidItem.TRACK.value: 3,
    }

    # Recommendation weight for each type when several possible
    TYPE_REC_WEIGHT: Dict[str, int] = {
        ValidItem.ALBUM.value: 1,
        ValidItem.ARTIST.value: 1,
        ValidItem.TRACK.value: 3,
        # ValidItem.PLAYLIST.value: 0,
        # ValidItem.SHOW.value: 0, ValidItem.EPISODE.value: 0, ValidItem.AUDIOBOOK.value: 0,
    }

    def __init__(self):
        self.__client = deezer_client

    @staticmethod
    def cache(name, obj):
        from config import PROJECT_ROOT

        response_dir = PROJECT_ROOT / "responses"
        response_dir.mkdir(parents=True, exist_ok=True)
        with open(response_dir / name, "w") as f:
            json.dump(obj, f)

    @staticmethod
    def read_cache(name):
        from config import PROJECT_ROOT

        return json.load(open(PROJECT_ROOT / "responses" / name, "r"))

    # -- Helpers --

    @classmethod
    def get_backbone_type(cls, restricted_types: List[str]) -> str:
        """
        Get backbone type out of list of restricted types
        Args:
            restricted_types (List[str]): values from self.all_types

        Returns:
            selected backbone type, one of restricted_types
        """
        candidates = sorted(
            restricted_types, key=lambda type_: cls.BACKBONE_PRIORITIES[type_]
        )
        return next(iter(candidates))

    @staticmethod
    def _scale_per_type(limit: int, restricted_types: List[str]):
        relative_rec_weights = [
            DeezerWrapper.TYPE_REC_WEIGHT[_type] for _type in restricted_types
        ]
        scaled_rec_weights = {
            _type: scaled_weight
            for _type, scaled_weight in zip(
                restricted_types,
                utils.scale_weights(relative_rec_weights, limit),
            )
        }
        return scaled_rec_weights

    # -- Deezer methods --

    def find(
        self,
        item_id: int,
        item_type: Union[ValidItem, str],
    ) -> DeezerResource:
        """
        Find an item from Deezer

        Args:
            item_id (int): id of the item looked for
            item_type (str): type of the item e.g. album, artist, track

        Returns:
            instance of DeezerItem subclass
        """
        if isinstance(item_type, str):
            item_type = ValidItem(item_type)

        valid_types = [
            ValidItem.ALBUM.value,
            ValidItem.ARTIST.value,
            ValidItem.TRACK.value,
        ]
        if item_type.value not in valid_types:
            raise ValueError(
                "[Error: DeezerWrapper.find] Item type not provided or not in "
                f"{','.join(valid_types)}"
            )

        if item_type == ValidItem.ALBUM:
            return self.__client.get_album(album_id=item_id)
        elif item_type == ValidItem.ARTIST:
            return self.__client.get_artist(artist_id=item_id)
        # item_type == ValidItem.TRACK:
        return self.__client.get_track(track_id=item_id)

    def _search_item_type(
        self,
        item_type: str,
        keywords: List[str],
        limit: int = 5,
    ) -> List[DeezerResource]:
        """
        Select right deezer endpoint for different types search

        Args:
            item_type (str): one of ValidItem.values()
            keywords (List[str]): search keywords
            limit (str): results limit

        Returns:
            list of matching DeezerResource (subclass corresponding to item type)
        """
        if item_type == ValidItem.ARTIST.value:
            return self.__client.search_artists(" ".join(keywords))[:limit]
        elif item_type == ValidItem.ALBUM.value:
            return self.__client.search_albums(" ".join(keywords))[:limit]
        elif item_type == ValidItem.TRACK.value:
            return self.__client.search(" ".join(keywords))[:limit]
        raise NotImplementedError(
            f"[Error: DeezerWrapper._search_item_type] "
            f"Item type {item_type} not supported"
        )

    def _search_best_type(
        self,
        keywords: List[str],
        target_type: str,
        allowed_types: List[str],
        limit: int = 5,
    ) -> List[DeezerResource]:
        """
        Search a list of target_type items from keywords.
        Patches the poor ability for deezer/search to find an item of type X from keywords for type B.

        Args:
            keywords (List[str]): search keywords
            target_type (str): one of ValidItem.values(), the type of the return objects
            allowed_types (List[str]): list of types allowed to scan
            limit (str): results limit

        Returns:
            list of DeezerResource with subtype = target_type
        """  # noqa: E501

        keywords_str = commons.values_to_str(keywords, sep=" ")
        type_priorities = [
            ValidItem.TRACK.value,
            ValidItem.ARTIST.value,
            ValidItem.ALBUM.value,
        ]  # people more likely to search tracks than artists than albums
        # scan all and find best match

        search_partial = functools.partial(
            self._search_item_type,
            keywords=keywords,
            limit=limit * 3,
            # ^ to allow bigger range and get limit artists out of the results
        )
        score_partial = functools.partial(
            DeezerWrapper._match_score,
            keywords=keywords_str,
            types_priority=type_priorities,
            hipster_mode=False,
        )

        # get all candidates for all types
        all_candidates = sorted(
            [
                candidate_res
                for candidate_type in allowed_types
                for candidate_res in search_partial(item_type=candidate_type)
            ],
            key=lambda c: -score_partial(c),
        )

        # select the #limit best ones
        best_candidates = {}
        for candidate_resource in all_candidates:
            for converted in ResourceFactory(
                resource=candidate_resource
            ).to_type(
                target_type=ValidItem(target_type),
            ):
                if best_candidates.get(converted.id) is None:
                    best_candidates[converted.id] = converted
                    if len(best_candidates) == limit:
                        return list(best_candidates.values())
        return list(best_candidates.values())

    @staticmethod
    def _is_better_match(
        candidate: deezer.Resource,
        champion: deezer.Resource,
        keywords: str,
        types_priority: List[str],
        hipster_mode: bool = False,
    ) -> bool:
        """
        Whether the candidate is a better search match than the champion.

        Args:
            candidate (deezer.Resource): candidate result
            champion (deezer.Resource): current best match
            keywords (str): query keywords
            types_priority (List[str]): the lower the index the more encouraged
            hipster_mode (bool): should encourage a less popular result

        Returns:
            (bool)
        """  # noq: E501

        score_calculator = functools.partial(
            DeezerWrapper._match_score,
            keywords=keywords,
            types_priority=types_priority,
            hipster_mode=hipster_mode,
        )

        return score_calculator(candidate) > score_calculator(champion)

    @staticmethod
    def _match_score(
        candidate: deezer.Resource,
        keywords: str,
        types_priority: List[str],
        hipster_mode: bool = False,
    ) -> float:
        """
        Compute a match score for candidate given query keywords and advanced modes.
        Formula: 2 * w_str - .1 * w_type + w_pop, all weights in [0..1]
        where:
            - w_str: SequenceMatcher().ratio for candidate - SequenceMatcher().ratio for champion
            - w_type: penalty of type priority (0 if candidate type is first in types_priority)
            - w_pop: +/- a normalized popularity score.
                     - if hipster_mode
                     + if not

        Args:
            candidate (deezer.Resource): candidate result
            keywords (str): query keywords
            types_priority (List[str]): the lower the index the more encouraged
            hipster_mode (bool): encourages a less popular result

        Returns:
            (float) a match score
        """

        factory_ = ResourceFactory(resource=candidate)

        # Weight of keywords match
        max_full_name_len = 30 + 70 + 70  # artist + album + track
        w_str = SequenceMatcher(
            None,
            utils.order_words(
                keywords.lower(), sep=" ", fixed_len=max_full_name_len
            ),
            utils.order_words(
                factory_.full_name.lower(),
                sep=" ",
                fixed_len=max_full_name_len,
            ),
        ).ratio()

        # start = time.time()

        # Weight of type priority
        w_type = types_priority.index(candidate.type) / max(
            len(types_priority) - 1, 1
        )

        # Weight of popularity (people usually search for popular things unless hipster mode activated)
        hipster_multiplier = -1 if hipster_mode else 1

        # Deactivated to simplify - Thresholds
        # distance = factory_.popularity_distance
        # bound = 0 if distance < 0 else DeezerWrapper.POPULARITY_UPPERS[candidate.type]
        # normalization_factor = abs(bound - factory_.popularity_threshold)
        # w_pop = hipster_multiplier * (distance / normalization_factor)

        w_pop = (
            hipster_multiplier * factory_.popularity / 100
        )  # popularity is a percent

        return 2 * w_str - 0.1 * w_type + w_pop

    def search(
        self,
        keywords: List[str],
        session_id: str,
        graph_key: str,
        restricted_types: Optional[List[str]] = None,
        max_depth: int = 2,
        task_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Search from keywords and recursive recommendation. Add results to ItemStore
        Adding to the store will form a graph whose structure is a backbone of a single type
        and stars of the other types.
        Backbone types priorities are the order of self.all_types

        Args:
            keywords: search keywords
            session_id (str): user session identifier
            graph_key: key of the graph it corresponds to in the store
            restricted_types: result items type restriction. All if None.
            max_depth: recommendations start at level 2, inclusive
            task_id (str): if provided, set intermediate results to task

        Returns:
            id of the graph
        """
        restricted_types = restricted_types or DeezerWrapper.ALL_TYPES

        assert (
            len(set(restricted_types) - set(DeezerWrapper.ALL_TYPES)) == 0
        ), (
            "[Error: DeezerWrapper.search] "
            f"restricted_types={','.join(restricted_types)} contains illegal values."
            f"Accepted values are {','.join(DeezerWrapper.ALL_TYPES)}"
        )

        backbone_type = self.get_backbone_type(
            restricted_types=restricted_types
        )

        # Get Deezer results
        search_results = self._search_best_type(
            keywords=keywords,
            allowed_types=restricted_types,
            target_type=backbone_type,
            limit=DeezerWrapper.REC_SIZE,
        )

        # Parse and set results to store
        ItemStore().add_nodes(
            session_id=session_id,
            graph_key=graph_key,
            items_=search_results,
            depth=1,
            task_id=task_id,
            is_backbone=True,
        )

        ItemStore().relate(
            session_id=session_id,
            graph_key=graph_key,
            parent_id=hash(graph_key),
            children_ids={item_.id for item_ in search_results},
            task_id=task_id,
            is_backbone=True,
            color=config.NodeColor.BACKBONE,
        )

        # Expand search
        exploration_mode = {
            **{t: False for t in restricted_types},
            backbone_type: True,
        }
        related_partial = functools.partial(
            self.find_related,
            session_id=session_id,
            graph_key=graph_key,
            depth=2,
            max_depth=max_depth,
            backbone_type=backbone_type,
            star_types=restricted_types,
            task_id=task_id,
            exploration_mode=exploration_mode,
            **kwargs,
        )
        if max_depth >= 1:
            for item_ in search_results:
                related_partial(item_=item_)

        return graph_key

    @staticmethod
    def find_related(
        session_id: str,
        graph_key: str,
        item_: DeezerResource,
        depth: int,
        max_depth: int,
        backbone_type: str,
        star_types: List[str],
        task_id: Optional[str] = None,
        exploration_mode: bool | Dict[str, bool] = False,
        limit: int | None = None,
        **kwargs,
    ) -> List[DeezerResource]:
        """
        Find nodes related to a starting node
        Args:
            session_id (str): user session identifier
            graph_key (str): to get items from store
            item_ (DeezerResource): starting item to find related for
            depth (int): current depth
            max_depth (int): maximum depth allowed, inclusive
            backbone_type (str): item type of the backbone
            star_types (List[str]): types of the star nodes
            task_id (str): if provided, set intermediate results to task
            exploration_mode (bool | dict[type, bool]): to avoid getting tracks from the same artists
            limit (int): for star items

        Returns:
            (List[DeezerResource]) Star items
        """

        # -- Input validation --
        if not item_:
            return []
        if depth > max_depth:
            return []
        if isinstance(exploration_mode, dict) and not (
            {backbone_type, *star_types} == set(exploration_mode.keys())
        ):
            raise ValueError(  # noqa: E501
                "[Error: DeezerWrapper.find_related]"
                f" Illegal value for exploration_mode : {exploration_mode}. "
                f" Provide the a value for each type in {', '.join([backbone_type, *star_types])}"
            )

        if isinstance(exploration_mode, bool):
            exploration_mode = {
                t: exploration_mode for t in [backbone_type, *star_types]
            }

        assert backbone_type in DeezerWrapper.ALL_TYPES, (
            "[Error: DeezerWrapper.find_related] "
            f"Illegal value for backbone type : {backbone_type}. "
            f"Accepted values are {','.join(DeezerWrapper.ALL_TYPES)}"
        )

        # -- Core --
        # Get backbone extension first
        backbone_extension = list(
            DeezerWrapper.recommend_from_item(
                item_=item_,
                limit_per_type={backbone_type: 1},
                exploration_mode=exploration_mode,
            )
        )
        assert len(backbone_extension) <= 1, (
            "[Error: DeezerWrapper.find_related] "
            f"Backbone extensions larger than 1: {backbone_extension}"
            f"From item {item_}, limit per type = {backbone_type}: 1"
        )
        ItemStore().add_nodes(
            session_id=session_id,
            graph_key=graph_key,
            items_=backbone_extension,
            depth=depth,
            selected_types=[backbone_type],
            task_id=task_id,
            is_backbone=True,
        )

        ItemStore().relate(
            session_id=session_id,
            graph_key=graph_key,
            parent_id=item_.id,
            children_ids={
                parsed_item.id for parsed_item in backbone_extension
            },
            task_id=task_id,
            is_backbone=False,
            color=config.NodeColor.BACKBONE,
        )

        if backbone_extension:  # bfs
            DeezerWrapper.find_related(
                session_id=session_id,
                graph_key=graph_key,
                item_=backbone_extension[0],
                depth=depth + 1,
                max_depth=max_depth,
                backbone_type=backbone_type,
                star_types=star_types,
                task_id=task_id,
                exploration_mode=exploration_mode,
                color=config.NodeColor.BACKBONE,
            )

        # Then get star
        # make sure backbone type not in star types
        star_types = [type_ for type_ in star_types if type_ != backbone_type]

        if star_types:  # If no start type, no star
            limit_per_type = DeezerWrapper._scale_per_type(
                limit=limit or DeezerWrapper.REC_SIZE,
                restricted_types=star_types,
            )
            star_items = list(
                DeezerWrapper.recommend_from_item(
                    item_=item_,
                    limit_per_type=limit_per_type,
                    exploration_mode=exploration_mode,
                )
            )

            # Parse and add to store
            ItemStore().add_nodes(
                session_id=session_id,
                graph_key=graph_key,
                items_=star_items,
                depth=depth + 2,
                task_id=task_id,
                is_backbone=False,
                color=kwargs.get("color") or commons.random_color_generator(),
            )

            ItemStore().relate(
                session_id=session_id,
                graph_key=graph_key,
                parent_id=item_.id,
                children_ids={parsed_item.id for parsed_item in star_items},
                task_id=task_id,
                color=config.NodeColor.BACKBONE,
                hidden=True,
                is_backbone=False,
            )
            return star_items
        return []

    @staticmethod
    def fill(
        session_id: str,
        graph_key: str,
        item_: DeezerResource,
        restricted_types: List[str],
        depth: int | None = 1,
        task_id: str | None = None,
        color: str | None = None,
    ):
        """

        Args:
            session_id (str): user session identifier
            graph_key (str): to get items from store
            item_ (DeezerResource): starting item to find related for
            restricted_types (List[str]): allowed types to get
            depth (int): current depth
            task_id (str): if provided, set intermediate results to task
            color (str): optional, node color
        """
        alternative_types = [
            type_ for type_ in restricted_types if type_ != item_.type
        ]
        limit_per_type = DeezerWrapper._scale_per_type(
            limit=DeezerWrapper.REC_SIZE, restricted_types=alternative_types
        )
        filled = DeezerWrapper.recommend_from_item(
            item_=item_,
            limit_per_type=limit_per_type,
            exploration_mode={type_: False for type_ in restricted_types},
        )

        # Parse and add to store
        ItemStore().add_nodes(
            session_id=session_id,
            graph_key=graph_key,
            items_=list(filled),
            depth=depth + 2,
            task_id=task_id,
            is_backbone=False,
            color=color or commons.random_color_generator(),
        )

        ItemStore().relate(
            session_id=session_id,
            graph_key=graph_key,
            parent_id=item_.id,
            children_ids={parsed_item.id for parsed_item in filled},
            task_id=task_id,
            color=config.NodeColor.BACKBONE,
            hidden=True,
            is_backbone=False,
        )

    @staticmethod
    def recommend_from_item(
        item_: DeezerResource,
        limit_per_type: Dict[str, int],
        exploration_mode: Dict[str, bool] = None,
    ) -> Set[DeezerResource]:
        """
        Get recommendation results from item. Add items to ItemStore
        Args:
            item_ (DeezerResource): parsed starting item
            limit_per_type (dict): max results per items type
            exploration_mode (bool | dict[type, bool]): get from different artists

        Returns:
            tuple of recommended DeezerResource
        """
        if not item_:
            return set()
        if exploration_mode is None:
            exploration_mode = {t: False for t in limit_per_type.keys()}

        all_results = set()
        factory_ = ResourceFactory(resource=item_)
        if limit := limit_per_type.get(ValidItem.TRACK.value):
            if not exploration_mode[ValidItem.TRACK.value]:
                all_results.update(
                    set(
                        factory_.dive(target_type=ValidItem.TRACK, limit=limit)
                    )
                )
            else:
                all_results.update(
                    set(
                        factory_.explore(
                            target_type=ValidItem.TRACK, limit=limit
                        )
                    )
                )
        if limit := limit_per_type.get(ValidItem.ALBUM.value):
            # get artists albums
            if not exploration_mode[ValidItem.ALBUM.value]:
                all_results.update(
                    set(
                        factory_.dive(target_type=ValidItem.ALBUM, limit=limit)
                    )
                )
            else:
                all_results.update(
                    set(
                        factory_.explore(
                            target_type=ValidItem.ALBUM, limit=limit
                        )
                    )
                )
        if limit := limit_per_type.get(ValidItem.ARTIST.value):
            if not exploration_mode[ValidItem.ARTIST.value]:
                all_results.update(
                    set(
                        factory_.dive(
                            target_type=ValidItem.ARTIST, limit=limit
                        )
                    )
                )
            else:
                all_results.update(
                    set(
                        factory_.explore(
                            target_type=ValidItem.ARTIST, limit=limit
                        )
                    )
                )
        return all_results
