"""
Base classes and interfaces for the element finder system
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from playwright.sync_api import Page, ElementHandle
import time


@dataclass
class ElementMatch:
    """Represents a matched element with its confidence score and metadata"""
    element: ElementHandle
    score: float
    matched_by: str
    matched_text: str
    strategy_name: str
    match_info: Dict[str, Any]
    
    def __post_init__(self):
        # Ensure score is between 0 and 1
        self.score = max(0.0, min(1.0, self.score))


@dataclass 
class FinderContext:
    """Context information for element finding operations"""
    page: Page
    description: str
    original_description: str
    key_words: str
    element_type: Optional[str] = None
    timeout: int = 30000
    retry_attempts: int = 5
    enable_dynamic_discovery: bool = True
    cache_enabled: bool = True
    debug: bool = False


class ElementFinderStrategy(ABC):
    """Base class for all element finding strategies"""
    
    def __init__(self, priority: int = 0):
        self.priority = priority
        self.name = self.__class__.__name__
    
    @abstractmethod
    def can_handle(self, context: FinderContext) -> bool:
        """Determine if this strategy can handle the given context"""
        pass
    
    @abstractmethod
    def find_elements(self, context: FinderContext) -> List[ElementMatch]:
        """Find and score potential elements"""
        pass
    
    def get_selectors(self, context: FinderContext) -> List[Tuple[str, str]]:
        """Get CSS selectors for this strategy (selector, description)"""
        return []
    
    def score_element(self, element: ElementHandle, context: FinderContext) -> Optional[ElementMatch]:
        """Score a single element for relevance"""
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
            
            # Calculate similarity score
            score = self.calculate_text_similarity(context.key_words, element_text)
            
            if score > self.get_score_threshold():
                return ElementMatch(
                    element=element,
                    score=score + self.get_strategy_bonus(),
                    matched_by=f"{self.name} text match",
                    matched_text=element_text,
                    strategy_name=self.name,
                    match_info={
                        'tag_name': tag_name,
                        'role': element_role,
                        'class': element_class,
                        'id': element_id
                    }
                )
                
        except Exception as e:
            if context.debug:
                print(f"  → Error scoring element in {self.name}: {e}")
        
        return None
    
    def extract_element_text(self, element: ElementHandle, context: FinderContext) -> str:
        """Extract text from element - can be overridden by strategies"""
        # Try common text extraction methods
        text = element.text_content() or element.get_attribute('value') or ''
        if not text:
            text = element.get_attribute('aria-label') or ''
        if not text:
            text = element.get_attribute('title') or ''
        return text.strip()
    
    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (0-1 score)"""
        text1 = text1.lower().strip()
        text2 = text2.lower().strip()
        
        # Exact match
        if text1 == text2:
            return 1.0
        
        # Contains match
        if text1 in text2 or text2 in text1:
            return 0.8
        
        # Word overlap
        words1 = set(text1.split())
        words2 = set(text2.split())
        if words1 & words2:  # Intersection
            overlap = len(words1 & words2) / max(len(words1), len(words2))
            return overlap * 0.7
        
        return 0.0
    
    def get_score_threshold(self) -> float:
        """Minimum score threshold for this strategy"""
        return 0.5
    
    def get_strategy_bonus(self) -> float:
        """Bonus points for this strategy type"""
        return 0.0
    
    def __lt__(self, other):
        """Enable sorting by priority (higher priority first)"""
        return self.priority > other.priority


class TimingMixin:
    """Mixin to add timing capabilities to strategies"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timing_data = {}
    
    def time_operation(self, operation_name: str, func, *args, **kwargs):
        """Time an operation and store the result"""
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            self.timing_data[operation_name] = duration
            return result
        except Exception as e:
            duration = time.time() - start_time
            self.timing_data[f"{operation_name}_failed"] = duration
            raise e
    
    def get_timing_summary(self) -> Dict[str, float]:
        """Get timing summary for this strategy"""
        return self.timing_data.copy()


class CacheableStrategy(ElementFinderStrategy):
    """Strategy that supports caching of results"""
    
    def get_cache_key(self, context: FinderContext) -> str:
        """Generate a cache key for this search"""
        return f"{self.name}:{context.description}:{context.page.url}"
    
    def should_use_cache(self, context: FinderContext) -> bool:
        """Determine if cache should be used for this context"""
        return context.cache_enabled