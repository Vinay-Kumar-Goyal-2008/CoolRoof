"""External dependencies behind interfaces, each with a local and an AWS implementation.

Selected by ``RUNTIME=local|aws`` in :func:`packages.adapters.registry.build_adapters`.
Data-source adapters (Landsat, NWP, solar, FIRMS) live next to the modules that
use them and follow the same fixture/live pattern.
"""

from packages.adapters.registry import Adapters, build_adapters

__all__ = ["Adapters", "build_adapters"]
