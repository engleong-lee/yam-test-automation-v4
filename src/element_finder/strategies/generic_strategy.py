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
        """Comprehensive text extraction for any element with container filtering"""
        texts = []
        
        # Try all common text sources
        text_content = element.text_content()
        if text_content:
            text_content = text_content.strip()
            # Filter out container elements with excessive text (likely not the target element)
            if len(text_content) < 150:  # Reasonable limit for interactive elements
                texts.append(text_content)
        
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
    
    def score_element(self, element, context: FinderContext):
        """Enhanced scoring for generic elements with container detection"""
        try:
            if not element.is_visible():
                return None
                
            # Get basic element information
            tag_name = element.evaluate('el => el.tagName.toLowerCase()')
            element_role = element.get_attribute('role') or ''
            element_class = element.get_attribute('class') or ''
            element_id = element.get_attribute('id') or ''
            
            # Extract text using strategy-specific methods
            element_text = self.extract_element_text(element, context)
            
            if not element_text:
                return None
            
            # Calculate basic similarity score
            base_score = self.calculate_text_similarity(context.key_words, element_text)
            
            if base_score <= self.get_score_threshold():
                return None
            
            # Apply text relevance scoring for container detection
            relevance_score = self.calculate_text_relevance(context.key_words, element_text)
            
            # Apply container penalty
            container_penalty = self.get_container_penalty(element_text, element_class, element_id, tag_name)
            
            # Final score calculation
            final_score = base_score * relevance_score - container_penalty + self.get_strategy_bonus()
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
        if len(search_text) > 0 and len(element_text) > 0:
            relevance_ratio = len(search_text) / len(element_text)
            
            # Perfect match
            if search_text == element_text:
                return 1.0
            elif search_text in element_text:
                # Higher relevance if search text is significant portion
                if relevance_ratio >= 0.5:  # 50% or more - very likely target
                    return 1.0
                elif relevance_ratio >= 0.2:  # 20-50% - likely target
                    return 0.9
                elif relevance_ratio >= 0.1:  # 10-20% - possible target
                    return 0.7
                else:  # Less than 10% - likely a container
                    return 0.3
            else:
                # Word overlap case
                words_search = set(search_text.split())
                words_element = set(element_text.split())
                if words_search & words_element:
                    overlap_ratio = len(words_search & words_element) / len(words_element)
                    return max(0.5, overlap_ratio)
        
        return 0.5  # Default relevance
    
    def get_container_penalty(self, element_text: str, element_class: str, element_id: str, tag_name: str) -> float:
        """Apply penalty for elements that are likely large containers"""
        penalty = 0.0
        
        # Heavy penalty for very long text (almost certainly containers)
        if len(element_text) > 100:
            penalty += 0.4
        elif len(element_text) > 50:
            penalty += 0.2
        
        # Penalty for generic container tags with no interactive role
        if tag_name in ['div', 'span', 'section', 'main'] and not any(keyword in element_class.lower() for keyword in ['button', 'btn', 'clickable', 'interactive']):
            penalty += 0.2
        
        # Penalty for container-like classes
        container_classes = ['content', 'container', 'wrapper', 'main', 'body', 'section', 'grid', 'col', 'layout']
        if any(container_class in element_class.lower() for container_class in container_classes):
            penalty += 0.3
        
        # Penalty for container-like IDs
        if any(container_class in element_id.lower() for container_class in container_classes):
            penalty += 0.3
        
        # Heavy penalty for Salesforce-specific container classes
        salesforce_containers = ['maincontentmark', 'slds-grid', 'slds-col', 'slds-container', 'slds-page-header']
        if any(sf_class in element_class.lower() for sf_class in salesforce_containers):
            penalty += 0.5
        
        return penalty