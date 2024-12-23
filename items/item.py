"""
Deezer Items classes for parsing, control and styling

Contains:
    - ValiItem: all possible deezer item types
    - DeezerItem (parent class)
    - one class for each deezer item type
"""

import random
from enum import Enum
from math import sqrt
from typing import Annotated, Any, Dict, List, Tuple

import deezer  # type: ignore
from commons import scale_weights
from config import NodeColor
from deezer.exceptions import DeezerErrorResponse  # type: ignore
from pydantic import BaseModel
from pydantic.functional_validators import BeforeValidator

# -- Validators --


def is_deezer_resource(v: Any):
    if not isinstance(v, deezer.Resource):
        raise ValueError("not a deezer resource")
    return v


DeezerResource = Annotated[Any, BeforeValidator(is_deezer_resource)]


# -- Utils --


class ValidItem(Enum):  # should match deezer types
    ALBUM = "album"
    ARTIST = "artist"
    PLAYLIST = "playlist"
    TRACK = "track"
    SHOW = "show"
    EPISODE = "episode"
    AUDIOBOOK = "audiobook"


POPULARITY_THRESHOLDS: Dict[str, int] = {
    ValidItem.ARTIST.value: int(2e4),
    ValidItem.ALBUM.value: int(2e3),
    ValidItem.TRACK.value: int(1e4),
}

POPULARITY_UPPERS: Dict[str, int] = {
    ValidItem.ARTIST.value: int(12e6),  # Taylor Swift (2023)
    ValidItem.ALBUM.value: int(2e5),  # Bad Bunny - Un Verano Sin Ti (2023)
    ValidItem.TRACK.value: int(1e6),  # Known upper limit
}

# -- Classes --


