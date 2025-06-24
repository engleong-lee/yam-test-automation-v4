"""
Hybrid Element Finder - Orchestrates multiple strategies with caching and auto-discovery
"""

import time
from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, ElementHandle

from .base import ElementFinderStrategy, ElementMatch, FinderContext
from .cache import SmartCache
from .strategies import (
    FormFieldStrategy, ButtonStrategy, DevExtremeStrategy, 
    MenuItemStrategy, GenericStrategy
)


class HybridElementFinder:
    """
    High-performance element finder that combines multiple strategies with caching.
    
    Performance targets:
    - <100ms for cached elements
    - 1-2s for first-time discovery
    - 2-5s improvement over original find_element method
    """
    
    def __init__(self, enable_cache: bool = True, enable_auto_discovery: bool = True, debug: bool = False):
        self.cache = SmartCache() if enable_cache else None
        self.enable_auto_discovery = enable_auto_discovery
        self.debug = debug
        
        # Initialize strategies in priority order (highest first)
        self.strategies: List[ElementFinderStrategy] = [
            DevExtremeStrategy(),    # Priority 90 - Framework specific
            ButtonStrategy(),        # Priority 85 - High confidence
            FormFieldStrategy(),     # Priority 80 - High confidence  
            MenuItemStrategy(),      # Priority 75 - High confidence
            GenericStrategy()        # Priority 10 - Fallback
        ]
        
        # Sort strategies by priority
        self.strategies.sort()
        
        # Performance tracking
        self.performance_stats = {
            'total_searches': 0,
            'cache_hits': 0,
            'strategy_usage': {},
            'average_search_time': 0.0,
            'successful_searches': 0
        }
    
    def find_element(self, page: Page, description: str, timeout: int = 30000, retry_attempts: int = 5) -> Optional[ElementHandle]:
        """
        Main entry point - finds element using hybrid approach
        
        Args:
            page: Playwright page object
            description: Human-readable description of element to find
            timeout: Maximum time to spend searching (ms)
            retry_attempts: Number of retry attempts for dynamic content
            
        Returns:
            ElementHandle if found, None otherwise
        """
        start_time = time.time()
        self.performance_stats['total_searches'] += 1
        
        # Normalize description
        original_description = description
        description = description.lower().strip('"')
        key_words = self._extract_key_words(description)
        
        # Create context
        context = FinderContext(
            page=page,
            description=description,
            original_description=original_description,
            key_words=key_words,
            timeout=timeout,
            retry_attempts=retry_attempts,
            enable_dynamic_discovery=self.enable_auto_discovery,
            cache_enabled=self.cache is not None,
            debug=self.debug
        )
        
        if self.debug:
            print(f"🔍 HybridFinder: Searching for '{description}'")
        
        # Phase 1: Check cache first
        cached_result = self._try_cache(context)
        if cached_result:
            search_time = time.time() - start_time
            self._update_performance_stats('cache', search_time, True)
            if self.debug:
                print(f"✓ Cache hit! Found in {search_time*1000:.1f}ms")
            return cached_result
        
        # Phase 2: Wait for initial page stability
        self._wait_for_page_stability(context)
        
        # Phase 3: Try strategies in priority order
        best_match = None
        
        for attempt in range(retry_attempts):
            if self.debug:
                print(f"  → Attempt {attempt + 1}/{retry_attempts}")
            
            # Get applicable strategies for this context
            applicable_strategies = [s for s in self.strategies if s.can_handle(context)]
            
            if self.debug:
                strategy_names = [s.name for s in applicable_strategies]
                print(f"  → Using strategies: {strategy_names}")
            
            # Try each applicable strategy
            for strategy in applicable_strategies:
                strategy_start = time.time()
                
                try:
                    matches = strategy.find_elements(context)
                    strategy_time = time.time() - strategy_start
                    
                    if matches:
                        # Sort matches by score (highest first)
                        matches.sort(key=lambda m: m.score, reverse=True)
                        top_match = matches[0]
                        
                        if self.debug:
                            print(f"  → {strategy.name}: Found {len(matches)} matches, best score: {top_match.score:.2f} ({strategy_time*1000:.1f}ms)")
                        
                        # Update strategy performance tracking
                        self._update_strategy_stats(strategy.name, strategy_time, True)
                        
                        # Check if this is our best match so far
                        if best_match is None or top_match.score > best_match.score:
                            best_match = top_match
                        
                        # Early termination for high-confidence matches
                        if top_match.score >= 0.9:
                            if self.debug:
                                print(f"  → High confidence match found, stopping search")
                            break
                    else:
                        self._update_strategy_stats(strategy.name, strategy_time, False)
                        
                except Exception as e:
                    strategy_time = time.time() - strategy_start
                    self._update_strategy_stats(strategy.name, strategy_time, False)
                    if self.debug:
                        print(f"  → {strategy.name} failed: {e}")
            
            # If we found a good match, use it
            if best_match and best_match.score >= 0.5:
                break
            
            # Wait before retry (if not last attempt)
            if attempt < retry_attempts - 1:
                wait_time = min(2 ** attempt, 5)  # Exponential backoff, max 5s
                if self.debug:
                    print(f"  → Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                
                # Re-check page stability
                self._wait_for_page_stability(context)
        
        # Phase 4: Process results
        search_time = time.time() - start_time
        
        if best_match:
            self._update_performance_stats(best_match.strategy_name, search_time, True)
            
            # Cache the successful result
            if self.cache:
                self._cache_result(context, best_match)
            
            if self.debug:
                print(f"✓ Found element using {best_match.strategy_name}")
                print(f"  → Score: {best_match.score:.2f}")
                print(f"  → Matched by: {best_match.matched_by}")
                print(f"  → Matched text: '{best_match.matched_text}'")
                print(f"  → Total time: {search_time*1000:.1f}ms")
            
            return best_match.element
        else:
            self._update_performance_stats('none', search_time, False)
            
            if self.debug:
                print(f"✗ No element found after {search_time:.2f}s")
                
            # Generate debug information
            self._generate_debug_info(context)
            
            return None
    
    def _try_cache(self, context: FinderContext) -> Optional[ElementHandle]:
        """Try to find element using cache"""
        if not self.cache:
            return None
        
        if context.debug:
            print(f"  🔍 Checking cache for '{context.description}' on {context.page.url}")
        
        # Try different cache strategies
        for strategy in self.strategies:
            if strategy.can_handle(context):
                if context.debug:
                    print(f"    → Trying {strategy.name} cache lookup")
                
                cached_entry = self.cache.get(context.description, context.page.url, strategy.name)
                if cached_entry:
                    if context.debug:
                        print(f"    ✓ Found cached entry: {cached_entry.selector} (score: {cached_entry.score:.2f})")
                    
                    # Verify cached element still exists and is valid
                    try:
                        element = context.page.query_selector(cached_entry.selector)
                        if element and element.is_visible():
                            # Verify it still matches our description
                            element_text = strategy.extract_element_text(element, context)
                            if element_text and strategy.calculate_text_similarity(context.key_words, element_text) >= 0.5:
                                self.performance_stats['cache_hits'] += 1
                                self.cache.record_success(context.description, cached_entry.selector, strategy.name)
                                
                                if context.debug:
                                    print(f"    ✓ Cache hit! Using cached selector: {cached_entry.selector}")
                                
                                return element
                            elif context.debug:
                                print(f"    ✗ Text similarity too low: '{element_text}' vs '{context.key_words}'")
                        elif context.debug:
                            print(f"    ✗ Cached element not visible or not found")
                    except Exception as e:
                        if context.debug:
                            print(f"    ✗ Cache validation failed: {e}")
                        # Remove invalid cache entry
                        cache_key = self.cache.generate_cache_key(context.description, context.page.url, strategy.name)
                        self.cache.remove(cache_key)
                elif context.debug:
                    print(f"    ✗ No cached entry found for {strategy.name}")
        
        if context.debug:
            print(f"  ✗ No valid cache entries found")
        
        return None
    
    def _wait_for_page_stability(self, context: FinderContext):
        """Wait for page to be stable before searching"""
        try:
            context.page.wait_for_load_state('domcontentloaded', timeout=5000)
        except:
            pass
        
        # Skip network idle wait for interactive elements that are typically already loaded
        if self._is_likely_interactive_element(context.description):
            if context.debug:
                print(f"  → Skipping network wait for interactive element")
            return
        
        try:
            context.page.wait_for_load_state('networkidle', timeout=3000)
        except:
            if context.debug:
                print(f"  → Network idle timeout, continuing anyway")
    
    def _is_likely_interactive_element(self, description: str) -> bool:
        """Check if description suggests an element that's likely already in DOM"""
        interactive_indicators = ['button', 'menu', 'logout', 'login', 'submit', 'click']
        return any(indicator in description.lower() for indicator in interactive_indicators) or len(description.split()) <= 2
    
    def _extract_key_words(self, description: str) -> str:
        """Extract key words from description by removing element type indicators"""
        type_words = ['field', 'button', 'dropdown', 'menu', 'link', 'checkbox', 'radio', 'input']
        words = description.split()
        key_words = [word for word in words if word not in type_words]
        return ' '.join(key_words).strip()
    
    def _cache_result(self, context: FinderContext, match: ElementMatch):
        """Cache a successful search result"""
        if not self.cache:
            return
        
        try:
            # Generate a reliable selector for the element
            selector = self._generate_element_selector(match.element)
            
            # Get element attributes for caching
            element_attributes = {
                'tag': match.element.evaluate('el => el.tagName.toLowerCase()'),
                'id': match.element.get_attribute('id') or '',
                'class': match.element.get_attribute('class') or '',
                'role': match.element.get_attribute('role') or ''
            }
            
            self.cache.put(
                description=context.description,
                url=context.page.url,
                selector=selector,
                matched_text=match.matched_text,
                strategy_name=match.strategy_name,
                score=match.score,
                element_attributes=element_attributes
            )
            
            self.cache.record_success(context.description, selector, match.strategy_name)
            
        except Exception as e:
            if context.debug:
                print(f"  → Failed to cache result: {e}")
    
    def _generate_element_selector(self, element: ElementHandle) -> str:
        """Generate a reliable CSS selector for an element"""
        try:
            return element.evaluate('''(el) => {
                // Try to generate a unique selector
                if (el.id) {
                    return '#' + el.id;
                }
                
                // Try class-based selector if unique
                if (el.className) {
                    const classes = el.className.trim().split(/\\s+/);
                    for (const cls of classes) {
                        const selector = el.tagName.toLowerCase() + '.' + cls;
                        if (document.querySelectorAll(selector).length === 1) {
                            return selector;
                        }
                    }
                }
                
                // Fallback to nth-child selector
                let selector = el.tagName.toLowerCase();
                let current = el;
                
                while (current.parentElement) {
                    const parent = current.parentElement;
                    const siblings = Array.from(parent.children).filter(
                        child => child.tagName === current.tagName
                    );
                    
                    if (siblings.length > 1) {
                        const index = siblings.indexOf(current) + 1;
                        selector = current.tagName.toLowerCase() + ':nth-child(' + index + ') > ' + selector;
                    } else {
                        selector = current.tagName.toLowerCase() + ' > ' + selector;
                    }
                    
                    current = parent;
                    
                    // Stop if we have a parent with ID
                    if (parent.id) {
                        selector = '#' + parent.id + ' > ' + selector;
                        break;
                    }
                    
                    // Limit depth
                    if (selector.split(' > ').length > 5) break;
                }
                
                return selector;
            }''')
        except:
            # Fallback selector
            return element.evaluate('el => el.tagName.toLowerCase()')
    
    def _update_performance_stats(self, strategy_name: str, duration: float, success: bool):
        """Update performance statistics"""
        if strategy_name not in self.performance_stats['strategy_usage']:
            self.performance_stats['strategy_usage'][strategy_name] = {
                'attempts': 0, 'successes': 0, 'avg_time': 0.0
            }
        
        stats = self.performance_stats['strategy_usage'][strategy_name]
        stats['attempts'] += 1
        
        if success:
            stats['successes'] += 1
            self.performance_stats['successful_searches'] += 1
        
        # Update average time (running average)
        stats['avg_time'] = (stats['avg_time'] * (stats['attempts'] - 1) + duration) / stats['attempts']
        
        # Update global average
        total = self.performance_stats['total_searches']
        self.performance_stats['average_search_time'] = (
            self.performance_stats['average_search_time'] * (total - 1) + duration
        ) / total
    
    def _update_strategy_stats(self, strategy_name: str, duration: float, success: bool):
        """Update strategy-specific statistics"""
        self._update_performance_stats(strategy_name, duration, success)
    
    def _generate_debug_info(self, context: FinderContext):
        """Generate debug information when element is not found"""
        if not context.debug:
            return
        
        try:
            # Save HTML dump
            timestamp = int(time.time())
            html_dump_path = f"debug_html_dump_{timestamp}.html"
            html_content = context.page.content()
            with open(html_dump_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"  → HTML dump saved to: {html_dump_path}")
            
            # Save screenshot
            screenshot_path = f"debug_screenshot_{timestamp}.png"
            context.page.screenshot(path=screenshot_path)
            print(f"  → Screenshot saved to: {screenshot_path}")
            
        except Exception as e:
            print(f"  → Failed to generate debug info: {e}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        stats = self.performance_stats.copy()
        
        if self.cache:
            stats['cache_stats'] = self.cache.get_stats()
        
        # Calculate success rate
        if stats['total_searches'] > 0:
            stats['success_rate'] = stats['successful_searches'] / stats['total_searches']
            stats['cache_hit_rate'] = stats['cache_hits'] / stats['total_searches']
        else:
            stats['success_rate'] = 0.0
            stats['cache_hit_rate'] = 0.0
        
        return stats
    
    def clear_cache(self):
        """Clear the element cache"""
        if self.cache:
            self.cache.clear()
    
    def save_cache(self):
        """Force save cache to disk"""
        if self.cache:
            self.cache.force_save()
    
    def reset_stats(self):
        """Reset performance statistics"""
        self.performance_stats = {
            'total_searches': 0,
            'cache_hits': 0,
            'strategy_usage': {},
            'average_search_time': 0.0,
            'successful_searches': 0
        }