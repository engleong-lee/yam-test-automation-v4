"""
Auto-discovery page object model that learns and caches page structure
"""

import time
import json
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from playwright.sync_api import Page, ElementHandle


@dataclass
class ElementDescriptor:
    """Describes an element found during page discovery"""
    selector: str
    text_content: str
    attributes: Dict[str, str]
    element_type: str  # 'button', 'input', 'select', etc.
    confidence: float
    discovery_method: str
    last_seen: float
    access_count: int = 0
    
    def matches_description(self, description: str) -> float:
        """Calculate how well this descriptor matches a description"""
        description_lower = description.lower()
        
        # Check text content match
        text_score = 0.0
        if self.text_content:
            text_lower = self.text_content.lower()
            if description_lower == text_lower:
                text_score = 1.0
            elif description_lower in text_lower or text_lower in description_lower:
                text_score = 0.8
            else:
                # Word overlap
                desc_words = set(description_lower.split())
                text_words = set(text_lower.split())
                if desc_words & text_words:
                    text_score = len(desc_words & text_words) / max(len(desc_words), len(text_words)) * 0.7
        
        # Check attribute matches
        attr_score = 0.0
        for attr_name, attr_value in self.attributes.items():
            if attr_value and description_lower in attr_value.lower():
                attr_score = max(attr_score, 0.6)
        
        return max(text_score, attr_score) * self.confidence


