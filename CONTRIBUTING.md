# Contributing to AgentOps

Thank you for your interest in contributing to AgentOps! This project aims to
demonstrate how multi-agent systems can safely automate infrastructure
remediation.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/agentops.git
   cd agentops
   ```
3. Create a virtual environment and install dev dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
4. Run the tests:
   ```bash
   pytest -v
   ```

## Development Guidelines

### Code Style
- We use `ruff` for linting and formatting
- Type hints are required for all public APIs
- Docstrings follow Google style

### Testing
- All new features must include tests
- Maintain 50+ tests (currently exceeded)
- Run `pytest --cov=agentops` to check coverage

### Safety First
- Every remediation action must have a rollback plan
- HITL approval gates cannot be bypassed in production
- Kill switch must remain functional at all times
- Blast radius limits must be enforced

### Architecture Principles
- Agents communicate only through the A2A protocol
- All decisions are logged for audit
- State machines enforce valid lifecycle transitions
- DAG-based orchestration ensures correct execution order

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for your changes
3. Ensure all tests pass: `pytest -v`
4. Ensure linting passes: `ruff check src/ tests/`
5. Write a clear PR description
6. Submit for review

## Reporting Issues

Please use GitHub Issues with the following template:
- **What happened**: Description of the issue
- **Expected behavior**: What should have happened
- **Steps to reproduce**: Minimal reproduction steps
- **Environment**: Python version, OS, etc.

## Code of Conduct

Be respectful, constructive, and collaborative. We're building safety-critical
systems — precision and thoughtfulness matter.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.
