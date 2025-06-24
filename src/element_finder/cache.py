"""
Caching system for element finder results
"""

import time
import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from difflib import SequenceMatcher


@dataclass
class CacheEntry:
    """Represents a cached element search result"""
    selector: str
    description: str
    matched_text: str
    strategy_name: str
    score: float
    element_attributes: Dict[str, str]
    timestamp: float
    url_pattern: str
    access_count: int = 0
    last_accessed: float = 0.0
    
    def is_expired(self, max_age_seconds: int = 3600000) -> bool:
        """Check if cache entry is expired"""
        return time.time() - self.timestamp > max_age_seconds
    
    def matches_current_page(self, current_url: str) -> bool:
        """Check if cache entry is relevant for current page"""
        # Simple URL matching - can be enhanced with regex patterns
        return self.url_pattern in current_url or current_url in self.url_pattern


class ElementCache:
    """High-performance cache for element finder results with page-level caching"""
    
    def __init__(self, cache_dir: str = "page_models", max_entries: int = 1000):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.max_entries = max_entries
        self.memory_cache: Dict[str, CacheEntry] = {}
        # Page-level caches organized by URL
        self.page_caches: Dict[str, Dict[str, CacheEntry]] = {}
        self.load_from_disk()
    
    def generate_cache_key(self, description: str, url: str, strategy_name: str = "") -> str:
        """Generate a consistent cache key"""
        # Use the same URL normalization as url_pattern to avoid duplicates
        normalized_url = self._extract_url_pattern(url)
        key_data = f"{description}:{normalized_url}:{strategy_name}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, description: str, url: str, strategy_name: str = "") -> Optional[CacheEntry]:
        """Get cached result with fuzzy matching and page-level lookup"""
        url_pattern = self._extract_url_pattern(url)
        
        # First try exact match in page cache
        if url_pattern in self.page_caches:
            page_cache = self.page_caches[url_pattern]
            
            # Try exact description match first
            exact_key = self._normalize_description(description)
            if exact_key in page_cache:
                entry = page_cache[exact_key]
                if not entry.is_expired():
                    entry.access_count += 1
                    entry.last_accessed = time.time()
                    return entry
            
            # Try fuzzy matching with 80% similarity threshold for better precision
            best_match = None
            best_similarity = 0.0
            
            for cached_desc, entry in page_cache.items():
                if entry.is_expired():
                    continue
                    
                similarity = self._calculate_similarity(description, entry.description)
                if similarity >= 0.8 and similarity > best_similarity:
                    best_match = entry
                    best_similarity = similarity
            
            if best_match:
                best_match.access_count += 1
                best_match.last_accessed = time.time()
                return best_match
        
        # Fallback to old memory cache for backwards compatibility
        cache_key = self.generate_cache_key(description, url, strategy_name)
        if cache_key in self.memory_cache:
            entry = self.memory_cache[cache_key]
            if not entry.is_expired() and entry.matches_current_page(url):
                entry.access_count += 1
                entry.last_accessed = time.time()
                return entry
        
        return None
    
    def put(self, description: str, url: str, selector: str, matched_text: str,
            strategy_name: str, score: float, element_attributes: Dict[str, str]):
        """Cache a successful element find result with page-level organization"""
        url_pattern = self._extract_url_pattern(url)
        
        entry = CacheEntry(
            selector=selector,
            description=description,
            matched_text=matched_text,
            strategy_name=strategy_name,
            score=score,
            element_attributes=element_attributes,
            timestamp=time.time(),
            url_pattern=url_pattern,
            access_count=1,
            last_accessed=time.time()
        )
        
        # Store in page-level cache
        if url_pattern not in self.page_caches:
            self.page_caches[url_pattern] = {}
        
        # Store with multiple keys for better matching
        normalized_desc = self._normalize_description(description)
        self.page_caches[url_pattern][normalized_desc] = entry
        
        # Also store with original description as additional key
        if normalized_desc != description.lower():
            self.page_caches[url_pattern][description.lower()] = entry
        
        # Store with key terms as additional keys (only for exact matches)
        key_terms = self._extract_key_terms(description)
        for term in key_terms:
            if len(term) > 3 and term not in ['button', 'field', 'input', 'click']:  # Avoid generic terms
                self.page_caches[url_pattern][term] = entry
        
        print(f"💾 Cached element: '{description}' -> {selector} (score: {score:.2f})")
        
        # Cleanup if cache is too large
        self._cleanup_if_needed()
        
        # Save to disk periodically
        total_entries = sum(len(cache) for cache in self.page_caches.values())
        if total_entries % 5 == 0:
            self.save_to_disk()
        
        # Also save immediately for high-confidence results
        if score >= 0.8:
            self.save_to_disk()
    
    def remove(self, cache_key: str):
        """Remove entry from cache"""
        if cache_key in self.memory_cache:
            del self.memory_cache[cache_key]
    
    def clear(self):
        """Clear all cache entries"""
        self.memory_cache.clear()
        # Remove disk cache files
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_entries = len(self.memory_cache)
        expired_entries = sum(1 for entry in self.memory_cache.values() if entry.is_expired())
        
        if total_entries > 0:
            avg_score = sum(entry.score for entry in self.memory_cache.values()) / total_entries
            total_accesses = sum(entry.access_count for entry in self.memory_cache.values())
        else:
            avg_score = 0.0
            total_accesses = 0
        
        return {
            'total_entries': total_entries,
            'expired_entries': expired_entries,
            'average_score': avg_score,
            'total_accesses': total_accesses,
            'cache_hit_rate': self._calculate_hit_rate()
        }
    
    def _extract_url_pattern(self, url: str) -> str:
        """Extract a reusable pattern from URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # Use only domain for broader matching across different pages
        return parsed.netloc
    
    def _cleanup_if_needed(self):
        """Remove oldest/least accessed entries if cache is full"""
        if len(self.memory_cache) > self.max_entries:
            # Sort by access count (ascending) and last accessed (ascending)
            sorted_entries = sorted(
                self.memory_cache.items(),
                key=lambda x: (x[1].access_count, x[1].last_accessed)
            )
            
            # Remove 10% of entries
            entries_to_remove = max(1, int(self.max_entries * 0.1))
            for cache_key, _ in sorted_entries[:entries_to_remove]:
                del self.memory_cache[cache_key]
    
    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate (placeholder - would need hit/miss tracking)"""
        # This would need to be implemented with proper hit/miss tracking
        return 0.0
    
    def save_to_disk(self):
        """Save cache to disk with page-level organization"""
        try:
            # Save each page cache to a separate JSON file
            for url_pattern, page_cache in self.page_caches.items():
                if not page_cache:
                    continue
                    
                # Create safe filename from URL pattern
                safe_filename = self._url_to_filename(url_pattern)
                cache_file = self.cache_dir / f"{safe_filename}.json"
                
                # Convert entries to dict, using the first occurrence of each selector
                seen_selectors = set()
                cache_data = {}
                
                for desc_key, entry in page_cache.items():
                    if entry.selector not in seen_selectors:
                        cache_data[desc_key] = asdict(entry)
                        seen_selectors.add(entry.selector)
                
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                
                print(f"💾 Page cache saved: {len(cache_data)} entries to {cache_file}")
            
            # Also save legacy cache for backwards compatibility
            if self.memory_cache:
                legacy_file = self.cache_dir / "element_cache.json"
                legacy_data = {key: asdict(entry) for key, entry in self.memory_cache.items()}
                with open(legacy_file, 'w') as f:
                    json.dump(legacy_data, f, indent=2)
                
        except Exception as e:
            print(f"Warning: Failed to save cache to disk: {e}")
    
    def force_save(self):
        """Force save cache to disk regardless of entry count"""
        if len(self.memory_cache) > 0:
            self.save_to_disk()
        else:
            print("💾 Cache is empty, nothing to save")
    
    def load_from_disk(self):
        """Load cache from disk with page-level organization"""
        try:
            # Load page-level cache files
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.name == "element_cache.json":
                    continue  # Skip legacy file for now
                    
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                    
                    # Extract URL pattern from the actual cached entries instead of filename
                    actual_url_patterns = set()
                    for desc_key, entry_data in cache_data.items():
                        if 'url_pattern' in entry_data:
                            actual_url_patterns.add(entry_data['url_pattern'])
                    
                    # Use the most common URL pattern from the entries
                    if actual_url_patterns:
                        url_pattern = max(actual_url_patterns, key=lambda x: sum(1 for entry in cache_data.values() if entry.get('url_pattern') == x))
                    else:
                        # Fallback to filename conversion
                        url_pattern = self._filename_to_url(cache_file.stem)
                    
                    print(f"📂 Loading cache from {cache_file.name} -> URL pattern: {url_pattern}")
                    
                    if url_pattern not in self.page_caches:
                        self.page_caches[url_pattern] = {}
                    
                    loaded_count = 0
                    for desc_key, entry_data in cache_data.items():
                        entry = CacheEntry(**entry_data)
                        if not entry.is_expired():  # Only load non-expired entries
                            self.page_caches[url_pattern][desc_key] = entry
                            loaded_count += 1
                    
                    print(f"📂 Loaded {loaded_count} cache entries for {url_pattern}")
                            
                except Exception as e:
                    print(f"Warning: Failed to load cache file {cache_file}: {e}")
            
            # Load legacy cache for backwards compatibility
            legacy_file = self.cache_dir / "element_cache.json"
            if legacy_file.exists():
                with open(legacy_file, 'r') as f:
                    cache_data = json.load(f)
                
                for key, entry_data in cache_data.items():
                    entry = CacheEntry(**entry_data)
                    if not entry.is_expired():
                        self.memory_cache[key] = entry
                        
        except Exception as e:
            print(f"Warning: Failed to load cache from disk: {e}")
    
    def deduplicate_cache(self):
        """Remove duplicate entries based on description, url_pattern, and strategy"""
        seen_entries = {}
        duplicates_to_remove = []
        
        for cache_key, entry in self.memory_cache.items():
            # Create a unique identifier for the actual element
            unique_id = f"{entry.description}:{entry.url_pattern}:{entry.strategy_name}:{entry.selector}"
            
            if unique_id in seen_entries:
                existing_key, existing_entry = seen_entries[unique_id]
                
                # Keep the entry with higher access count or more recent timestamp
                if (entry.access_count > existing_entry.access_count or
                    (entry.access_count == existing_entry.access_count and entry.timestamp > existing_entry.timestamp)):
                    # Mark the old entry for removal and keep the new one
                    duplicates_to_remove.append(existing_key)
                    seen_entries[unique_id] = (cache_key, entry)
                else:
                    # Mark the new entry for removal and keep the old one
                    duplicates_to_remove.append(cache_key)
            else:
                seen_entries[unique_id] = (cache_key, entry)
        
        # Remove duplicates
        for key in duplicates_to_remove:
            if key in self.memory_cache:
                del self.memory_cache[key]
        
        if duplicates_to_remove:
            print(f"🧹 Removed {len(duplicates_to_remove)} duplicate cache entries")
            self.save_to_disk()
        
        return len(duplicates_to_remove)
    
    def _calculate_similarity(self, desc1: str, desc2: str) -> float:
        """Calculate similarity between two descriptions using SequenceMatcher"""
        return SequenceMatcher(None, desc1.lower(), desc2.lower()).ratio()
    
    def _normalize_description(self, description: str) -> str:
        """Normalize description for consistent caching"""
        normalized = description.lower().strip()
        # Remove common articles and prepositions
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = [word for word in normalized.split() if word not in stop_words]
        return ' '.join(words)
    
    def _extract_key_terms(self, description: str) -> List[str]:
        """Extract key terms from description for multiple keys"""
        normalized = self._normalize_description(description)
        words = normalized.split()
        
        # Return individual significant words and common phrases
        key_terms = []
        
        # Add individual words longer than 2 characters
        key_terms.extend([word for word in words if len(word) > 2])
        
        # Add common UI element patterns
        ui_patterns = {
            'button': ['btn', 'click', 'submit'],
            'field': ['input', 'textbox', 'form'],
            'dropdown': ['select', 'option', 'menu'],
            'link': ['href', 'anchor', 'url']
        }
        
        for pattern, synonyms in ui_patterns.items():
            if pattern in normalized:
                key_terms.extend(synonyms)
        
        return list(set(key_terms))  # Remove duplicates
    
    def _url_to_filename(self, url_pattern: str) -> str:
        """Convert URL pattern to safe filename"""
        # Replace unsafe characters with underscores
        safe_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
        filename = ''.join(c if c in safe_chars else '_' for c in url_pattern)
        # Limit length and remove multiple underscores
        filename = '_'.join(part for part in filename.split('_') if part)
        return filename[:50]  # Limit filename length
    
    def _filename_to_url(self, filename: str) -> str:
        """Convert filename back to URL pattern (best effort)"""
        # Handle the specific pattern of domain_path -> domain only (new format)
        parts = filename.split('_')
        if len(parts) >= 2:
            # Reconstruct domain with dots
            domain_parts = []
            
            # Look for common TLD patterns to identify the domain
            # Handle compound TLDs like .com.au, .co.uk, etc.
            for i, part in enumerate(parts):
                if part in ['com', 'org', 'net', 'edu', 'gov', 'co']:
                    # Check if next part is a country code (compound TLD)
                    if i < len(parts) - 1 and parts[i + 1] in ['au', 'uk', 'nz', 'za', 'jp', 'cn']:
                        domain_parts = parts[:i+2]  # Include both parts of compound TLD
                        break
                    elif i == len(parts) - 1:  # TLD is at the end
                        domain_parts = parts[:i+1]
                        break
                    # If there are more parts after this TLD, continue looking
                elif part in ['au', 'uk', 'nz', 'za', 'jp', 'cn'] and i == len(parts) - 1:  # Country TLD at end
                    domain_parts = parts[:i+1]
                    break
            
            if domain_parts:
                domain = '.'.join(domain_parts)
                return domain
        
        # Fallback to simple replacement
        return filename.replace('_', '.')