class AutoDiscoveryPageModel:
    """Self-learning page model that discovers and caches element structure"""
    
    def __init__(self, cache_dir: str = ".page_models"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Page models indexed by URL pattern
        self.page_models: Dict[str, Dict[str, ElementDescriptor]] = {}
        
        # Discovery settings
        self.max_elements_per_page = 200
        self.discovery_timeout = 10  # seconds
        
    def discover_page(self, page: Page, force_rediscovery: bool = False) -> bool:
        """
        Discover and catalog all interactive elements on the current page
        
        Args:
            page: Playwright page object
            force_rediscovery: Force rediscovery even if page is already known
            
        Returns:
            True if discovery was performed, False if skipped
        """
        url_pattern = self._get_url_pattern(page.url)
        
        # Skip if already discovered and not forcing
        if not force_rediscovery and url_pattern in self.page_models:
            return False
        
        print(f"🔍 Discovering page structure for: {url_pattern}")
        start_time = time.time()
        
        # Initialize page model
        if url_pattern not in self.page_models:
            self.page_models[url_pattern] = {}
        
        page_model = self.page_models[url_pattern]
        discovered_count = 0
        
        # Phase 1: Discover visible interactive elements
        interactive_selectors = [
            'input, button, textarea, select, a[href]',
            '[role="button"], [role="menuitem"], [role="option"], [role="combobox"]',
            '[onclick], [tabindex]',
            'div[class*="button"], div[class*="menu"], span[class*="button"]'
        ]
        
        for selector in interactive_selectors:
            try:
                elements = page.query_selector_all(selector)
                
                for element in elements:
                    if discovered_count >= self.max_elements_per_page:
                        break
                    
                    if not element.is_visible():
                        continue
                    
                    descriptor = self._create_element_descriptor(element, page)
                    if descriptor:
                        # Use selector as key for now
                        key = f"{descriptor.element_type}_{len(page_model)}"
                        page_model[key] = descriptor
                        discovered_count += 1
                        
                if discovered_count >= self.max_elements_per_page:
                    break
                    
            except Exception as e:
                print(f"  → Discovery selector failed: {e}")
                continue
        
        discovery_time = time.time() - start_time
        print(f"  → Discovered {discovered_count} elements in {discovery_time:.2f}s")
        
        # Save to disk
        self._save_page_model(url_pattern)
        
        return True
    
    def find_element_by_description(self, page: Page, description: str) -> Optional[ElementHandle]:
        """
        Find element using discovered page model
        
        Args:
            page: Playwright page object
            description: Human-readable description
            
        Returns:
            ElementHandle if found, None otherwise
        """
        url_pattern = self._get_url_pattern(page.url)
        
        if url_pattern not in self.page_models:
            # Try to discover the page first
            if self.discover_page(page):
                pass  # Discovery completed
            else:
                return None
        
        page_model = self.page_models[url_pattern]
        
        # Find best matching descriptor
        best_match = None
        best_score = 0.0
        
        for key, descriptor in page_model.items():
            score = descriptor.matches_description(description)
            if score > best_score and score >= 0.5:  # Minimum threshold
                best_score = score
                best_match = descriptor
        
        if best_match:
            try:
                # Try to find the element using the cached selector
                element = page.query_selector(best_match.selector)
                if element and element.is_visible():
                    # Update access statistics
                    best_match.access_count += 1
                    best_match.last_seen = time.time()
                    return element
            except:
                pass
        
        return None
    
    def _create_element_descriptor(self, element: ElementHandle, page: Page) -> Optional[ElementDescriptor]:
        """Create a descriptor for an element"""
        try:
            # Get basic element information
            tag_name = element.evaluate('el => el.tagName.toLowerCase()')
            element_role = element.get_attribute('role')
            element_class = element.get_attribute('class') or ''
            element_id = element.get_attribute('id') or ''
            
            # Determine element type
            element_type = self._determine_element_type(tag_name, element_role, element_class)
            
            # Extract text content
            text_content = self._extract_comprehensive_text(element)
            
            # Skip elements without meaningful text or identifiers
            if not text_content and not element_id and not element_class:
                return None
            
            # Generate selector
            selector = self._generate_reliable_selector(element)
            
            # Collect attributes
            attributes = {
                'id': element_id,
                'class': element_class,
                'role': element_role or '',
                'type': element.get_attribute('type') or '',
                'name': element.get_attribute('name') or '',
                'aria-label': element.get_attribute('aria-label') or '',
                'title': element.get_attribute('title') or '',
                'placeholder': element.get_attribute('placeholder') or ''
            }
            
            # Calculate confidence based on available information
            confidence = self._calculate_element_confidence(text_content, attributes, element_type)
            
            return ElementDescriptor(
                selector=selector,
                text_content=text_content,
                attributes=attributes,
                element_type=element_type,
                confidence=confidence,
                discovery_method='auto_discovery',
                last_seen=time.time()
            )
            
        except Exception as e:
            print(f"  → Failed to create descriptor: {e}")
            return None
    
    def _determine_element_type(self, tag_name: str, role: str, class_name: str) -> str:
        """Determine the semantic type of an element"""
        if role:
            if role in ['button', 'menuitem', 'option', 'combobox']:
                return role
        
        if tag_name in ['button', 'input', 'select', 'textarea']:
            return tag_name
        
        if tag_name == 'a':
            return 'link'
        
        # Check class names for semantic meaning
        class_lower = class_name.lower()
        if any(btn in class_lower for btn in ['button', 'btn']):
            return 'button'
        if any(menu in class_lower for menu in ['menu', 'nav']):
            return 'menu'
        if any(dropdown in class_lower for dropdown in ['dropdown', 'select']):
            return 'dropdown'
        
        return 'interactive'
    
    def _extract_comprehensive_text(self, element: ElementHandle) -> str:
        """Extract text from element using multiple strategies"""
        texts = []
        
        # Direct text content
        text_content = element.text_content()
        if text_content and text_content.strip():
            texts.append(text_content.strip())
        
        # Aria label
        aria_label = element.get_attribute('aria-label')
        if aria_label and aria_label.strip():
            texts.append(aria_label.strip())
        
        # Title
        title = element.get_attribute('title')
        if title and title.strip():
            texts.append(title.strip())
        
        # Value (for inputs)
        value = element.get_attribute('value')
        if value and value.strip():
            texts.append(value.strip())
        
        # Placeholder
        placeholder = element.get_attribute('placeholder')
        if placeholder and placeholder.strip():
            texts.append(placeholder.strip())
        
        # Return the longest meaningful text
        meaningful_texts = [t for t in texts if len(t) > 2]
        if meaningful_texts:
            return max(meaningful_texts, key=len)
        
        return texts[0] if texts else ''
    
    def _generate_reliable_selector(self, element: ElementHandle) -> str:
        """Generate a reliable CSS selector for an element"""
        try:
            return element.evaluate('''(el) => {
                // Strategy 1: Use ID if available and unique
                if (el.id && document.querySelectorAll('#' + el.id).length === 1) {
                    return '#' + el.id;
                }
                
                // Strategy 2: Use class combination if unique
                if (el.className) {
                    const classes = el.className.trim().split(/\\s+/).slice(0, 3); // Max 3 classes
                    const classSelector = el.tagName.toLowerCase() + '.' + classes.join('.');
                    if (document.querySelectorAll(classSelector).length === 1) {
                        return classSelector;
                    }
                }
                
                // Strategy 3: Use attributes
                const attrs = [];
                if (el.type) attrs.push('[type="' + el.type + '"]');
                if (el.name) attrs.push('[name="' + el.name + '"]');
                if (el.getAttribute('role')) attrs.push('[role="' + el.getAttribute('role') + '"]');
                
                if (attrs.length > 0) {
                    const attrSelector = el.tagName.toLowerCase() + attrs.join('');
                    if (document.querySelectorAll(attrSelector).length <= 3) {
                        return attrSelector;
                    }
                }
                
                // Strategy 4: Use text content for unique elements
                if (el.textContent && el.textContent.trim()) {
                    const text = el.textContent.trim();
                    const elements = Array.from(document.querySelectorAll(el.tagName));
                    const matchingElements = elements.filter(e => e.textContent.trim() === text);
                    if (matchingElements.length === 1) {
                        return el.tagName.toLowerCase() + ':contains("' + text + '")';
                    }
                }
                
                // Fallback: nth-child selector
                let path = [];
                let current = el;
                
                while (current.parentElement) {
                    const parent = current.parentElement;
                    const siblings = Array.from(parent.children);
                    const index = siblings.indexOf(current) + 1;
                    
                    path.unshift(current.tagName.toLowerCase() + ':nth-child(' + index + ')');
                    current = parent;
                    
                    if (current.id) {
                        path.unshift('#' + current.id);
                        break;
                    }
                    
                    if (path.length > 4) break; // Limit depth
                }
                
                return path.join(' > ');
            }''')
        except:
            # Ultimate fallback
            return element.evaluate('el => el.tagName.toLowerCase()')
    
    def _calculate_element_confidence(self, text_content: str, attributes: Dict[str, str], element_type: str) -> float:
        """Calculate confidence score for an element descriptor"""
        confidence = 0.5  # Base confidence
        
        # Text content boosts confidence
        if text_content:
            if len(text_content) > 20:
                confidence += 0.2
            elif len(text_content) > 5:
                confidence += 0.1
        
        # Specific attributes boost confidence
        if attributes.get('id'):
            confidence += 0.2
        if attributes.get('aria-label'):
            confidence += 0.15
        if attributes.get('role'):
            confidence += 0.1
        
        # Element type affects confidence
        if element_type in ['button', 'input', 'select']:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _get_url_pattern(self, url: str) -> str:
        """Extract a reusable pattern from URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # Use domain + path without query parameters
        return f"{parsed.netloc}{parsed.path}"
    
    def _save_page_model(self, url_pattern: str):
        """Save page model to disk"""
        try:
            safe_filename = url_pattern.replace('/', '_').replace(':', '_')
            model_file = self.cache_dir / f"{safe_filename}.json"
            
            page_model = self.page_models[url_pattern]
            serializable_model = {
                key: asdict(descriptor) for key, descriptor in page_model.items()
            }
            
            with open(model_file, 'w') as f:
                json.dump(serializable_model, f, indent=2)
                
        except Exception as e:
            print(f"  → Failed to save page model: {e}")
    
    def load_page_models(self):
        """Load all page models from disk"""
        try:
            for model_file in self.cache_dir.glob("*.json"):
                with open(model_file, 'r') as f:
                    data = json.load(f)
                
                url_pattern = model_file.stem.replace('_', '/')
                self.page_models[url_pattern] = {
                    key: ElementDescriptor(**desc_data) 
                    for key, desc_data in data.items()
                }
                
        except Exception as e:
            print(f"Warning: Failed to load page models: {e}")
    
    def get_statistics(self) -> Dict[str, any]:
        """Get statistics about discovered page models"""
        total_pages = len(self.page_models)
        total_elements = sum(len(model) for model in self.page_models.values())
        
        element_types = {}
        for model in self.page_models.values():
            for descriptor in model.values():
                element_types[descriptor.element_type] = element_types.get(descriptor.element_type, 0) + 1
        
        return {
            'total_pages': total_pages,
            'total_elements': total_elements,
            'element_types': element_types,
            'pages': list(self.page_models.keys())
        }