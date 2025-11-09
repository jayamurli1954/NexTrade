# 🤝 Contributing to NexTrade

Thank you for your interest in contributing to NexTrade! This document provides guidelines and instructions for contributing.

## 💼 Code of Conduct

- Be respectful and inclusive
- Focus on what is best for the community
- Show empathy towards other community members
- Report unacceptable behavior to maintainers

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Git
- Angel One trading account
- Conda (for environment management)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/nextrade.git
cd nextrade

# Create conda environment
conda create -n nextrade-dev python=3.10
conda activate nextrade-dev

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks (optional but recommended)
pre-commit install
```

### Project Structure Overview

```
nextrade/
├── ui_new/                 # UI Components
│   ├── tabs/              # Individual features
│   ├── connection_manager.py
│   └── main_window.py
├── analyzer/              # Trading logic
├── indicators/            # Technical indicators
├── order_manager/         # Trading execution
├── tests/                 # Unit tests
└── docs/                  # Documentation
```

---

## 📋 Types of Contributions

### 🐛 Bug Reports

Found a bug? Great! Please:

1. **Check existing issues** to avoid duplicates
2. **Create a new issue** with:
   - Clear title describing the bug
   - Detailed description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots/logs if applicable
   - Your environment (OS, Python version, etc.)

**Example Bug Report:**
```markdown
## Bug: UI Freezes During Analyzer Scan

### Description
The main window becomes unresponsive during the analyzer scan operation.

### Steps to Reproduce
1. Go to Analyzer tab
2. Click "Scan Now" button
3. Wait for scan to start
4. Try to click other tabs

### Expected Behavior
Other tabs should remain clickable during scan

### Actual Behavior
Window shows "(Not Responding)" and becomes frozen

### Environment
- OS: Windows 11
- Python: 3.10.5
- PyQt5: 5.15.7
```

### ✨ Feature Requests

Have an idea? We'd love to hear it!

1. **Check existing issues** for similar requests
2. **Create new issue** with:
   - Clear title for the feature
   - Detailed description
   - Use cases and benefits
   - Example usage or mockup
   - Any alternative solutions considered

**Example Feature Request:**
```markdown
## Feature: Real-time Price Alerts

### Description
Add notification system for price alerts on watched stocks.

### Use Case
Traders want to be notified when a stock hits certain price levels 
without constantly watching the screen.

### Proposed Solution
- Add alert configuration tab
- Support for email/desktop notifications
- Price level targets
- Bracket alerts (buy at X, sell at Y)

### Example
- Notify when RELIANCE reaches ₹2500
- Stop notifying after trade executed
```

### 🔧 Code Contributions

### Step 1: Fork the Repository

```bash
# Fork on GitHub (via web interface)
# Then clone your fork
git clone https://github.com/yourname/nextrade.git
cd nextrade
```

### Step 2: Create a Feature Branch

```bash
# Create and switch to new branch
git checkout -b feature/your-feature-name

# Good branch names:
# feature/add-alerts-system
# bugfix/fix-analyzer-freezing
# enhancement/improve-performance
# docs/add-api-examples
```

### Step 3: Make Your Changes

**Code Style Guidelines:**
```python
# Follow PEP 8
# Use meaningful variable names
# Add docstrings to all functions
# Keep functions focused and testable

# Good example:
def calculate_rsi(prices: list, period: int = 14) -> float:
    """
    Calculate Relative Strength Index.
    
    Args:
        prices: List of price values
        period: RSI period (default: 14)
    
    Returns:
        RSI value between 0 and 100
    
    Raises:
        ValueError: If period > len(prices)
    """
    if period > len(prices):
        raise ValueError("Period cannot exceed number of prices")
    
    # Implementation...
    return rsi_value
```

### Step 4: Write/Update Tests

```bash
# Run existing tests
python -m pytest tests/

# Run tests for specific module
python -m pytest tests/test_analyzer.py -v

# Run with coverage
python -m pytest tests/ --cov=nextrade
```

### Step 5: Commit Your Changes

```bash
# Stage changes
git add .

# Commit with meaningful message
git commit -m "feature: add price alert system

- Add AlertManager class
- Implement email notifications
- Add alert configuration UI
- Write unit tests for AlertManager
- Update documentation"

# Commit message guidelines:
# - Use imperative mood ("add" not "added")
# - First line: short description (<50 chars)
# - Blank line separator
# - Detailed explanation of changes
# - Reference issues: Fixes #123
```

### Step 6: Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### Step 7: Create a Pull Request

1. Go to GitHub
2. Click "Compare & pull request"
3. Fill in the PR template:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Enhancement
- [ ] Documentation

## Related Issues
Fixes #123

## Testing Done
- [ ] Unit tests added
- [ ] Manual testing completed
- [ ] All tests passing

## Screenshots (if applicable)
[Add screenshots for UI changes]

## Checklist
- [ ] Code follows style guidelines
- [ ] Docstrings added/updated
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes
```

---

## 📐 Code Standards

### Python Style Guide (PEP 8)

```python
# ✅ Good
def analyze_stock(symbol: str, period: int = 20) -> dict:
    """Analyze stock using technical indicators."""
    pass

# ❌ Bad
def analyzeStock(symbol,period=20):
    pass
```

### Documentation

