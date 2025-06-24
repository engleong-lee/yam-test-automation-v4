"""
Strategy for finding form field elements (inputs, textareas, selects)
"""

from typing import List, Tuple
from ..base import ElementFinderStrategy, ElementMatch, FinderContext


class FormFieldStrategy(ElementFinderStrategy):
    """Strategy specialized for form field elements"""
    
    def __init__(self):
        super().__init__(priority=80)  # High priority for form fields
    
    def can_handle(self, context: FinderContext) -> bool:
        """Check if this is a form field request"""
        field_indicators = ['field', 'input', 'email', 'password', 'name', 'address', 'phone']
        return any(indicator in context.description.lower() for indicator in field_indicators)
    
    def get_selectors(self, context: FinderContext) -> List[Tuple[str, str]]:
        """Get selectors for form fields"""
        return [
            ('input[type="text"], input[type="email"], input[type="password"], input:not([type]), textarea', 'text inputs'),
            ('input, textarea, select', 'all form fields'),
        ]
    
    def find_elements(self, context: FinderContext) -> List[ElementMatch]:
        """Find form field elements"""
        matches = []
        
        for selector, desc in self.get_selectors(context):
            try:
                elements = context.page.query_selector_all(selector)
                if context.debug:
                    print(f"  → FormField: Found {len(elements)} elements using {desc}")
                
                for element in elements:
                    match = self.score_element(element, context)
                    if match:
                        matches.append(match)
                        
            except Exception as e:
                if context.debug:
                    print(f"  → FormField selector failed: {e}")
        
        return matches
    
    def extract_element_text(self, element, context: FinderContext) -> str:
        """Enhanced text extraction for form fields"""
        # Try multiple strategies for form field text
        texts = []
        
        # 1. Placeholder text
        placeholder = element.get_attribute('placeholder')
        if placeholder:
            texts.append(placeholder.strip())
        
        # 2. Associated label using multiple strategies
        label_text = self._get_associated_label_text(element, context)
        if label_text:
            texts.append(label_text)
        
        # 3. aria-label
        aria_label = element.get_attribute('aria-label')
        if aria_label:
            texts.append(aria_label.strip())
        
        # 4. name/id attributes (converted to readable form)
        name = element.get_attribute('name')
        if name:
            readable_name = self._convert_attribute_to_text(name)
            if readable_name:
                texts.append(readable_name)
        
        element_id = element.get_attribute('id')
        if element_id:
            readable_id = self._convert_attribute_to_text(element_id)
            if readable_id:
                texts.append(readable_id)
        
        # Return the first non-empty text found
        return next((text for text in texts if text), '')
    
    def _get_associated_label_text(self, element, context: FinderContext) -> str:
        """Get label text associated with form field using multiple strategies"""
        try:
            # Strategy 1: label[for] attribute
            element_id = context.page.evaluate('(el) => el.id', element)
            if element_id:
                label = context.page.query_selector(f'label[for="{element_id}"]')
                if label:
                    label_text = label.text_content()
                    if label_text:
                        return label_text.strip()
            
            # Strategy 2: wrapped in label
            parent_label = context.page.evaluate('''(el) => {
                let parent = el.parentElement;
                let depth = 0;
                while (parent && parent.tagName !== 'LABEL' && parent.tagName !== 'BODY' && depth < 3) {
                    parent = parent.parentElement;
                    depth++;
                }
                return parent && parent.tagName === 'LABEL' ? parent.textContent : null;
            }''', element)
            if parent_label:
                return parent_label.strip()
            
            # Strategy 3: sibling label
            sibling_label = context.page.evaluate('''(el) => {
                let parent = el.parentElement;
                if (parent) {
                    let sibling = parent.previousElementSibling;
                    if (sibling && sibling.tagName === 'LABEL') {
                        return sibling.textContent;
                    }
                    // Check parent's parent too
                    if (parent.parentElement) {
                        sibling = parent.parentElement.previousElementSibling;
                        if (sibling && sibling.tagName === 'LABEL') {
                            return sibling.textContent;
                        }
                    }
                }
                return null;
            }''', element)
            if sibling_label:
                return sibling_label.strip()
                
        except Exception as e:
            if context.debug:
                print(f"  → Error getting label text: {e}")
        
        return ''
    
    def _convert_attribute_to_text(self, attr_value: str) -> str:
        """Convert attribute value to readable text"""
        if not attr_value:
            return ''
        
        # Common meaningful attributes for form fields
        meaningful_terms = ['email', 'password', 'name', 'phone', 'address', 'city', 'zip']
        attr_lower = attr_value.lower()
        
        if any(term in attr_lower for term in meaningful_terms):
            # Convert camelCase and underscore/dash separated to readable text
            import re
            readable = attr_value.replace('_', ' ').replace('-', ' ')
            readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', readable)
            return ' '.join(word.capitalize() for word in readable.split())
        
        return ''
    
    def get_score_threshold(self) -> float:
        """Lower threshold for form fields as they often have partial matches"""
        return 0.3
    
    def get_strategy_bonus(self) -> float:
        """Bonus points for form field matches"""
        return 0.2