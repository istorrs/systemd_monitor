# Pre-Commit Hook Documentation

This repository includes a pre-commit hook that enforces code quality standards before allowing commits.

## What the Hook Does

The pre-commit hook performs two essential checks:

### 1. Pylint Code Quality Check
- Runs `pylint` on all staged Python files
- Ensures code achieves a 10/10 rating
- Uses configuration from `.pylintrc`

### 2. Unit Test Execution
- Runs all unit tests using `pytest`
- Ensures no tests are failing
- Prevents commits that break existing functionality

## How It Works

When you attempt to commit, the hook automatically:
1. Identifies all staged `.py` files
2. Runs pylint on each file
3. If pylint passes, runs the full test suite
4. Only allows the commit if both checks pass

## Output

The hook provides color-coded, detailed output:
- ✓ **Green**: Check passed
- ✗ **Red**: Check failed (commit blocked)
- ⚠ **Yellow**: Warning (non-blocking)

## Bypassing the Hook

In rare cases where you need to bypass the hook (NOT recommended):

```bash
git commit --no-verify
```

**Warning**: Only bypass the hook if you have a very good reason and understand the implications.

## Requirements

- `pylint>=2.0` - For code quality checks
- `pytest>=6.0` - For running tests

Install with:
```bash
pip install -r requirements-dev.txt
```

## Benefits

1. **Consistency**: Ensures all committed code meets quality standards
2. **Early Detection**: Catches issues before they reach the repository
3. **Confidence**: Confirms tests pass before committing
4. **Team Standards**: Maintains code quality across all contributors
