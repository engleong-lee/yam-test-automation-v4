"""
Enhanced Test Automation with Hybrid Element Finder

This is the new version that replaces the monolithic find_element method
with a high-performance, modular hybrid approach.

Performance improvements:
- <100ms for cached elements  
- 1-2s for first-time discovery
- 2-5s improvement over original method
"""

from playwright.sync_api import sync_playwright
import time
import os
import json
from anthropic import Anthropic

from element_finder import HybridElementFinder


class EnhancedTestAutomation:
    """Enhanced test automation with hybrid element finder system"""
    
    def __init__(self, headless=False, slow_mo=0, enable_cache=True, enable_auto_discovery=True, debug=False, debug_html_mode=False):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=headless,
            slow_mo=slow_mo
        )
        self.page = self.browser.new_page()
        self.page.set_default_timeout(30000)
        
        # Initialize Anthropic client
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable must be set")
        self.anthropic = Anthropic(api_key=api_key)
        
        # Initialize the hybrid element finder
        self.element_finder = HybridElementFinder(
            enable_cache=enable_cache,
            enable_auto_discovery=enable_auto_discovery,
            debug=debug
        )
        
        self.debug = debug
        self.debug_html_mode = debug_html_mode
        
        # Initialize HTML debug folder if enabled
        if self.debug_html_mode:
            self._create_html_debug_folder()
        
        # Performance tracking
        self.test_performance = {
            'total_steps': 0,
            'successful_steps': 0,
            'total_element_searches': 0,
            'total_search_time': 0.0,
            'failed_steps': []
        }
    
    def parse_all_steps_with_llm(self, test_steps):
        """Parse all BDD steps using LLM into structured actions"""
        if not test_steps:
            return []
        
        # Create prompt for LLM to parse all steps at once
        prompt = f"""You are a BDD test step parser. Parse the following test steps into structured actions.

For each step, return a tuple with the action type and parameters:
- navigate: ("navigate", "url")
- fill: ("fill", "value", "field_description") 
- click: ("click", "element_description")
- click_excluding: ("click_excluding", "target_text", "exclusion_text") - for clicks with exclusions like "click X but not Y"
- verify: ("verify", "text_to_verify")
- should_verify: ("should_verify", "text_to_verify")

Special patterns to recognize:
- "click X but not Y" → ("click_excluding", "X", "Y")
- "click X excluding Y" → ("click_excluding", "X", "Y")  
- "click X except Y" → ("click_excluding", "X", "Y")

Input steps:
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(test_steps))}

Return only a valid JSON array of tuples, no other text. Example format:
[
  ["navigate", "https://example.com"],
  ["fill", "user@example.com", "email field"],
  ["click", "login button"],
  ["click_excluding", "Save", "Save as"],
  ["should_verify", "Sign in"],
  ["verify", "Dashboard"]
]

Parse the steps above:"""

        try:
            message = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            
            # Parse the JSON response
            parsed_actions = json.loads(response_text)
            
            # Convert lists to tuples for consistency with original format
            return [tuple(action) for action in parsed_actions]
            
        except Exception as e:
            print(f"Error parsing steps with LLM: {e}")
            print(f"LLM Response: {response_text if 'response_text' in locals() else 'No response'}")
            return []
    
    def find_element(self, description):
        """
        Enhanced find_element using hybrid approach
        
        This replaces the original 400-line find_element method with a
        high-performance, modular system.
        """
        start_time = time.time()
        self.test_performance['total_element_searches'] += 1
        
        if self.debug:
            print(f"🔍 Enhanced: Finding element '{description}'")
        
        # Use the hybrid element finder
        element = self.element_finder.find_element(
            page=self.page,
            description=description,
            timeout=30000,
            retry_attempts=5
        )
        
        search_time = time.time() - start_time
        self.test_performance['total_search_time'] += search_time
        
        if element:
            if self.debug:
                print(f"✓ Found element in {search_time*1000:.1f}ms")
        else:
            if self.debug:
                print(f"✗ Element not found after {search_time:.2f}s")
        
        return element
    
    def find_element_excluding(self, target_text, exclusion_text):
        """
        Find element containing target_text but excluding exclusion_text
        
        This method finds elements using hybrid approach then filters out
        elements that contain the exclusion text.
        """
        start_time = time.time()
        self.test_performance['total_element_searches'] += 1
        
        if self.debug:
            print(f"🔍 Enhanced: Finding element '{target_text}' excluding '{exclusion_text}'")
        
        # Use the hybrid element finder with exclusion
        element = self.element_finder.find_element_excluding(
            page=self.page,
            target_description=target_text,
            exclusion_description=exclusion_text,
            timeout=30000,
            retry_attempts=5
        )
        
        search_time = time.time() - start_time
        self.test_performance['total_search_time'] += search_time
        
        if element:
            if self.debug:
                print(f"✓ Found element excluding unwanted matches in {search_time*1000:.1f}ms")
        else:
            if self.debug:
                print(f"✗ Element not found after {search_time:.2f}s")
        
        return element
    
    def execute_step(self, parsed_action, step_number=None):
        """Execute a single parsed action with enhanced element finding"""
        step_start_time = time.time()
        self.test_performance['total_steps'] += 1
        
        if not parsed_action:
            print(f"No action provided")
            return False
        
        action = parsed_action[0]
        
        try:
            if action == 'navigate':
                url = parsed_action[1]
                print(f"Navigating to: {url}")
                self.page.goto(url)
                # Wait for page to load
                self.page.wait_for_load_state('networkidle')
                self.test_performance['successful_steps'] += 1
                
                # Capture HTML debug if enabled
                if step_number is not None:
                    self._capture_html_debug(step_number, action, url)
                
                return True
            
            elif action == 'fill':
                value = parsed_action[1]
                field_description = parsed_action[2]
                print(f"Filling '{value}' into {field_description}")
                
                element = self.find_element(field_description)
                if element:
                    element.fill(value)
                    # Small wait for form validation/updates
                    time.sleep(0.5)
                    
                    # For password fields, sometimes we need to trigger validation
                    if 'password' in field_description.lower():
                        print(f"  → Triggering form validation...")
                        element.press('Tab')
                        time.sleep(0.5)
                    
                    self.test_performance['successful_steps'] += 1
                    
                    # Capture HTML debug if enabled
                    if step_number is not None:
                        self._capture_html_debug(step_number, action, field_description)
                    
                    return True
                else:
                    print(f"Could not find element: {field_description}")
                    self._record_failed_step(action, field_description)
                    return False
            
            elif action == 'click' or action == 'click_excluding':
                if action == 'click':
                    element_description = parsed_action[1]
                    print(f"Clicking on: {element_description}")
                    element = self.find_element(element_description)
                    description_for_debug = element_description
                else:  # click_excluding
                    target_text = parsed_action[1]
                    exclusion_text = parsed_action[2]
                    print(f"Clicking on: {target_text} (excluding: {exclusion_text})")
                    element = self.find_element_excluding(target_text, exclusion_text)
                    description_for_debug = f"{target_text} (excluding: {exclusion_text})"
                
                if element:
                    # Enhanced click with better error handling
                    try:
                        # Check if element is visible and enabled
                        is_visible = element.is_visible()
                        is_enabled = not element.get_attribute('disabled')
                        
                        if self.debug:
                            print(f"  → Element state: visible={is_visible}, enabled={is_enabled}")
                        
                        if not is_enabled:
                            print(f"  → Element is disabled, waiting for it to be enabled...")
                            # Wait up to 10 seconds for element to become enabled
                            start_wait = time.time()
                            while time.time() - start_wait < 10:
                                if not element.get_attribute('disabled'):
                                    break
                                time.sleep(0.5)
                        
                        element.click()
                        print(f"  → Clicked successfully!")
                        
                        # Wait for any navigation or updates
                        try:
                            time.sleep(0.5)
                            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                        except Exception as nav_error:
                            if self.debug:
                                print(f"  → Navigation wait failed: {nav_error}")
                        
                        self.test_performance['successful_steps'] += 1
                        
                        # Capture HTML debug if enabled
                        if step_number is not None:
                            self._capture_html_debug(step_number, action, description_for_debug)
                        
                        return True
                        
                    except Exception as click_error:
                        print(f"  → Error clicking element: {click_error}")
                        print(f"  → Attempting JavaScript click...")
                        try:
                            self.page.evaluate('(el) => el.click()', element)
                            print(f"  → JavaScript click successful!")
                            self.test_performance['successful_steps'] += 1
                            
                            # Capture HTML debug if enabled
                            if step_number is not None:
                                self._capture_html_debug(step_number, action, description_for_debug)
                            
                            return True
                        except Exception as js_error:
                            print(f"  → JavaScript click also failed: {js_error}")
                            self._record_failed_step(action, description_for_debug, str(click_error))
                            return False
                else:
                    print(f"Could not find element: {description_for_debug}")
                    self._record_failed_step(action, description_for_debug)
                    return False
            
            elif action == 'verify' or action == 'should_verify':
                if len(parsed_action) > 1:
                    text_to_verify = parsed_action[1]
                else:
                    print(f"No text specified for verification")
                    return False
                    
                print(f"Verifying '{text_to_verify}' is displayed")
                
                # Enhanced verification with multiple strategies
                max_retries = 8
                wait_times = [0.5, 1, 1.5, 2, 3, 4, 5, 7]
                
                for attempt in range(max_retries):
                    print(f"  → Verification attempt {attempt + 1}/{max_retries}")
                    
                    try:
                        # Wait for page stability
                        self.page.wait_for_load_state('domcontentloaded', timeout=3000)
                        
                        current_url = self.page.url
                        page_title = self.page.title()
                        page_content = self.page.content()
                        
                        # Check multiple sources
                        if (text_to_verify.lower() in page_title.lower() or 
                            text_to_verify.lower() in current_url.lower() or
                            text_to_verify.lower() in page_content.lower()):
                            print(f"✓ '{text_to_verify}' found on page")
                            self.test_performance['successful_steps'] += 1
                            
                            # Capture HTML debug if enabled
                            if step_number is not None:
                                self._capture_html_debug(step_number, action, text_to_verify)
                            
                            return True
                        
                        # Check visible text elements
                        visible_text = self.page.evaluate('''() => {
                            return new Promise(resolve => {
                                setTimeout(() => {
                                    const text = Array.from(document.querySelectorAll('*'))
                                        .filter(el => {
                                            const style = window.getComputedStyle(el);
                                            return el.offsetParent !== null && 
                                                   el.textContent.trim() &&
                                                   style.visibility !== 'hidden' &&
                                                   style.display !== 'none';
                                        })
                                        .map(el => el.textContent.trim())
                                        .join(' ');
                                    resolve(text);
                                }, 100);
                            });
                        }''')
                        
                        if text_to_verify.lower() in visible_text.lower():
                            print(f"✓ '{text_to_verify}' found in visible text")
                            self.test_performance['successful_steps'] += 1
                            
                            # Capture HTML debug if enabled
                            if step_number is not None:
                                self._capture_html_debug(step_number, action, text_to_verify)
                            
                            return True
                            
                    except Exception as e:
                        print(f"  → Verification attempt {attempt + 1} failed: {e}")
                    
                    if attempt < max_retries - 1:
                        wait_time = wait_times[attempt]
                        print(f"  → Text not found yet, waiting {wait_time}s...")
                        time.sleep(wait_time)
                
                print(f"✗ '{text_to_verify}' not found on page after {max_retries} attempts")
                self._record_failed_step(action, text_to_verify)
                return False
            
            else:
                print(f"Unknown action: {action}")
                self._record_failed_step(action, "unknown action")
                return False
                
        except Exception as e:
            print(f"Error executing step: {e}")
            self._record_failed_step(action, str(parsed_action), str(e))
            return False
    
    def _create_html_debug_folder(self):
        """Create the html_debug folder for storing HTML snapshots"""
        self.html_debug_folder = os.path.join(os.getcwd(), 'html_debug')
        try:
            os.makedirs(self.html_debug_folder, exist_ok=True)
            if self.debug:
                print(f"📁 HTML debug folder created: {self.html_debug_folder}")
        except Exception as e:
            print(f"Warning: Could not create HTML debug folder: {e}")
            self.debug_html_mode = False
    
    def _capture_html_debug(self, step_number, action, description):
        """Capture HTML and screenshot for debugging purposes"""
        if not self.debug_html_mode:
            return
        
        try:
            timestamp = int(time.time())
            safe_description = "".join(c for c in description if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_description = safe_description.replace(' ', '_')[:50]
            
            base_filename = f"step_{step_number:02d}_{action}_{safe_description}_{timestamp}"
            html_file = os.path.join(self.html_debug_folder, f"{base_filename}.html")
            screenshot_file = os.path.join(self.html_debug_folder, f"{base_filename}.png")
            
            # Save HTML content
            html_content = self.page.content()
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Save screenshot
            self.page.screenshot(path=screenshot_file)
            
            if self.debug:
                print(f"📄 HTML debug saved: {base_filename}")
                
        except Exception as e:
            print(f"Warning: Could not save HTML debug: {e}")
    
    def _record_failed_step(self, action, description, error=None):
        """Record a failed step for analysis"""
        self.test_performance['failed_steps'].append({
            'action': action,
            'description': description,
            'error': error,
            'timestamp': time.time()
        })
    
    def run_test(self, test_steps):
        """Run a complete test scenario with enhanced performance tracking"""
        print("🚀 Starting enhanced test execution...\n")
        
        test_start_time = time.time()
        
        # Parse all steps with LLM upfront
        print("Parsing test steps with LLM...")
        parsed_actions = self.parse_all_steps_with_llm(test_steps)
        
        if not parsed_actions:
            print("Failed to parse test steps. Exiting.")
            return
        
        if len(parsed_actions) != len(test_steps):
            print(f"Warning: Parsed {len(parsed_actions)} actions from {len(test_steps)} steps")
        
        print(f"Successfully parsed {len(parsed_actions)} actions\n")
        
        # Execute steps
        for i, (step, parsed_action) in enumerate(zip(test_steps, parsed_actions), 1):
            print(f"Step {i}: {step}")
            print(f"  → Parsed as: {parsed_action}")
            
            step_start = time.time()
            success = self.execute_step(parsed_action, step_number=i)
            step_duration = time.time() - step_start
            
            if success:
                print(f"  ✓ Completed in {step_duration:.2f}s")
            else:
                print(f"  ✗ Failed after {step_duration:.2f}s")
                print(f"Test failed at step {i}")
                break
            print()
        
        # Print performance summary
        total_test_time = time.time() - test_start_time
        self._print_performance_summary(total_test_time)
        
        print("🎯 Enhanced test execution completed!")
    
    def _print_performance_summary(self, total_test_time):
        """Print comprehensive performance summary"""
        print("\n" + "="*60)
        print("📊 PERFORMANCE SUMMARY")
        print("="*60)
        
        # Test-level stats
        success_rate = self.test_performance['successful_steps'] / max(1, self.test_performance['total_steps'])
        print(f"Test Steps: {self.test_performance['successful_steps']}/{self.test_performance['total_steps']} successful ({success_rate:.1%})")
        print(f"Total Test Time: {total_test_time:.2f}s")
        
        # Element finder stats
        if self.test_performance['total_element_searches'] > 0:
            avg_search_time = self.test_performance['total_search_time'] / self.test_performance['total_element_searches']
            print(f"Element Searches: {self.test_performance['total_element_searches']}")
            print(f"Average Search Time: {avg_search_time*1000:.1f}ms")
            print(f"Total Search Time: {self.test_performance['total_search_time']:.2f}s")
        
        # Element finder performance stats
        finder_stats = self.element_finder.get_performance_stats()
        if finder_stats['total_searches'] > 0:
            print(f"\n📈 Element Finder Performance:")
            print(f"  Success Rate: {finder_stats['success_rate']:.1%}")
            print(f"  Cache Hit Rate: {finder_stats['cache_hit_rate']:.1%}")
            print(f"  Average Time: {finder_stats['average_search_time']*1000:.1f}ms")
            
            # Strategy breakdown
            print(f"\n🎯 Strategy Usage:")
            for strategy, stats in finder_stats['strategy_usage'].items():
                if stats['attempts'] > 0:
                    success_rate = stats['successes'] / stats['attempts']
                    print(f"  {strategy}: {stats['successes']}/{stats['attempts']} ({success_rate:.1%}) - avg {stats['avg_time']*1000:.1f}ms")
        
        # Failed steps
        if self.test_performance['failed_steps']:
            print(f"\n❌ Failed Steps:")
            for i, failure in enumerate(self.test_performance['failed_steps'], 1):
                print(f"  {i}. {failure['action']}: {failure['description']}")
                if failure['error']:
                    print(f"     Error: {failure['error']}")
        
        print("="*60)
    
    def cleanup(self):
        """Clean up browser resources"""
        try:
            # Save cache before cleanup
            print(f"\n💾 Saving cache...")
            self.element_finder.save_cache()
            
            # Print final stats
            print(f"\n📋 Final Statistics:")
            finder_stats = self.element_finder.get_performance_stats()
            print(f"  Total element searches: {finder_stats['total_searches']}")
            print(f"  Cache hits: {finder_stats['cache_hits']}")
            print(f"  Success rate: {finder_stats.get('success_rate', 0):.1%}")
            
        except Exception as e:
            print(f"Error generating final stats: {e}")
        finally:
            self.browser.close()
            self.playwright.stop()
    
    def load_test_steps(self, file_path):
        """Load test steps from external file"""
        test_steps = []
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line:  # Skip empty lines
                        test_steps.append(line)
        except FileNotFoundError:
            print(f"Test file not found: {file_path}")
            return []
        return test_steps


# Example usage and comparison
if __name__ == "__main__":
    import os
    import sys
    
    # Check if test filename was provided as command line argument
    if len(sys.argv) < 2:
        print("Usage: python enhanced_test_automation.py <test_filename> [--debug] [--debug-html]")
        print("Example: python enhanced_test_automation.py feature1.test --debug --debug-html")
        sys.exit(1)
    
    test_filename = sys.argv[1]
    debug_mode = '--debug' in sys.argv
    
    # Check for debug HTML mode
    debug_html_mode = '--debug-html' in sys.argv
    
    # Load test steps from external file
    automation = EnhancedTestAutomation(
        headless=False, 
        slow_mo=500,
        enable_cache=True,
        enable_auto_discovery=True,
        debug=debug_mode,
        debug_html_mode=debug_html_mode
    )
    
    # Get test file path relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_file = os.path.join(script_dir, '..', 'tests', test_filename)
    
    test_steps = automation.load_test_steps(test_file)
    
    if not test_steps:
        print("No test steps found. Exiting.")
        automation.cleanup()
        exit(1)
    
    # Run the enhanced test
    try:
        automation.run_test(test_steps)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        print("Taking final screenshot...")
        try:
            automation.page.screenshot(path="enhanced_test_failure_screenshot.png")
            print("Screenshot saved to: enhanced_test_failure_screenshot.png")
        except Exception:
            pass
    finally:
        automation.cleanup()