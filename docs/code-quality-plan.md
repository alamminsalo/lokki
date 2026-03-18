# Code Quality Improvement Plan

## Overview

This document outlines a comprehensive plan for improving lokki's code quality, functionality, and maintainability. The improvements are organized into 5 sequential milestones (M54-M58) that build upon each other.

## Milestone Dependencies

```
M54 (Error Handling) → M55 (Type Safety) → M56 (Testing)
                              ↓
                    M57 (Logging) → M58 (Build Performance)
```

**Recommended Implementation Order:**
1. **M54** - Error Handling & Validation (foundation for everything)
2. **M55** - Type Safety & Code Quality (cleaner code for testing)
3. **M56** - Testing Coverage (test the improvements)
4. **M57** - Logging Enhancements (observability)
5. **M58** - Build Performance (optimization)

## Milestone Summary

### Milestone 54 — Error Handling & Validation

**Purpose:** Implement comprehensive error handling with custom exceptions, graph validation, and configuration validation.

**Key Deliverables:**
- Custom exception hierarchy (`LokkiError`, `GraphValidationError`, `ConfigurationError`, etc.)
- Graph validation (cycle detection, unreachable steps, duplicate names)
- Configuration validation for deployment readiness
- Improved error messages with context
- Better S3 and build error handling

**Files Created:**
- `lokki/_errors.py` - Custom exceptions
- `tests/test_errors.py` - Error handling tests

**Files Modified:**
- `lokki/graph.py` - Add validation
- `lokki/config.py` - Add validation method
- `lokki/store/s3.py` - Better error handling
- `lokki/builder/builder.py` - Wrap errors

**Impact:** Better debugging, clearer error messages, prevents invalid configurations

---

### Milestone 55 — Type Safety & Code Quality

**Purpose:** Improve type annotations, reduce code duplication, and enhance API consistency.

**Key Deliverables:**
- AWS client factory (reduce duplication)
- Better type annotations (TypedDict, TypeVar, Literal)
- Complete API docstrings
- Standardized naming conventions
- Strict mypy compliance

**Files Modified:**
- `lokki/_aws.py` - Factory pattern
- `lokki/store/protocol.py` - TypedDict
- All modules - Enhanced type hints and docstrings

**Impact:** Better IDE support, fewer runtime errors, easier maintenance

---

### Milestone 56 — Testing Coverage & Quality

**Purpose:** Add comprehensive test coverage for uncovered modules.

**Key Deliverables:**
- S3Store tests with moto
- MemoryStore tests
- CloudFormation builder tests
- State machine builder tests
- Batch handler tests
- Edge case tests for retry logic
- Graph validation tests
- Configuration validation tests

**Files Created:**
- `tests/test_store_s3.py`
- `tests/test_store_memory.py`
- `tests/test_cloudformation.py`
- `tests/test_state_machine.py`
- `tests/test_batch_handler.py`

**Impact:** Confidence in refactoring, catch regressions, document behavior

---

### Milestone 57 — Logging & Observability Enhancements

**Purpose:** Enhance logging with correlation IDs, structured events, and performance metrics.

**Key Deliverables:**
- Correlation ID tracking across steps
- Enhanced step logging (input/output sizes, retry attempts)
- Improved map progress logging (timing, slow items)
- Structured logging events
- Performance metrics
- Log sampling for production
- `@timed` decorator for timing

**Files Modified:**
- `lokki/logging.py` - Enhanced loggers
- `lokki/_utils.py` - Timing utilities
- All runtime modules - Add correlation IDs

**Impact:** Better production debugging, performance insights, easier troubleshooting

---

### Milestone 58 — Build Performance & Caching

**Purpose:** Improve build performance with dependency caching, incremental builds, and parallel package generation.

**Key Deliverables:**
- Dependency caching (hash-based)
- Incremental build support
- Parallel Lambda package building
- Build progress reporting
- Build validation
- Cache management CLI commands
- Build timing and metrics

**Files Created:**
- `lokki/cli/cache.py` - Cache management
- `tests/test_cache.py` - Cache tests

