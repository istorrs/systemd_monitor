# Claude Code Quality Requirements

## CRITICAL: Pre-Commit Checklist

**BEFORE EVERY COMMIT, YOU MUST:**

1. ✅ **Run pylint** - Code MUST score 10.00/10
2. ✅ **Run black** - Code MUST pass black formatting
3. ✅ **Run flake8** - Code MUST have zero violations
4. ✅ **Run pytest** - ALL unit tests MUST pass (no failures, only xfail allowed)

## Commit Rules

### NEVER commit code that:
- Fails pylint (score < 10.00/10)
- Fails black formatting checks
- Has any flake8 violations
- **Has ANY failing unit tests** (this is THE MOST IMPORTANT rule)
- Has unused imports
- Has code quality issues

### Pre-Commit Hook Requirements

The pre-commit hooks are configured in `.pre-commit-config.yaml` and include:
- trim trailing whitespace
- fix end of files
- check yaml
- check for added large files
- check for merge conflicts
- debug statements (python)
- **black** (auto-formatting)
- **flake8** (linting)
- **pylint** (code quality - must score 10.00/10)

**IMPORTANT**: The pre-commit hooks do NOT include pytest (unit tests). You MUST run pytest manually before every commit!

### Verification Commands

```bash
# 1. Run black (auto-fixes formatting)
black systemd_monitor/ tests/

# 2. Run flake8
flake8 systemd_monitor/ tests/

# 3. Run pylint (must be 10.00/10)
pylint systemd_monitor/

# 4. Run ALL unit tests (CRITICAL - DON'T FORGET THIS!)
pytest tests/ -v

# 5. Check pre-commit hooks pass
pre-commit run --all-files
```

## Why This Matters

**Committing code that fails tests breaks the entire CI/CD pipeline:**
- GitHub Actions will fail
- Package builds will fail
- Other developers cannot work
- Wastes significant time debugging and reverting

## Test Requirements

### Unit Test Rules

1. **All tests must pass** - No exceptions
2. **xfail is allowed** - Tests marked with `@pytest.mark.xfail` can fail
3. **Coverage should be high** - Aim for >90% code coverage
4. **Update tests when changing code** - If you modify functionality, update the corresponding tests

### Common Test Failures

When you change architecture or refactor:
1. **Update mock objects** - Ensure mocks match new signatures
2. **Update assertions** - Check tests verify the right attributes/behavior
3. **Update test setup** - Ensure fixtures match new initialization
4. **Run tests locally** - ALWAYS run `pytest` before committing

## Architectural Changes

When making significant architectural changes (like the DBusRouter refactor):

1. **Plan the changes** - Understand what will break
2. **Update implementation** - Make the code changes
3. **Update tests immediately** - Fix all broken tests before committing
4. **Run full test suite** - Verify nothing else broke
5. **Update documentation** - If public API changed

## Development Environment Setup

The development environment in Claude Code is ephemeral (resets between sessions).

Run this at the start of EVERY session:
```bash
./scripts/setup-dev.sh
```

This installs:
- pre-commit framework and hooks
- Package dependencies
- Development tools

## Amending Commits

If you committed code that breaks tests:
1. Fix the tests immediately
2. Amend the commit: `git commit --amend --no-edit`
3. Force push if necessary (only on feature branches!)

## Summary

**THE GOLDEN RULE**: If pytest fails, DO NOT COMMIT. Period.

No exceptions. No excuses. Fix the tests first, then commit.
