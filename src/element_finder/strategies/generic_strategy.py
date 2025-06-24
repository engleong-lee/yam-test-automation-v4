"""
Generic fallback strategy for any interactive elements
"""

from typing import List, Tuple
from ..base import ElementFinderStrategy, ElementMatch, FinderContext


class GenericStrategy(ElementFinderStrategy):
    """Fallback strategy that can handle any interactive element"""
    
    def __init__(self):
        super().__init__(priority=10)  # Lowest priority - fallback only
    
    def can_handle(self, context: FinderContext) -> bool:
        """Generic strategy can handle any request as fallback"""
        return True
    
    def get_selectors(self, context: FinderContext) -> List[Tuple[str, str]]:
        """Get broad selectors for any interactive elements"""
        return [
            ('input, button, textarea, select, a[href]', 'standard interactive elements'),
            ('[role="button"], [role="menuitem"], [role="option"], [role="combobox"]', 'ARIA interactive elements'),
            ('[onclick], [tabindex]', 'clickable elements'),
            ('div[class*="button"], div[class*="menu"], div[class*="item"]', 'styled interactive elements'),
            ('*', 'all elements')  # Last resort
        ]
    
    def find_elements(self, context: FinderContext) -> List[ElementMatch]:
        """Find elements using broad selectors"""
        matches = []
        
        for selector, desc in self.get_selectors(context):
            try:
                elements = context.page.query_selector_all(selector)
                if context.debug:
                    print(f"  → Generic: Found {len(elements)} elements using {desc}")
                
                # Limit processing for very broad selectors
                max_elements = 50 if selector != '*' else 20
                
                for i, element in enumerate(elements[:max_elements]):
                    if not element.is_visible():
                        continue
                        
                    match = self.score_element(element, context)
                    if match:
                        matches.append(match)
                        
                        # Early termination for high-confidence matches
                        if match.score >= 0.9:
                            if context.debug:
                                print(f"  → High-confidence generic match found (score: {match.score:.2f})")
                            return [match]
                
                # If we found decent matches, don't continue to broader selectors
                if matches and selector != '*':
                    break
                        
            except Exception as e:
                if context.debug:
                    print(f"  → Generic selector failed: {e}")
        
        return matches
    
    def extract_element_text(self, element, context: FinderContext) -> str:
        """Comprehensive text extraction for any element"""
        texts = []
        
        # Try all common text sources
        text_content = element.text_content()
        if text_content:
            texts.append(text_content.strip())
        
        aria_label = element.get_attribute('aria-label')
        if aria_label:
            texts.append(aria_label.strip())
        
        title = element.get_attribute('title')
        if title:
            texts.append(title.strip())
        
        value = element.get_attribute('value')
        if value:
            texts.append(value.strip())
        
        placeholder = element.get_attribute('placeholder')
        if placeholder:
            texts.append(placeholder.strip())
        
        # For generic elements, also try alt text
        alt = element.get_attribute('alt')
        if alt:
            texts.append(alt.strip())
        
        # Return the first meaningful text
        return next((text for text in texts if text and len(text.strip()) > 0), '')
    
    def get_score_threshold(self) -> float:
        """Higher threshold for generic strategy to reduce false positives"""
        return 0.6
    
    def get_strategy_bonus(self) -> float:
        """No bonus for generic matches"""
        return 0.0