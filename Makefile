# Makefile for Angelica AI

PYTHON := python
UNITTEST := -m unittest
TEST_DIR := tests

.PHONY: all run test smoke test-core test-modules test-tools test-commands lint clean help

help:
	@echo "Angelica AI Makefile"
	@echo "--------------------"
	@echo "Usage:"
	@echo "  make run           - Run the main application (tui.py)"
	@echo "  make test          - Run ALL tests"
	@echo "  make test-core     - Run core logic tests (parser, context, processor)"
	@echo "  make test-modules  - Run basic module tests"
	@echo "  make test-tools    - Run comprehensive tool tests (files, shell, search)"
	@echo "  make test-commands - Run CLI command tests (/add, /drop)"
	@echo "  make smoke         - Run end-to-end smoke user flow test"
	@echo "  make clean         - Remove temporary files (pycache, etc.)"

# Run the application
run:
	$(PYTHON) tui.py

# Run ALL tests
test:
	$(PYTHON) $(UNITTEST) discover -s $(TEST_DIR) -t .

smoke:
	$(PYTHON) $(UNITTEST) tests/test_smoke_user_flow.py

# Run specific test suites
test-core:
	$(PYTHON) $(UNITTEST) tests/test_core_logic.py

test-modules:
	$(PYTHON) $(UNITTEST) tests/test_modules.py

test-tools:
	$(PYTHON) $(UNITTEST) tests/test_tools_comprehensive.py tests/test_search_tools.py

test-commands:
	$(PYTHON) $(UNITTEST) tests/test_commands.py

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -f communication.log

# Versioning
bump-patch:
	bump-my-version bump patch

bump-minor:
	bump-my-version bump minor

bump-major:
	bump-my-version bump major
