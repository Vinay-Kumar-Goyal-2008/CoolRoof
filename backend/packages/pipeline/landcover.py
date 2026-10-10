"""ESA WorldCover class codes (D6) [R: WorldCover v200 product legend]."""

from __future__ import annotations

from enum import IntEnum

__all__ = ["WorldCover"]


class WorldCover(IntEnum):
    TREE = 10
    SHRUB = 20
    GRASS = 30
    CROPLAND = 40
    BUILT = 50
    BARE = 60
    SNOW = 70
    WATER = 80
    WETLAND = 90
    MANGROVE = 95
    MOSS = 100

    @classmethod
    def vegetation(cls) -> tuple[WorldCover, ...]:
        return (cls.TREE, cls.SHRUB, cls.GRASS)

    @classmethod
    def rural_reference(cls) -> tuple[WorldCover, ...]:
        """Spec M6: reference mask is cropland / tree."""
        return (cls.CROPLAND, cls.TREE)
