# Atlassian User Suspend CLI - Makefile
# Convenient commands for environment setup and maintenance

# Detect OS for cross-platform compatibility
UNAME_S := $(shell uname -s 2>/dev/null || echo Windows)
ifeq ($(UNAME_S),Linux)
	VENV_BIN = venv/bin
	VENV_ACTIVATE = source venv/bin/activate
	PYTHON = python3
endif
ifeq ($(UNAME_S),Darwin)
	VENV_BIN = venv/bin  
	VENV_ACTIVATE = source venv/bin/activate
	PYTHON = python3
endif
ifeq ($(UNAME_S),Windows)
	VENV_BIN = venv\Scripts
	VENV_ACTIVATE = venv\Scripts\activate.bat
	PYTHON = python
endif
ifneq (,$(findstring MINGW,$(UNAME_S)))
	VENV_BIN = venv/Scripts
	VENV_ACTIVATE = source venv/Scripts/activate  
	PYTHON = python
endif

.PHONY: help activate install setup test clean status shell run-test run-show-users run-search run-suspend-dry

# Default target
help:
	@echo "Atlassian User Suspend CLI - Available commands:"
	@echo ""
	@echo "Environment Setup:"
	@echo "  make activate    - Create virtual environment and install dependencies"
	@echo "  make install     - Install Python dependencies (in current environment)"
	@echo "  make setup       - Create .env file from template"
	@echo "  make shell       - Start interactive shell with activated environment"
	@echo ""
	@echo "Testing:"
	@echo "  make test        - Test API connection"
	@echo "  make run-test    - Test API connection (in virtual environment)"
	@echo ""
	@echo "Running Commands:"
	@echo "  make run-show-users - Show all users (in virtual environment)"
	@echo "  make run-search EMAIL=user@example.com - Search specific user"
	@echo "  make run-suspend-dry - Test suspend operation (dry-run)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean       - Clean logs and cache files"
	@echo "  make status      - Check project status"
	@echo ""
	@echo "Script Usage:"
	@echo "  ./test_connection.py           - Test API connection"
	@echo "  ./atlassian-user-suspend-cli.py show-cloud-users - Show all users"
	@echo "  ./atlassian-user-suspend-cli.py search user@example.com - Search user"
	@echo "  ./atlassian-user-suspend-cli.py suspend --dry-run - Test suspend"
	@echo "  ./atlassian-user-suspend-cli.py restore --test - Test restore"

# Virtual environment management
activate:
	@echo "Setting up virtual environment..."
	@mkdir -p logs
	@if [ -d "venv" ]; then \
		echo "[CHECK] Virtual environment already exists"; \
	else \
		echo "[SETUP] Creating virtual environment..."; \
		$(PYTHON) -m venv venv; \
		echo "[SETUP] Installing dependencies..."; \
		$(VENV_BIN)/pip install --upgrade pip; \
		$(VENV_BIN)/pip install -r requirements.txt; \
		echo "[CHECK] Virtual environment created successfully"; \
	fi
	@echo ""
	@echo "Virtual environment ready!"
	@echo ""
	@echo "📋 Ways to work with virtual environment:"
	@echo ""
	@echo "1️⃣  Interactive shell:"
	@echo "   make shell"
	@echo ""
	@echo "2️⃣  Direct commands:"
	@echo "   make run-test         # Test connection"
	@echo "   make run-show-users   # Show all users"
	@echo ""
	@echo "3️⃣  Manual activation (if not using make shell):"
	@echo "   $(VENV_ACTIVATE)"

# Setup and installation
install:
	pip install -r requirements.txt

setup:
	@if [ ! -f .env ]; then \
		cp .env-example .env; \
		echo "Created .env file from template. Please edit it with your credentials."; \
		echo "Required: ORG_ID and API_KEY"; \
	else \
		echo ".env file already exists"; \
	fi

# Testing
test:
	@echo "Testing API connection..."
	@chmod +x test_connection.py
	./test_connection.py

