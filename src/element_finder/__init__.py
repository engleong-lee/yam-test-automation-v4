"""
Enhanced Element Finder System

A modular, high-performance element finder that replaces the monolithic find_element method
with a strategy-based approach supporting multiple UI frameworks and caching.
"""

from .base import ElementFinderStrategy, ElementMatch, FinderContext
from .hybrid_finder import HybridElementFinder
from .strategies import (
    FormFieldStrategy,
    ButtonStrategy, 
    DevExtremeStrategy,
    MenuItemStrategy,
    GenericStrategy
)
from .cache import ElementCache
from .page_model import AutoDiscoveryPageModel

__all__ = [
    'ElementFinderStrategy',
    'ElementMatch', 
    'FinderContext',
    'HybridElementFinder',
    'FormFieldStrategy',
    'ButtonStrategy',
    'DevExtremeStrategy', 
    'MenuItemStrategy',
    'GenericStrategy',
    'ElementCache',
    'AutoDiscoveryPageModel'
]