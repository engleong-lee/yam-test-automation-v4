"""
Element finder strategies for different UI patterns and frameworks
"""

from .form_field_strategy import FormFieldStrategy
from .button_strategy import ButtonStrategy
from .devextreme_strategy import DevExtremeStrategy
from .menu_item_strategy import MenuItemStrategy
from .generic_strategy import GenericStrategy

__all__ = [
    'FormFieldStrategy',
    'ButtonStrategy', 
    'DevExtremeStrategy',
    'MenuItemStrategy',
    'GenericStrategy'
]