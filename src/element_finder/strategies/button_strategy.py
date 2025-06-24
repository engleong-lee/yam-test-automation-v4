"""
Strategy for finding button elements
"""

from typing import List, Tuple, Optional
from ..base import ElementFinderStrategy, ElementMatch, FinderContext


class ButtonStrategy(ElementFinderStrategy):
    """Strategy specialized for button elements"""
    
    def __init__(self):
        super().__init__(priority=85)  # High priority for buttons
    
    def can_handle(self, context: FinderContext) -> bool:
        """Check if this is a button request"""
        button_indicators = ['button', 'click', 'submit', 'login', 'save', 'next', 'back']
        return any(indicator in context.description.lower() for indicator in button_indicators)
    
    def get_selectors(self, context: FinderContext) -> List[Tuple[str, str]]:
        """Get selectors for buttons"""
        return [
            ('button, input[type="button"], input[type="submit"]', 'native buttons'),
            ('div[role="button"], a[role="button"], span[role="button"]', 'role-based buttons'),
            ('a[class*="button"], a[class*="btn"]', 'link buttons'),
            ('[class*="button"]:not([class*="container"]):not([class*="wrapper"]), [class*="btn"]:not([class*="container"]):not([class*="wrapper"])', 'styled buttons'),
            ('[onclick], [tabindex]', 'clickable elements'),
        ]
    
    def find_elements(self, context: FinderContext) -> List[ElementMatch]:
        """Find button elements"""
        matches = []
        
        for selector, desc in self.get_selectors(context):
            try:
                elements = context.page.query_selector_all(selector)
                if context.debug:
                    print(f"  → Button: Found {len(elements)} elements using {desc}")
                
                for element in elements:
                    match = self.score_element(element, context)
                    if match:
                        matches.append(match)
                        
                        # Early termination for high-confidence button matches
                        if match.score >= 0.9:
                            if context.debug:
                                print(f"  → High-confidence button match found (score: {match.score:.2f})")
                            return [match]  # Return immediately for excellent matches
                        
            except Exception as e:
                if context.debug:
                    print(f"  → Button selector failed: {e}")
        
        return matches
    
    def extract_element_text(self, element, context: FinderContext) -> str:
        """Enhanced text extraction for buttons with container detection"""
        # Try multiple strategies for button text
        texts = []
        
        # 1. aria-label (often most reliable for complex buttons)
        aria_label = element.get_attribute('aria-label')
        if aria_label:
            texts.append(aria_label.strip())
        
        # 2. Nested text patterns (for complex button structures)
        try:
            nested_text = element.evaluate('''(el) => {
                // Look for common button text patterns
                const textSpan = el.querySelector('.dx-button-text, .button-text, .btn-text, span:not(.slds-assistive-text)');
                if (textSpan && textSpan.textContent) {
                    return textSpan.textContent.trim();
                }
                return '';
            }''')
            if nested_text:
                texts.append(nested_text)
        except:
            pass
        
        # 3. Direct text content (with length filtering for container detection)
        text_content = element.text_content()
        if text_content:
            text_content = text_content.strip()
            # Filter out container elements with excessive text
            if len(text_content) < 200:  # Reasonable limit for button text
                texts.append(text_content)
        
        # 4. Value attribute (for input buttons)
        value = element.get_attribute('value')
        if value:
            texts.append(value.strip())
        
        # 5. Title attribute
        title = element.get_attribute('title')
        if title:
            texts.append(title.strip())
        
        # Return the first non-empty, meaningful text
        for text in texts:
            if text and len(text.strip()) > 0:
                # Filter out very generic or empty text
                if text.strip().lower() not in ['', ' ', '...', 'button']:
                    return text.strip()
        
        return ''
    
    def get_score_threshold(self) -> float:
        """Standard threshold for buttons"""
        return 0.5
    
    def get_strategy_bonus(self) -> float:
        """Bonus points for button matches"""
        return 0.3
    
    def score_element(self, element, context: FinderContext):
        """Enhanced scoring for button elements with better relevance detection"""
        try:
            if not element.is_visible():
                return None
                
            # Get basic element information
            tag_name = element.evaluate('el => el.tagName.toLowerCase()')
            element_role = element.get_attribute('role')
            element_class = element.get_attribute('class') or ''
            element_id = element.get_attribute('id') or ''
            
            # Extract text using strategy-specific methods
            element_text = self.extract_element_text(element, context)
            
            if not element_text:
                return None
            
            # Calculate enhanced similarity score with text relevance
            base_score = self.calculate_text_similarity(context.key_words, element_text)
            
            if base_score <= self.get_score_threshold():
                return None
            
            # Apply text relevance scoring
            relevance_score = self.calculate_text_relevance(context.key_words, element_text)
            
            # Apply element type preference
            element_type_bonus = self.get_element_type_bonus(tag_name, element_role, element_class)
            
            # Container penalty for elements that might be large containers
            container_penalty = self.get_container_penalty(element_text, element_class, element_id)
            
            # Final score calculation
            final_score = base_score * relevance_score + element_type_bonus - container_penalty + self.get_strategy_bonus()
            final_score = max(0.0, min(1.0, final_score))  # Clamp to 0-1
            
            if final_score > self.get_score_threshold():
                return ElementMatch(
                    element=element,
                    score=final_score,
                    matched_by=f"{self.name} enhanced text match",
                    matched_text=element_text,
                    strategy_name=self.name,
                    match_info={
                        'tag_name': tag_name,
                        'role': element_role,
                        'class': element_class,
                        'id': element_id,
                        'base_score': base_score,
                        'relevance_score': relevance_score,
                        'element_type_bonus': element_type_bonus,
                        'container_penalty': container_penalty
                    }
                )
                
        except Exception as e:
            if context.debug:
                print(f"  → Error scoring element in {self.name}: {e}")
        
        return None
    
    def calculate_text_relevance(self, search_text: str, element_text: str) -> float:
        """Calculate how relevant the element text is to the search text"""
        search_text = search_text.lower().strip()
        element_text = element_text.lower().strip()
        
        # If search text is significant portion of element text, high relevance
        if len(search_text) > 0:
            relevance_ratio = len(search_text) / len(element_text)
            
            # Perfect match or search text is major portion
            if search_text == element_text:
                return 1.0
            elif search_text in element_text:
                # Text prominence detection - where does the search text appear?
                prominence_bonus = self.calculate_text_prominence(search_text, element_text)
                
                # Higher relevance if search text is significant portion
                if relevance_ratio >= 0.3:  # 30% or more
                    return 1.0 + prominence_bonus
                elif relevance_ratio >= 0.1:  # 10-30%
                    return 0.8 + prominence_bonus
                else:  # Less than 10% - likely a container
                    return 0.3 + prominence_bonus
            else:
                # Word overlap case
                words_search = set(search_text.split())
                words_element = set(element_text.split())
                if words_search & words_element:
                    overlap_ratio = len(words_search & words_element) / len(words_element)
                    return max(0.5, overlap_ratio)
        
        return 0.5  # Default relevance
    
    def calculate_text_prominence(self, search_text: str, element_text: str) -> float:
        """Calculate bonus based on where the search text appears in the element text"""
        if search_text not in element_text:
            return 0.0
        
        # Find position of search text
        position = element_text.find(search_text)
        text_length = len(element_text)
        
        # Calculate relative position (0.0 = start, 1.0 = end)
        relative_position = position / max(text_length - len(search_text), 1)
        
        # Bonus for text appearing early (first 20% of element text)
        if relative_position <= 0.2:
            return 0.1  # 10% bonus for early appearance
        elif relative_position <= 0.5:
            return 0.05  # 5% bonus for first half
        else:
            return 0.0  # No bonus for later appearance
    
    def get_element_type_bonus(self, tag_name: str, element_role: str, element_class: str) -> float:
        """Give bonus points for actual button elements vs generic containers"""
        # Actual button elements get highest bonus
        if tag_name in ['button', 'input']:
            return 0.2
        
        # Elements with button role
        if element_role == 'button':
            return 0.15
        
        # Elements with button-like classes
        button_classes = ['btn', 'button', 'slds-button', 'dx-button']
        if any(btn_class in element_class.lower() for btn_class in button_classes):
            return 0.1
        
        # Generic clickable elements (div, span, a) get no bonus
        return 0.0
    
    def get_container_penalty(self, element_text: str, element_class: str, element_id: str) -> float:
        """Apply penalty for elements that are likely large containers"""
        penalty = 0.0
        
        # Penalty for very long text (likely containers)
        if len(element_text) > 100:
            penalty += 0.2
        
        # Penalty for container-like classes
        container_classes = ['content', 'container', 'wrapper', 'main', 'body', 'section']
        if any(container_class in element_class.lower() for container_class in container_classes):
            penalty += 0.15
        
        # Penalty for container-like IDs
        if any(container_class in element_id.lower() for container_class in container_classes):
            penalty += 0.15
        
        # Penalty for Salesforce-specific container classes
        salesforce_containers = ['maincontentmark', 'slds-grid', 'slds-col', 'slds-container']
        if any(sf_class in element_class.lower() for sf_class in salesforce_containers):
            penalty += 0.3
        
        return penalty