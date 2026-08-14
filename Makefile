# SVN Desktop Suite — Top-Level Makefile
# Orchestrates building, testing, and packaging both applications.
#
# All targets automatically create and use a virtual environment at .venv/
# Dependencies are installed on first run; subsequent runs reuse the venv.

.PHONY: help venv build-all build-client build-server \
        test-all test-shared test-client test-server \
        lint-all typecheck coverage \
        package-all package-flatpak package-deb \
        install-client install-server \
        vendor-shared gen-pip-sources \
        clean clean-venv \
        dev-client dev-server dev-all \
        run-client run-server

# ---------------------------------------------------------------------------
# Virtual environment paths (auto-created by the venv target)
# ---------------------------------------------------------------------------
VENV_DIR    := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP    := $(VENV_DIR)/bin/pip
VENV_BIN    := $(VENV_DIR)/bin

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Virtual environment bootstrap
# ---------------------------------------------------------------------------

venv: $(VENV_PYTHON) ## Create virtual environment and install all dependencies

$(VENV_PYTHON):
	@echo "=== Creating virtual environment at $(VENV_DIR)/ ==="
	python3 -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip setuptools wheel -q
	$(VENV_PIP) install "PySide6>=6.7" "keyring>=25.0" -q
	$(VENV_PIP) install "pytest>=8.0" "pytest-qt>=4.4" "pytest-cov>=5.0" -q
	$(VENV_PIP) install "ruff>=0.4" "mypy>=1.10" "build" -q
	@echo "=== Virtual environment ready ==="

# ---------------------------------------------------------------------------
# Development install (editable mode inside venv)
# ---------------------------------------------------------------------------

dev-client: venv ## Install SVN Client in editable mode (inside .venv)
	$(VENV_PIP) install -e svn_client[dev] -q

dev-server: venv ## Install SVN Server Admin in editable mode (inside .venv)
	$(VENV_PIP) install -e svn_server[dev] -q

dev-all: dev-client dev-server ## Install both apps in editable mode

# ---------------------------------------------------------------------------
# Run (launches app from venv)
# ---------------------------------------------------------------------------

run-client: venv ## Run SVN Client from virtual environment
	PYTHONPATH=. $(VENV_PYTHON) -m svn_client

run-server: venv ## Run SVN Server Admin from virtual environment
	PYTHONPATH=. $(VENV_PYTHON) -m svn_server

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

build-client: venv ## Build SVN Client wheel
	$(VENV_PYTHON) -m build svn_client

build-server: venv ## Build SVN Server Admin wheel
	$(VENV_PYTHON) -m build svn_server

build-all: build-client build-server ## Build both wheels

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

test-shared: venv ## Run shared library tests
	PYTHONPATH=. $(VENV_PYTHON) -m pytest svn_shared/tests/ -v --tb=short

test-client: venv ## Run client tests
	PYTHONPATH=. $(VENV_PYTHON) -m pytest svn_client/tests/ -v --tb=short

test-server: venv ## Run server tests
	PYTHONPATH=. $(VENV_PYTHON) -m pytest svn_server/tests/ -v --tb=short

test-all: venv ## Run all tests
	PYTHONPATH=. $(VENV_PYTHON) -m pytest svn_shared/tests/ svn_client/tests/ svn_server/tests/ -v --tb=short

coverage: venv ## Run tests with coverage on shared library
	PYTHONPATH=. $(VENV_PYTHON) -m pytest svn_shared/tests/ --cov=svn_shared --cov-report=html --cov-report=term

# ---------------------------------------------------------------------------
# Lint & Type Check
# ---------------------------------------------------------------------------

lint-all: venv ## Lint all packages
	$(VENV_BIN)/ruff check svn_shared/ svn_client/ svn_server/

typecheck: venv ## Type-check all packages
	PYTHONPATH=. $(VENV_BIN)/mypy svn_shared/ svn_client/ svn_server/

# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

package-all: vendor-shared package-flatpak package-deb ## Build all distribution packages (Flatpak + .deb)

package-flatpak: ## Build Flatpak bundles for both apps (requires flatpak-builder + KDE runtime)
	@echo "=== Packaging SVN Client as Flatpak ==="
	bash scripts/package-client-flatpak.sh
	@echo "=== Packaging SVN Server Admin as Flatpak ==="
	bash scripts/package-server-flatpak.sh

package-deb: ## Build Debian .deb packages for both apps (requires debhelper)
	@echo "=== Packaging SVN Client as .deb ==="
	bash scripts/package-client-deb.sh
	@echo "=== Packaging SVN Server Admin as .deb ==="
	bash scripts/package-server-deb.sh

install-client: ## Install SVN Client .deb (requires sudo)
	sudo dpkg -i svn_client/dist/svn-client_*.deb

install-server: ## Install SVN Server Admin .deb (requires sudo)
	sudo dpkg -i svn_server/dist/svn-server-admin_*.deb

vendor-shared: ## Copy svn_shared/ into each app package directory for standalone builds
	bash scripts/vendor-shared.sh

gen-pip-sources: venv ## Generate flatpak-pip-generator JSON files for offline Flatpak builds
	@echo "=== Generating Python wheel source manifests for Flatpak ==="
	$(VENV_PIP) install flatpak-pip-generator -q
	$(VENV_BIN)/flatpak-pip-generator PySide6 keyring SecretStorage jeepney \
	    --output svn_client/flatpak/python-deps
	cp svn_client/flatpak/python-deps.json svn_server/flatpak/python-deps.json
	@echo "=== Done. Commit svn_client/flatpak/python-deps.json and svn_server/flatpak/python-deps.json ==="

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

clean: ## Remove build artifacts (keeps .venv)
	rm -rf svn_client/dist svn_client/build svn_client/*.egg-info
	rm -rf svn_server/dist svn_server/build svn_server/*.egg-info
	rm -rf flatpak-build flatpak-repo
	rm -rf .kiro_tmp htmlcov .mypy_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-venv: clean ## Remove build artifacts AND the virtual environment
	rm -rf $(VENV_DIR)
	@echo "Virtual environment removed. Run 'make venv' to recreate."
