import deezer
from deezer import Artist, PaginatedList

DEFAULT_LIMIT = 5


class DeezerClientWithLimit(deezer.Client):
    def test(self):
        return self.request(
            method="GET",
            path="search",
            params={"q": "sza", "limit": 10},
            paginate_list=False,
        )

    def search_artists(
        self,
        query: str = "",
        strict: bool | None = None,
        ordering: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> PaginatedList[Artist]:
        return self._search(
            path="artist",
            query=query,
            strict=strict,
            ordering=ordering,
            limit=limit,
        )

    def search(
        self,
        query: str = "",
        strict: bool | None = None,
        ordering: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        track: str | None = None,
        label: str | None = None,
        dur_min: int | None = None,
        dur_max: int | None = None,
        bpm_min: int | None = None,
        bpm_max: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ):
        """
        Search tracks.

        Advanced search is available by either formatting the query yourself or
        by using the dedicated keywords arguments.

        :param query: the query to search for, this is directly passed as q query.
        :param strict: whether to disable fuzzy search and enable strict mode.
        :param ordering: see Deezer API docs for possible values.
        :param artist: parameter for the advanced search feature.
        :param album: parameter for the advanced search feature.
        :param track: parameter for the advanced search feature.
        :param label: parameter for the advanced search feature.
        :param dur_min: parameter for the advanced search feature.
        :param dur_max: parameter for the advanced search feature.
        :param bpm_min: parameter for the advanced search feature.
        :param bpm_max: parameter for the advanced search feature.
        :returns: a list of :class:`~deezer.Track` instances.
        """
        return self._search(
            "",
            query=query,
            strict=strict,
            ordering=ordering,
            artist=artist,
            album=album,
            track=track,
            label=label,
            dur_min=dur_min,
            dur_max=dur_max,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            limit=limit,
        )

    def search_albums(
        self,
        query: str = "",
        strict: bool | None = None,
        ordering: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> PaginatedList[deezer.Album]:
        """
        Search albums matching the given query.

        :param query: the query to search for, this is directly passed as q query.
        :param strict: whether to disable fuzzy search and enable strict mode.
        :param ordering: see Deezer API docs for possible values.
        :return: list of :class:`~deezer.Album` instances.
        """
        return self._search(
            path="album",
            query=query,
            strict=strict,
            ordering=ordering,
            limit=limit,
        )

    def _search(
        self,
        path: str,
        query: str = "",
        strict: bool | None = None,
        ordering: str | None = None,
        limit: int | None = None,
        **advanced_params: str | int | None,
    ):
        optional_params = {}
        if strict is True:
            optional_params["strict"] = "on"
        if ordering:
            optional_params["ordering"] = ordering
        if limit:
            optional_params["limit"] = limit
        query_parts = []
        if query:
            query_parts.append(query)
        query_parts.extend(
            f'{param_name}:"{param_value}"'
            for param_name, param_value in advanced_params.items()
            if param_value
        )

        return self._get_paginated_list(
            path=f"search/{path}" if path else "search",
            params={
                "q": " ".join(query_parts),
                **optional_params,
            },
        )


deezer_client = deezer.Client()  # DeezerClientWithLimit()