class SmartCache(ElementCache):
    """Enhanced cache with learning capabilities"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.success_patterns: Dict[str, int] = {}
        self.failure_patterns: Dict[str, int] = {}
    
    def record_success(self, description: str, selector: str, strategy_name: str):
        """Record a successful element find for learning"""
        pattern = f"{strategy_name}:{self._normalize_description(description)}"
        self.success_patterns[pattern] = self.success_patterns.get(pattern, 0) + 1
    
    def record_failure(self, description: str, strategy_name: str):
        """Record a failed element find for learning"""
        pattern = f"{strategy_name}:{self._normalize_description(description)}"
        self.failure_patterns[pattern] = self.failure_patterns.get(pattern, 0) + 1
    
    def get_strategy_confidence(self, description: str, strategy_name: str) -> float:
        """Get confidence score for a strategy based on historical performance"""
        pattern = f"{strategy_name}:{self._normalize_description(description)}"
        
        successes = self.success_patterns.get(pattern, 0)
        failures = self.failure_patterns.get(pattern, 0)
        
        total = successes + failures
        if total == 0:
            return 0.5  # Neutral confidence for new patterns
        
        return successes / total
    
    def _normalize_description(self, description: str) -> str:
        """Normalize description for pattern matching"""
        # Remove common variations and normalize to key terms
        normalized = description.lower().strip()
        
        # Remove common suffixes/prefixes
        for term in ['field', 'button', 'dropdown', 'menu', 'link']:
            normalized = normalized.replace(term, '').strip()
        
        # Keep only significant words
        words = [word for word in normalized.split() if len(word) > 2]
        return ' '.join(sorted(words))  # Sort for consistency