# Commands with virtual environment activated
shell:
	@chmod +x activate_shell.sh
	@./activate_shell.sh

run-test:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make activate' first."; \
		exit 1; \
	fi
	@echo "Testing API connection (in virtual environment)..."
	@chmod +x test_connection.py
	@$(VENV_ACTIVATE) && ./test_connection.py

run-show-users:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make activate' first."; \
		exit 1; \
	fi
	@echo "Showing all users (in virtual environment)..."
	@chmod +x atlassian-user-suspend-cli.py
	@$(VENV_ACTIVATE) && ./atlassian-user-suspend-cli.py show-cloud-users

run-search:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make activate' first."; \
		exit 1; \
	fi
	@if [ -z "$(EMAIL)" ]; then \
		echo "Usage: make run-search EMAIL=user@example.com"; \
		exit 1; \
	fi
	@echo "Searching for user: $(EMAIL) (in virtual environment)..."
	@chmod +x atlassian-user-suspend-cli.py
	@$(VENV_ACTIVATE) && ./atlassian-user-suspend-cli.py search $(EMAIL)

run-suspend-dry:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make activate' first."; \
		exit 1; \
	fi
	@echo "Running suspend dry-run (in virtual environment)..."
	@chmod +x atlassian-user-suspend-cli.py
	@$(VENV_ACTIVATE) && ./atlassian-user-suspend-cli.py suspend --dry-run

# Maintenance
clean:
	rm -rf __pycache__/
	rm -rf logs/*.log
	rm -f *_resume.json
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

clean-logs:
	rm -rf logs/
	mkdir -p logs

clean-all: clean
	rm -rf venv/
	rm -f .env

# Development (optional)
lint:
	@command -v black >/dev/null 2>&1 && black --check . || echo "black not installed"
	@command -v flake8 >/dev/null 2>&1 && flake8 . || echo "flake8 not installed"

format:
	@command -v black >/dev/null 2>&1 && black . || echo "black not installed, run: pip install black"

# Status check
status:
	@echo "Checking Atlassian User Suspend CLI status..."
	@echo ""
	@echo "Environment:"
	@if [ -d "venv" ]; then \
		echo "  [CHECK] Virtual environment exists"; \
		if [ -n "$VIRTUAL_ENV" ]; then \
			echo "  [CHECK] Virtual environment activated"; \
		else \
			echo "  [!] Virtual environment not activated (run: source venv/bin/activate)"; \
		fi \
	else \
		echo "  [X] Virtual environment missing (run: make activate)"; \
	fi
	@echo ""
	@echo "Configuration:"
	@if [ -f .env ]; then \
		echo "  [CHECK] .env file exists"; \
		if grep -q "your-organization-id" .env 2>/dev/null; then \
			echo "  [!] .env file needs to be configured"; \
		else \
			echo "  [CHECK] .env file appears configured"; \
		fi \
	else \
		echo "  [X] .env file missing (run: make setup)"; \
	fi
	@echo ""
	@echo "Scripts:"
	@if [ -x "./atlassian-user-suspend-cli.py" ]; then \
		echo "  [CHECK] atlassian-user-suspend-cli.py is executable"; \
	else \
		echo "  [!] atlassian-user-suspend-cli.py not executable (run: chmod +x atlassian-user-suspend-cli.py)"; \
	fi
	@if [ -x "./test_connection.py" ]; then \
		echo "  [CHECK] test_connection.py is executable"; \
	else \
		echo "  [!] test_connection.py not executable (run: chmod +x test_connection.py)"; \
	fi
	@echo ""
	@echo "Logs:"
	@if [ -d logs ]; then \
		echo "  [CHECK] logs directory exists"; \
		echo "  [INFO] Log files: $(ls logs/ 2>/dev/null | wc -l)"; \
	else \
		echo "  [INFO] logs directory will be created on first use"; \
	fi