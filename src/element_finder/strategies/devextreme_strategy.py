"""
Strategy specialized for DevExtreme UI framework elements
"""

from typing import List, Tuple
from ..base import ElementFinderStrategy, ElementMatch, FinderContext


class DevExtremeStrategy(ElementFinderStrategy):
    """Strategy specialized for DevExtreme UI components"""
    
    def __init__(self):
        super().__init__(priority=90)  # Highest priority for DevExtreme elements
    
    def can_handle(self, context: FinderContext) -> bool:
        """Check if page uses DevExtreme or description suggests DevExtreme elements"""
        # Check if page has DevExtreme classes/elements
        try:
            has_dx_elements = context.page.query_selector('[class*="dx-"]') is not None
            if has_dx_elements:
                return True
        except:
            pass
        
        # Check for dropdown/select type descriptions that often use DevExtreme
        dropdown_indicators = ['dropdown', 'select', 'type', 'category', 'choose']
        # Also handle menu items like logout, login, etc. that might be in DevExtreme menus
        menu_indicators = ['logout', 'login', 'menu', 'profile', 'switch']
        return (any(indicator in context.description.lower() for indicator in dropdown_indicators) or 
                any(indicator in context.description.lower() for indicator in menu_indicators))
    
    def get_selectors(self, context: FinderContext) -> List[Tuple[str, str]]:
        """Get selectors for DevExtreme components"""
        return [
            ('.dx-list-item-content', 'DevExtreme list item content'),
            ('.dx-item-content', 'DevExtreme item content'),
            ('[class*="dx-selectbox"], [class*="dx-dropdowneditor"]', 'DevExtreme dropdowns'),
            ('[class*="dx-button"]', 'DevExtreme buttons'),
            ('[class*="dx-menu-item-text"]', 'DevExtreme menu item text'),
            ('[class*="dx-textbox"], [class*="dx-texteditor"]', 'DevExtreme text inputs'),
            ('[role="option"]', 'dropdown option elements'),
            ('[class*="dx-"]', 'all DevExtreme components'),
            ('[role="combobox"]', 'combobox elements'),
        ]
    
    def find_elements(self, context: FinderContext) -> List[ElementMatch]:
        """Find DevExtreme elements"""
        matches = []
        
        for selector, desc in self.get_selectors(context):
            try:
                elements = context.page.query_selector_all(selector)
                if context.debug:
                    print(f"  → DevExtreme: Found {len(elements)} elements using {desc}")
                
                for element in elements:
                    match = self.score_element(element, context)
                    if match:
                        matches.append(match)
                        
                        # Early termination for exact matches in dropdown list items
                        element_text = self.extract_element_text(element, context).lower()
                        if (element_text == context.description.lower() and 
                            ('dx-list-item-content' in (element.get_attribute('class') or '') or
                             'dx-item-content' in (element.get_attribute('class') or ''))):
                            if context.debug:
                                print(f"  → Exact match in dropdown list item found (score: {match.score:.2f})")
                            match.score = max(match.score, 0.95)  # Boost score for exact matches
                            return [match]
                        
                        # Early termination for high-confidence DevExtreme matches
                        if match.score >= 0.85:
                            if context.debug:
                                print(f"  → High-confidence DevExtreme match found (score: {match.score:.2f})")
                            return [match]
                        
            except Exception as e:
                if context.debug:
                    print(f"  → DevExtreme selector failed: {e}")
        
        return matches
    
    def extract_element_text(self, element, context: FinderContext) -> str:
        """Enhanced text extraction for DevExtreme components"""
        texts = []
        
        # 1. Title attribute (very common in DevExtreme components)
        title_attr = element.get_attribute('title')
        if title_attr:
            texts.append(title_attr.strip())
        
        # 2. For DevExtreme combobox inputs, check parent container's title and associated label
        element_role = element.get_attribute('role')
        tag_name = element.evaluate('el => el.tagName.toLowerCase()')
        
        if element_role == 'combobox' and tag_name == 'input':
            try:
                # Look for parent title
                parent_title = element.evaluate('''(el) => {
                    let parent = el.parentElement;
                    while (parent && parent !== document.body) {
                        if (parent.title) {
                            return parent.title;
                        }
                        parent = parent.parentElement;
                    }
                    return null;
                }''')
                if parent_title:
                    texts.append(parent_title.strip())
                
                # Look for associated label in the same row/container
                associated_label = element.evaluate('''(el) => {
                    // Find the dx-selectbox container
                    let container = el.closest('.dx-selectbox, .dx-dropdowneditor');
                    if (!container) return null;
                    
                    // Look for label in the same row (common pattern for forms)
                    let row = container.closest('.row, .form-group, .col-md-19, [class*="col-"]');
                    if (row) {
                        let label = row.querySelector('label');
                        if (label && label.textContent) {
                            return label.textContent.trim();
                        }
                    }
                    
                    // Look for label as a sibling element
                    let parent = container.parentElement;
                    if (parent) {
                        let label = parent.querySelector('label');
                        if (label && label.textContent) {
                            return label.textContent.trim();
                        }
                    }
                    
                    return null;
                }''')
                if associated_label:
                    texts.append(associated_label.strip())
                    
            except:
                pass
        
        # 3. aria-label
        aria_label = element.get_attribute('aria-label')
        if aria_label:
            texts.append(aria_label.strip())
        
        # 4. Convert DevExtreme ID/class to readable text
        element_class = element.get_attribute('class') or ''
        element_id = element.get_attribute('id') or ''
        
        if 'dx-selectbox' in element_class.lower() or 'dx-dropdowneditor' in element_class.lower():
            if element_id:
                readable_text = self._convert_dx_id_to_text(element_id)
                if readable_text:
                    texts.append(readable_text)
        
        # 5. DevExtreme button text patterns
        if 'dx-button' in element_class.lower():
            try:
                button_text = element.evaluate('''(el) => {
                    const textSpan = el.querySelector('.dx-button-text');
                    if (textSpan && textSpan.textContent) {
                        return textSpan.textContent.trim();
                    }
                    return el.textContent ? el.textContent.trim() : '';
                }''')
                if button_text:
                    texts.append(button_text)
            except:
                pass
        
        # 5b. DevExtreme menu item text patterns
        if 'dx-menu-item-text' in element_class.lower():
            try:
                # For dx-menu-item-text spans, the text content is the primary source
                menu_text = element.text_content()
                if menu_text and menu_text.strip():
                    texts.append(menu_text.strip())
            except:
                pass
        
        # 5c. DevExtreme list item content patterns
        if 'dx-list-item-content' in element_class.lower() or 'dx-item-content' in element_class.lower():
            try:
                # For dx-list-item-content divs, the text content is the primary source
                item_text = element.text_content()
                if item_text and item_text.strip():
                    texts.append(item_text.strip())
            except:
                pass
        
        # 6. Standard text content and attributes
        text_content = element.text_content()
        if text_content:
            texts.append(text_content.strip())
        
        placeholder = element.get_attribute('placeholder')
        if placeholder:
            texts.append(placeholder.strip())
        
        # Return the first meaningful text found
        return next((text for text in texts if text and len(text.strip()) > 0), '')
    
    def _convert_dx_id_to_text(self, element_id: str) -> str:
        """Convert DevExtreme element ID to readable text"""
        if not element_id:
            return ''
        
        # Convert camelCase ID to readable text
        import re
        readable_id = element_id.replace('_', ' ').replace('-', ' ')
        # Split camelCase (e.g., "clientType" -> "client Type")
        readable_id = re.sub(r'([a-z])([A-Z])', r'\1 \2', readable_id)
        # Capitalize first letter of each word
        readable_id = ' '.join(word.capitalize() for word in readable_id.split())
        
        # Only return if it looks meaningful
        if len(readable_id.strip()) > 2 and readable_id.strip().lower() != element_id.lower():
            return readable_id.strip()
        
        return ''
    
    def get_score_threshold(self) -> float:
        """Lower threshold for DevExtreme elements as they often have partial matches"""
        return 0.3
    
    def get_strategy_bonus(self) -> float:
        """High bonus for DevExtreme matches since they're framework-specific"""
        return 0.4