**Files Modified:**
- `lokki/builder/builder.py` - Caching, parallel builds
- `lokki/builder/lambda_pkg.py` - Parallel support

**Impact:** Faster builds (5-10x improvement), better developer experience

---

## Implementation Guidelines

### Before Starting Each Milestone

1. **Read the milestone file** (`docs/tasks/m{N}.md`)
2. **Understand dependencies** - Ensure previous milestones are complete
3. **Create a feature branch** - `feature/m{N}_{milestone_name}`
4. **Set up test environment** - Ensure moto, pytest, mypy are working

### During Implementation

1. **Follow existing patterns** - Match code style and conventions
2. **Write tests first** - TDD approach where possible
3. **Run mypy** - Ensure type safety
4. **Run ruff** - Ensure code quality
5. **Update documentation** - Keep docs in sync

### After Completing Milestone

1. **All tests pass** - `uv run pytest`
2. **Mypy passes** - `uv run mypy lokki/`
3. **Ruff passes** - `uv run ruff check lokki/`
4. **Update milestone status** - Mark tasks complete in `docs/tasks/m{N}.md`
5. **Update README** - Mark milestone complete in `docs/tasks/README.md`

---

## Expected Outcomes

### Code Quality Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Test Coverage | ~70% | >85% |
| Mypy Errors | 0 | 0 (strict mode) |
| Code Duplication | Medium | Low |
| Error Context | Limited | Comprehensive |

### Developer Experience

- **Faster builds**: 5-10x improvement with caching
- **Better errors**: Clear, actionable error messages
- **IDE support**: Enhanced type hints and autocomplete
- **Debugging**: Correlation IDs and structured logs

### Production Reliability

- **Validation**: Catch configuration errors before deploy
- **Observability**: Track issues across steps
- **Performance**: Identify bottlenecks with metrics
- **Testing**: Confidence from comprehensive test suite

---

## Risk Mitigation

### Potential Risks

1. **Breaking changes** - New validation might reject previously valid configs
   - **Mitigation**: Add warnings first, make breaking in next major version

2. **Performance regression** - Enhanced logging might slow execution
   - **Mitigation**: Add sampling, make verbose logging optional

3. **Cache invalidation** - Dependency cache might become stale
   - **Mitigation**: Use content-based hashing, add cache clean command

4. **Test maintenance** - More tests to maintain
   - **Mitigation**: Focus on behavior tests, not implementation details

### Backward Compatibility

All milestones maintain backward compatibility:
- New exceptions inherit from base classes
- Type annotations don't change runtime behavior
- New config options have sensible defaults
- Logging enhancements are additive

---

## Success Criteria

### Milestone Completion

Each milestone is complete when:
- [ ] All tasks marked complete in milestone file
- [ ] All tests passing
- [ ] Mypy passes with strict mode
- [ ] Ruff passes with no errors
- [ ] Documentation updated
- [ ] No regressions in existing functionality

### Overall Success

The entire plan is successful when:
- [ ] All 5 milestones complete
- [ ] Test coverage >85%
- [ ] Build time reduced by 50%+
- [ ] Error messages are actionable
- [ ] Production debugging is easier
- [ ] Code is easier to maintain

---

## Next Steps

1. **Review milestones** - Ensure tasks are clear and achievable
2. **Prioritize** - Start with M54 (Error Handling)
3. **Create branch** - `feature/m54_error_handling`
4. **Implement T54.1** - Create custom exception hierarchy
5. **Write tests** - Test exceptions and error messages
6. **Iterate** - Complete remaining tasks in M54

For detailed task breakdowns, see individual milestone files:
- `docs/tasks/m54.md` - Error Handling & Validation
- `docs/tasks/m55.md` - Type Safety & Code Quality
- `docs/tasks/m56.md` - Testing Coverage & Quality
- `docs/tasks/m57.md` - Logging & Observability
- `docs/tasks/m58.md` - Build Performance & Caching

---

## Questions?

Refer to:
- `AGENTS.md` - Development guidelines
- `docs/api.md` - API reference
- `docs/config.md` - Configuration reference
- `docs/requirements.md` - Requirements specification