```python
# Class docstrings
class TechnicalAnalyzer:
    """Analyzes stocks using technical indicators.
    
    Attributes:
        data_provider: Source for market data
        indicators: List of technical indicators
    """

# Function docstrings
def calculate_moving_average(prices: list, period: int) -> float:
    """Calculate simple moving average.
    
    Args:
        prices: List of price values
        period: Number of periods to average
    
    Returns:
        Moving average value
    
    Raises:
        ValueError: If period > len(prices)
    
    Examples:
        >>> calculate_moving_average([10, 20, 30], 2)
        25.0
    """
    pass
```

### Type Hints

```python
# Use type hints for clarity
from typing import List, Dict, Optional

def get_signals(stocks: List[str]) -> Dict[str, Optional[str]]:
    """Get trading signals for stocks."""
    return {"RELIANCE": "BUY", "INFY": None}
```

---

## 🧪 Testing Guidelines

### Writing Tests

```python
import pytest
from analyzer.enhanced_analyzer import EnhancedAnalyzer

class TestEnhancedAnalyzer:
    """Test suite for EnhancedAnalyzer."""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance for tests."""
        return EnhancedAnalyzer()
    
    def test_calculate_rsi_basic(self, analyzer):
        """Test RSI calculation with sample data."""
        prices = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42]
        rsi = analyzer.calculate_rsi(prices)
        
        assert 0 <= rsi <= 100
        assert isinstance(rsi, float)
    
    def test_calculate_rsi_invalid_input(self, analyzer):
        """Test RSI calculation with invalid input."""
        with pytest.raises(ValueError):
            analyzer.calculate_rsi([], 14)
    
    @pytest.mark.integration
    def test_analyze_single_stock_live(self, analyzer):
        """Integration test with live API (skip in CI)."""
        signal = analyzer.analyze_single_stock('RELIANCE')
        assert signal is not None or signal is None  # Just check it runs
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_analyzer.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=nextrade --cov-report=html

# Run only fast tests (skip integration tests)
pytest -m "not integration"
```

---

## 📚 Documentation

### Adding Documentation

1. **Code Comments**: For complex logic
```python
# Calculate RSI by comparing up/down movements
# This prevents division by zero
if avg_loss == 0:
    rsi = 100
```

2. **Docstrings**: For all public functions/classes
3. **README**: For user-facing features
4. **docs/ folder**: For detailed guides

### Documentation Format

```markdown
# Feature Name

## Overview
Brief description of the feature.

## Installation
How to install/enable the feature.

## Usage
How to use the feature with examples.

## Configuration
Any configuration options.

## Troubleshooting
Common issues and solutions.

## See Also
Links to related documentation.
```

---

## 🔄 Pull Request Process

### Before Submitting PR:

1. ✅ **Tests Pass**
   ```bash
   pytest tests/
   ```

2. ✅ **Code Follows Style Guide**
   ```bash
   pylint nextrade/
   ```

3. ✅ **Documentation Updated**
   - Update README.md if needed
   - Add docstrings to new functions
   - Update docs/ if needed

4. ✅ **Branch is Up-to-Date**
   ```bash
   git fetch origin
   git rebase origin/main
   ```

5. ✅ **Commit Messages are Clear**
   - Descriptive messages
   - Reference related issues

### PR Review Process:

1. **Automated Checks**: GitHub Actions runs tests
2. **Manual Review**: Maintainers review code
3. **Suggestions**: May ask for changes
4. **Approval**: PR approved and merged

### After Merge:

- Delete your feature branch (optional)
- Your contribution is live!

---

## 🐛 Reporting Bugs

### Bug Report Template

```markdown
## Summary
One-line description of the bug.

## Environment
- **OS**: Windows 11 / macOS / Linux
- **Python Version**: 3.10
- **PyQt5 Version**: 5.15.7

## Steps to Reproduce
1. Do this
2. Then do that
3. Result is...

## Expected Behavior
What should happen?

## Actual Behavior
What actually happens?

## Error Message
```
Paste any error messages or tracebacks here
```

## Possible Solution
Any ideas on how to fix it?

## Additional Context
Any other relevant information?
```

---

## ✨ Areas for Contribution

### 🟢 Easy (Great for Beginners)
- Documentation improvements
- UI/UX enhancements
- Test coverage additions
- Bug fixes

### 🟡 Medium (Some Experience)
- New technical indicators
- Enhanced visualization
- Performance optimizations
- Configuration management

### 🔴 Hard (Expert Level)
- Live trading integration
- Machine learning signals
- Advanced portfolio optimization
- Parallel processing

---

## 📞 Getting Help

### Questions?
- Open a GitHub Discussion
- Check existing issues
- Read documentation in /docs

### Community Support
- GitHub Issues: Bug reports and feature requests
- Discussions: General questions
- Email: contact@nextrade.dev

---

## 🎯 Development Priorities

### Priority 1 (High)
- Bug fixes
- Security improvements
- Performance optimization

### Priority 2 (Medium)
- Feature requests with community interest
- Documentation improvements
- Code refactoring

### Priority 3 (Low)
- Nice-to-have features
- UI tweaks
- Advanced customization

---

## 🔐 Security

### Reporting Security Issues

⚠️ **Do NOT** open a public issue for security vulnerabilities.

Instead:
1. Email: security@nextrade.dev
2. Include details and reproduction steps
3. Allow time for fix before public disclosure

---

## 📝 License

By contributing to NexTrade, you agree that:
- Your contributions are provided under the MIT License
- You have the right to grant these rights
- You understand the implications

---

## 🙏 Thank You!

We appreciate all contributions, from code to documentation to bug reports. Every contribution helps make NexTrade better!

---

**Happy contributing! 🚀**
