# --------------------------------------------------
# Project configuration
# --------------------------------------------------

PROJECT_NAME := tikworks
SRC_DIR := src/python
DOCS_DIR := docs
DOCS_BUILD := docs/build/html
TESTS_DIR := tests

# Python executable (Maya)
MAYAPY ?= mayapy

# --------------------------------------------------
# Platform detection
# --------------------------------------------------

ifeq ($(OS),Windows_NT)
    PLATFORM := windows
    PATH_SEP := ;
    OPEN_CMD := start
    SET_PYTHONPATH = set PYTHONPATH=$(CURDIR)/$(SRC_DIR)$(PATH_SEP)%PYTHONPATH% &&
else
    PLATFORM := unix
    PATH_SEP := :
    OPEN_CMD := xdg-open
    SET_PYTHONPATH = PYTHONPATH=$(CURDIR)/$(SRC_DIR)$(PATH_SEP)$$PYTHONPATH
endif

# --------------------------------------------------
# Help system
# --------------------------------------------------

.PHONY: help
help: ## Show available commands
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | sort \
	 | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# --------------------------------------------------
# Documentation
# --------------------------------------------------

.PHONY: docs
docs: ## Build Sphinx documentation
	cd $(DOCS_DIR) && make html

.PHONY: show-doc
show-doc: ## Open built documentation in browser
	$(OPEN_CMD) $(DOCS_BUILD)/index.html

# --------------------------------------------------
# Tests
# --------------------------------------------------

.PHONY: tests
tests: tests-unit tests-integration ## Run all tests

.PHONY: tests-unit
tests-unit: ## Run unit tests
	$(SET_PYTHONPATH) $(MAYAPY) $(TESTS_DIR)/unit/invoke.py

.PHONY: tests-integration
tests-integration: ## Run integration tests
	$(SET_PYTHONPATH) $(MAYAPY) $(TESTS_DIR)/integration/invoke.py

.PHONY: tests-ui
tests-ui: ## Run Qt UI tests (no Maya standalone)
	$(SET_PYTHONPATH) set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && $(MAYAPY) -m pytest tests/ui -q

# --------------------------------------------------
# Coverage
# --------------------------------------------------

.PHONY: tests-cov
tests-cov: ## Run all tests with coverage
	$(MAYAPY) -m coverage erase
	$(SET_PYTHONPATH) $(MAYAPY) -m coverage run $(TESTS_DIR)/unit/invoke.py
	$(SET_PYTHONPATH) $(MAYAPY) -m coverage run $(TESTS_DIR)/integration/invoke.py
	$(MAYAPY) -m coverage report

.PHONY: tests-cov-unit
tests-cov-unit: ## Run unit tests with coverage
	$(SET_PYTHONPATH) $(MAYAPY) -m coverage run $(TESTS_DIR)/unit/invoke.py

.PHONY: tests-cov-integration
tests-cov-integration: ## Run integration tests with coverage
	$(SET_PYTHONPATH) $(MAYAPY) -m coverage run $(TESTS_DIR)/integration/invoke.py

# --------------------------------------------------
# CMake Build
# --------------------------------------------------

BUILD_DIR := build

ifndef VERSION
VERSION_ERROR = \
	@echo "ERROR: VERSION is required."; \
	@echo "Usage:"; \
	@echo "  make cmake-build VERSION=2026"; \
	@echo "  make cmake-release VERSION=2026"; \
	exit 1
endif

.PHONY: cmake-build
cmake-build: ## Configure and build Debug via CMake (requires VERSION)
ifndef VERSION
	$(VERSION_ERROR)
endif
	cmake -B $(BUILD_DIR) \
	 -DMAYA_VERSION=$(VERSION) \
	 -DCMAKE_BUILD_TYPE=Debug
	cmake --build $(BUILD_DIR) --config Debug

.PHONY: cmake-release
cmake-release: ## Configure and build Release via CMake (requires VERSION)
ifndef VERSION
	$(VERSION_ERROR)
endif
	cmake -B $(BUILD_DIR) \
	 -DMAYA_VERSION=$(VERSION) \
	 -DCMAKE_BUILD_TYPE=Release
	cmake --build $(BUILD_DIR) --config Release

# --------------------------------------------------
# Package-script based build/release/dev
# --------------------------------------------------

.PHONY: build
build: ## Build using package script (requires VERSION)
ifndef VERSION
	$(error ERROR: VERSION is required. Usage: make build VERSION=2026)
endif
	python package/package.py --build $(VERSION)

.PHONY: dev
dev: ## Dev build and deploy (all Maya versions, or specify VERSION=x)
ifdef VERSION
	python package/package.py --dev $(VERSION)
else
	python package/package.py --dev
endif

.PHONY: release
release: ## Release build via package script
	python package/package.py --release

.PHONY: add-plugin
add-plugin: ## Add a new C++ plugin to the project (requires PLUGIN_NAME)
ifndef PLUGIN_NAME
	$(error ERROR: PLUGIN_NAME is required. Usage: make add-plugin PLUGIN_NAME=myPlugin)
endif
	python package/package.py --add-plugin $(PLUGIN_NAME)
