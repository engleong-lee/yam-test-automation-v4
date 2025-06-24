"""
Strategy for finding menu item and navigation elements
"""

from typing import List, Tuple
from ..base import ElementFinderStrategy, ElementMatch, FinderContext


class MenuItemStrategy(ElementFinderStrategy):
    """Strategy specialized for menu items and navigation elements"""
    
    def __init__(self):
        super().__init__(priority=75)  # High priority for menu items
    
    def can_handle(self, context: FinderContext) -> bool:
        """Check if this is a menu item request"""
        menu_indicators = ['menu', 'nav', 'item', 'option', 'logout', 'profile']
        return any(indicator in context.description.lower() for indicator in menu_indicators)
    
    def get_selectors(self, context: FinderContext) -> List[Tuple[str, str]]:
        """Get selectors for menu items"""
        return [
            ('[role="menuitem"], [role="option"]', 'ARIA menu items'),
            ('.dx-menu-item-text', 'DevExtreme menu item text'),
            ('nav a, nav button, nav li', 'navigation elements'),
            ('[class*="menu"] a, [class*="menu"] button, [class*="menu"] li', 'menu-styled elements'),
            ('li a, li button, li span[onclick]', 'list item links/buttons'),
        ]
    
    def find_elements(self, context: FinderContext) -> List[ElementMatch]:
        """Find menu item elements"""
        matches = []
        
        for selector, desc in self.get_selectors(context):
            try:
                elements = context.page.query_selector_all(selector)
                if context.debug:
                    print(f"  → MenuItem: Found {len(elements)} elements using {desc}")
                
                for element in elements:
                    match = self.score_element(element, context)
                    if match:
                        matches.append(match)
                        
                        # Early termination for high-confidence menu item matches
                        if match.score >= 0.8 and 'menuitem' in (element.get_attribute('role') or ''):
                            if context.debug:
                                print(f"  → High-confidence menu item match found (score: {match.score:.2f})")
                            return [match]
                        
            except Exception as e:
                if context.debug:
                    print(f"  → MenuItem selector failed: {e}")
        
        return matches
    
    def extract_element_text(self, element, context: FinderContext) -> str:
        """Enhanced text extraction for menu items"""
        # Menu items usually have their text directly in text content
        text_content = element.text_content()
        if text_content:
            return text_content.strip()
        
        # Try aria-label for complex menu items
        aria_label = element.get_attribute('aria-label')
        if aria_label:
            return aria_label.strip()
        
        # Try title attribute
        title = element.get_attribute('title')
        if title:
            return title.strip()
        
        return ''
    
    def get_score_threshold(self) -> float:
        """Standard threshold for menu items"""
        return 0.5
    
    def get_strategy_bonus(self) -> float:
        """High bonus for menu item matches"""
        return 0.3