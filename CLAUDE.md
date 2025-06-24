# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Rules

- Focus on the task given and do not do other extra tasks. 
  If you discover worth-doing extra tasks, ask for approval before executing it.

- By default, backward compatibility is not required when making changes unless otherwise specified.

- In conversation, if let say we switch to entirely new tasks/topic then request to clear context in order to save token and avoid confusing with too much contexts.


## Common Development Commands

### Python Environment Setup
```bash
pip install -r requirements.txt
```

### Running Tests
```bash
python src/enhanced_test_automation.py
```

## Code Architecture

This is a Playwright-based web test automation framework built around a single class `EnhancedTestAutomation` that executes BDD-style test steps.

### Core Components

**EnhancedTestAutomation Class** (`src/enhanced_test_automation.py`)
- Main automation engine that parses and executes natural language test steps
- Uses Playwright for browser automation with Chromium
- Supports headless/headed modes and configurable slow motion timing

**Step Parser** (`parse_step` method)
- Converts BDD steps into structured actions using regex patterns
- Supports: navigation, form filling, clicking, and page verification
- Example patterns:
  - `Given I navigate to "URL"`
  - `When I fill in "VALUE" to FIELD`
  - `Then I click on "ELEMENT"`
  - `Then I verify that "PAGE" page is loaded`

**Element Discovery** (`find_element` method)
- Intelligent element matching using multiple heuristic strategies
- Searches by label associations, aria-labels, placeholders, button text
- Calculates text similarity scores to find best matching elements
- Handles different element types (inputs, buttons, textareas, selects)

**Element Label Resolution** (`get_element_label_text` method)
- Multi-strategy approach to find associated labels:
  - Label[for] attribute matching
  - Parent label wrapping
  - Sibling label elements
  - ARIA labels and placeholders
  - Button text/value attributes

### Key Features

- **Smart Element Matching**: Uses similarity scoring to match natural language descriptions to UI elements
- **Robust Button Handling**: Waits for disabled buttons to become enabled, handles form validation
- **Debug Support**: Detailed logging, screenshots on failures, element state inspection
- **Form Validation Awareness**: Triggers blur events and form validation for proper interaction

### Dependencies

- **playwright**: Browser automation library (>=1.40.0)
- **re**: Built-in regex for step parsing
- **time**: Built-in for delays and timeouts

### Configuration

Default browser settings in constructor:
- 30-second timeout for page operations
- Configurable headless mode and slow motion timing
- Chromium browser engine