class ResourceFactory(BaseModel):
    """
    Helper around deezer.Resource subclasses

    Warning: deezer connector fetches foreign attributes.
    To avoid API call, convert to dict
    """

    resource: DeezerResource

    def __hash__(self):
        return self.resource.id

    def __eq__(self, other):
        return self.resource.id == other.resource.id

    def to_type(self, target_type: ValidItem) -> List[DeezerResource]:
        """
        Convert to target type
        Args:
            target_type (ValidItem)

        Returns:
            (List[DeezerResource]) from self.resource
        """
        if target_type == ValidItem.ALBUM:
            return [self._album]
        if target_type == ValidItem.ARTIST:
            return self._artists
        if target_type == ValidItem.TRACK:
            return [self._track]
        raise NotImplementedError(
            "[ResourceFactory.to_type]"
            f" Target type {target_type.value} not supported"
        )

    def get_target_label(self, target_type: ValidItem) -> str:
        """
        Get label of target_type from another type.
        E.g. get artist name from self.resource being a track
        Args:
            target_type (ValidItem): label should be one of this type

        Returns:
            label as string
        """
        if self.resource.type == target_type.value:
            return self.label

        if target_type == ValidItem.ALBUM:
            if isinstance(self.resource, deezer.Artist):
                # first album name
                return ResourceFactory(
                    resource=self.resource.get_albums(limit=1)[0]
                ).label
            if isinstance(self.resource, deezer.Track):
                return ResourceFactory(resource=self.resource.album).label

        if target_type == ValidItem.ARTIST:
            if isinstance(self.resource, deezer.Album):
                return ResourceFactory(resource=self.resource.artist).label
            if isinstance(self.resource, deezer.Track):
                return ResourceFactory(resource=self.resource.artist).label

        if target_type == ValidItem.TRACK:
            if isinstance(self.resource, deezer.Album):
                return ResourceFactory(resource=self.resource.tracks[0]).label
            if isinstance(self.resource, deezer.Artist):
                return ResourceFactory(
                    resource=self.resource.get_top(limit=1)[0]
                ).label

        raise NotImplementedError(
            "[ResourceFactory.get_target_label]"
            f" Target type {target_type.value} not supported"
            f" for resource of type {self.resource.type}"
        )

    @property
    def label(self) -> str:
        if isinstance(self.resource, deezer.Artist):
            return self.resource.name
        if isinstance(self.resource, deezer.Album | deezer.Track):
            return self.resource.title
        raise NotImplementedError(
            "[ResourceFactory.label]"
            f" {self.resource.__class__} not supported for label property"
        )

    @property
    def full_name(self):
        name = self.label
        if isinstance(self.resource, deezer.Album):
            artist_names = [
                self.resource.as_dict()["artist"]["name"]
            ]  # [c.name for c in self.resource.contributors]
            return f"{name} {' '.join(artist_names)}"
        if isinstance(self.resource, deezer.Track):
            artist_names = [
                self.resource.as_dict()["artist"]["name"]
            ]  # [c.name for c in self.resource.contributors]
            album_name = self.resource.as_dict()["album"]["title"]
            return f"{name} {' '.join(artist_names)} {album_name}"
        return name  # Artist

    @property
    def title(self) -> str:
        if isinstance(self.resource, deezer.Artist):
            return self._artist_title
        if isinstance(self.resource, deezer.Album):
            return self._album_title
        if isinstance(self.resource, deezer.Track):
            return self._track_title
        raise NotImplementedError(
            "[ResourceFactory.title]"
            f" {self.resource.__class__} not supported for title property"
        )

    @property
    def artist_ids(self) -> Tuple[int]:
        if isinstance(self.resource, deezer.Artist):
            return (self.resource.id,)
        if isinstance(self.resource, deezer.Album | deezer.Track):
            return tuple(a["id"] for a in self.resource.as_dict()["contributors"])  # type: ignore
        raise NotImplementedError(
            "[ResourceFactory.artist_ids]"
            f" {self.resource.__class__} not supported for artist_ids property"
        )

    def dive(
        self, target_type: ValidItem, limit: int = 5
    ) -> Tuple[DeezerResource]:
        """
        Get more content from same artist(s)
        Args:
            target_type (ValidItem): artist, track or album
            limit (int): how many items to return

        Returns:
            List[DeezerResource] of size <= limit
        """
        if target_type == ValidItem.ARTIST:
            return tuple(self._artists[:limit])  # type: ignore
        current_artists = self._artists
        per_artist = [
            {
                "artist": artist,
                "limit": weight,
            }
            for artist, weight in zip(
                current_artists[:limit],
                scale_weights(
                    [1] * min(len(current_artists), limit), target_sum=limit
                ),
            )
        ]
        found = []
        for params in per_artist:
            if params["limit"] < 1:
                continue
            if target_type == ValidItem.ALBUM:
                all_albums = list(params["artist"].get_albums())
                found.extend(
                    random.sample(all_albums, params["limit"])
                    if params["limit"] < len(all_albums)
                    else all_albums
                )
            elif target_type == ValidItem.TRACK:
                try:
                    radio_tracks = list(
                        params["artist"].get_top()
                    )  # fixMe: get_radio has a bug. it gives the calling artist as the artist
                except DeezerErrorResponse:
                    continue
                found.extend(
                    random.sample(radio_tracks, params["limit"])
                    if params["limit"] < len(radio_tracks)
                    else radio_tracks
                )
            else:
                raise NotImplementedError(
                    "[ResourceFactory.dive]"
                    f" {target_type.value} not supported as a target type"
                )
        return tuple(found)  # type: ignore

    def explore(
        self, target_type: ValidItem, limit: int = 5
    ) -> Tuple[DeezerResource]:
        """
        Get more content from same artist(s)
        Args:
            target_type (ValidItem): artist, track or album
            limit (int): how many items to return

        Returns:
            List[DeezerResource] of size <= limit
        """
        current_artists = self._artists
        if target_type == ValidItem.ARTIST:
            all_related = set(
                [
                    related_artist
                    for artist in current_artists
                    for related_artist in artist.get_related()
                ]
            )
            # set order will randomize itself
            return tuple(list(all_related)[:limit])  # type: ignore

        per_artist = [
            {
                "artist": artist,
                "limit": limit,
            }
            for artist, weight in zip(
                current_artists[:limit],
                scale_weights(
                    [1] * min(len(current_artists), limit), target_sum=limit
                ),
            )
        ]
        related_items = [
            ResourceFactory(resource=params["artist"]).dive(
                target_type=target_type, limit=params["limit"]
            )
            for params in per_artist
        ]
        return tuple(  # type: ignore
            item_ for items_ in related_items for item_ in items_
        )

    @property
    def _album(self) -> deezer.Album:
        if isinstance(self.resource, deezer.Album):
            return self.resource
        if isinstance(self.resource, deezer.Track):
            return self.resource.album.get()
        if isinstance(self.resource, deezer.Artist):
            return self.resource.get_albums()[0]
        raise NotImplementedError(
            "[ResourceFactory._album]"
            f" {self.resource.__class__} not supported for artist_ids property"
        )

    @property
    def _track(self):
        if isinstance(self.resource, deezer.Track):
            return self.resource
        if isinstance(self.resource, deezer.Album):
            return self.resource.get_tracks()[0]
        if isinstance(self.resource, deezer.Artist):
            return self.resource.get_top()[0]
        raise NotImplementedError(
            "[ResourceFactory._track]"
            f" {self.resource.__class__} not supported for artist_ids property"
        )

    @property
    def _artists(self) -> List[deezer.Artist]:
        if isinstance(self.resource, deezer.Artist):
            return [self.resource]
        if isinstance(self.resource, deezer.Album | deezer.Track):
            return [a.get() for a in self.resource.contributors]
        raise NotImplementedError(
            "[ResourceFactory.artists]"
            f" {self.resource.__class__} not supported for artist_ids property"
        )

    @property
    def preview_url(self) -> str | None:
        if isinstance(self.resource, deezer.Track):
            return self.resource.preview
        return None

    @property
    def image(self) -> str | None:
        if isinstance(self.resource, deezer.Artist):
            return self.resource.picture_medium
        if isinstance(self.resource, deezer.Album):
            return self.resource.cover_medium
        if isinstance(self.resource, deezer.Track):
            return None  # no image for tracks
        raise NotImplementedError(
            "[ResourceFactory.image]"
            f" {self.resource.__class__} not supported for image property"
        )

    @property
    def popularity_indicator(self) -> int:
        if isinstance(self.resource, deezer.Track):
            return self.resource.rank
        if isinstance(self.resource, deezer.Artist):
            return self.resource.nb_fan
        if isinstance(self.resource, deezer.Album):
            return self.resource.fans

        raise NotImplementedError(
            "[ResourceFactory.popularity_indicator]"
            f" {self.resource.__class__} not supported for popularity property"
        )

    @property
    def popularity_upper(self):
        return POPULARITY_UPPERS[self.resource.type]

    @property
    def popularity_distance(self) -> int:
        return self.popularity_indicator - self.popularity_threshold

    @property
    def popularity(
        self,
    ) -> (
        int
    ):  # fixMe - not very contrasted, add some kind of log function for artist
        """is a percent"""
        return int(
            sqrt(self.popularity_indicator / self.popularity_upper) * 100
        )

    @property
    def popularity_threshold(self) -> int:
        return POPULARITY_THRESHOLDS[self.resource.type]

    @property
    def node_color(self) -> str:
        return NodeColor.PRIMARY.value  # default

    @property
    def _artist_title(self) -> str:
        return f"Artist - {self.resource.name}"

    @property
    def _album_title(self) -> str:
        return (
            f"Album - {self.resource.title}\n"
            f" by {','.join([a.name for a in self.resource.contributors])}\n"
            f" released on {self.resource.release_date}"
        )

    @property
    def _track_title(self) -> str:
        return (
            f"Track - {self.resource.title}\n"
            f"by {','.join([a.name for a in self.resource.contributors])}"
        )
