# lokki — Implementation Tasks

This directory contains implementation tasks grouped by milestone. Each milestone should be completable and testable independently.

## Legend

- `[x]` = Completed
- `[ ]` = Not yet completed

## Milestones

| # | Status | Title | Description |
|---|--------|-------|-------------|
| 1 | [x] | Project Scaffolding | Initialize project, create directory skeleton, export public API |
| 2 | [x] | Configuration | Implement TOML config loading, `lokki/config.py` |
| 3 | [x] | Decorator & Graph Model | `@step` and `@flow` decorators, graph model |
| 4 | [x] | CLI Entry Point | CLI with subcommands: init, run, build, deploy |
| 5 | [x] | S3 & Serialisation Layer | `lokki/s3.py`, S3Store for data persistence |
| 6 | [x] | Local Runner | `lokki/runner.py` for local execution |
| 7 | [x] | Runtime Handler | `lokki/runtime/handler.py` for Lambda execution |
| 8 | [x] | Lambda Packaging | `lokki/builder/lambda_pkg.py`, Docker/ZIP packages |
| 9 | [x] | State Machine Generation | `lokki/builder/state_machine.py`, Step Functions JSON |
| 10 | [x] | CloudFormation Generation | `lokki/builder/cloudformation.py`, IaC template |
| 11 | [x] | Build Orchestrator | `lokki/builder/builder.py`, coordinate all builders |
| 12 | [x] | End-to-End & Hardening | Full pipeline integration, error handling |
| 13 | [x] | Logging & Observability | Structured logging, progress tracking |
| 14 | [x] | Deploy Command | Deploy to AWS (S3, Lambda, SFN, CFN) |
| 15 | [x] | Local Testing with LocalStack | LocalStack integration for testing |
| 16 | [x] | LocalStack Step Functions | Test SFN locally |
| 17 | [x] | TOML Configuration Format | Migrate from YAML to TOML |
| 18 | [x] | Test Coverage Improvements | Add missing unit tests |
| 19 | [x] | CLI Commands: show, logs, destroy | Status, logs, teardown commands |
| 20 | [x] | Flow-level Parameters in `.next()` | Pass params to chained steps |
| 21 | [x] | Flow-level Parameters in `.map()` and `.agg()` | Pass params to mapped steps |
| 22 | [x] | Validate Nested .map() Blocks | Prevent nested map blocks |
| 23 | [x] | Step Retry Configuration | Configurable retry behavior |
| 24 | [x] | Code Refactoring | Clean up, improve structure |
| 25 | [x] | Documentation Update | Update README, API docs |
| 26 | [x] | Type Safety Improvements | Add type hints, fix mypy errors |
| 27 | [x] | Test Coverage Improvements | More comprehensive tests |
| 28 | [x] | Security Improvements | Security best practices |
| 29 | [x] | CLI Command: invoke | Direct step invocation |
| 30 | [x] | CI/CD Setup | GitHub Actions pipeline |
| 30 | [x] | Integration Tests | End-to-end test suite |
| 31 | [x] | Migrate to moto for AWS mocking | Use moto instead of LocalStack |
| 32 | [x] | AWS Batch Support | Batch job container support |
| 33 | [x] | Map Concurrency Limit | Limit concurrent map iterations |
| 34 | [x] | API Documentation | Complete API reference |
| 36 | [x] | Unify Store Interfaces | Consistent store API |
| 37 | [x] | S3 Directory Structure Refactoring | Organize S3 paths |
| 38 | [x] | Lambda Event Dataclass Refactoring | Clean event handling |
| 40 | [x] | Flow Params via Kwargs | Simplified parameter passing |
| 41 | [x] | Runtime Module Reorganization | Restructure runtime/ |
| 42 | [x] | Code Modernization and Maintainability | Modern Python, clean code |
| 44 | [x] | Docker Image Integration Tests | Test container builds |
| 45 | [x] | Test Flows Reorganization | Organize test flows |
| 46 | [x] | Local Store Support for Lambda/Batch Handlers | Local execution in handlers |
| 47 | [x] | Optional Aggregation for Map Blocks | Map without agg |
| 48 | [x] | Architecture Support | x86_64 and arm64 |
| 49 | [x] | New Map API with Direct Pass | Simplified map syntax |
| 50 | [x] | MemoryStore for Local Development | In-memory store |
| 51 | [x] | Include Configuration for Static Files | Include files in Docker images |
| 52 | [x] | UI Console | TUI for browsing flows, runs, and logs |

## Adding New Milestones

When adding a new milestone:

1. Create a new file `docs/tasks/m{N}.md` where `{N}` is the milestone number
2. Use this template:

```markdown
# Milestone {N} — {Title}

_Purpose: Brief description of what this milestone achieves._

### Background

Why this milestone is needed.

### Tasks

- [ ] **T{N}.1** Task description
  - Subtask details

- [ ] **T{N}.2** Another task
```

3. Update this README with the new milestone in the table
4. Update docs/tasks-completed.md if milestone is completed