# ⚡ CAPLBolt ⚡

Welcome to the CAPLBolt repository. This tool is designed to automate the generation of CAPL scripts for CAN and SOME/IP testing by parsing Excel requirement sheets and ARXML databases, mapping the data, and compiling it through Jinja2 templates.

It features both a robust Command-Line Interface (CLI) for seamless CI/CD pipeline integration and a blazing-fast, modern PyQt6 Graphical User Interface (GUI) for desktop users.

## 🚀 Getting Started (Environment Setup)

This project relies on uv for lightning-fast dependency management. Ensure uv is installed on your system (e.g., pip install uv or via your package manager).

### 1. Environment Setup

Create and activate an isolated virtual environment:

  ```
  uv venv
  # Linux/macOS: source .venv/bin/activate
  # Windows: .venv\Scripts\activate
  ```

### 2. Install Dependencies

Choose the installation mode that fits your workflow:

👉 Development Setup (For Contributors)

 Syncs the .venv with our lockfile and installs core + dev tools (Ruff, Pytest, PyInstaller).
  ```
  uv sync --extra dev
  ```

(Note: If you add new dependencies to pyproject.toml, run this command again to update the lockfile).

👉 Production / Standard Setup

 Installs only the core application without the dev overhead.

  ```
  uv pip install .
  ```

## 🛠 Development Workflow

As a contributor, you are expected to use the following tools to maintain code quality.
Code Linting & Formatting (Ruff)

We use Ruff to replace Flake8, Black, and isort. Its configuration is located at the bottom of the pyproject.toml.

  Lint & Auto-fix:   ```  ruff check . --fix ```

  Format the code (Auto-formatting):  ```  ruff format .  ```

## Running Tests (Pytest)

All tests are located in the tests/ directory. Ensure your code passes all tests before opening a Pull Request.

  Run all tests: 
   ```
   pytest
   ```

  Run tests with verbose output: 
  ```
  pytest -v
  ```


## 📦 Building the Executable

To package the application into a standalone .exe for end-users, ensure your dev environment is active and run:

  Ensure your virtual environment is active and dev dependencies are installed.

  Run the build command:
  ```
  pyinstaller build_config.spec --clean
  ```

  The compiled executable (CAPLBolt.exe), bundled with all necessary UI assets and Jinja templates, will be output to the dist/ directory.

## 🤝 Contributing Guidelines

We follow a standard Git Feature Branch Workflow.

1. Branch Naming Convention

Create a branch off master for your work. Use descriptive prefixes:

  - Features: feature/short-description (e.g., feature/add-someip-parser)

  - Bug Fixes: bugfix/issue-description (e.g., bugfix/gui-scaling-fix)

  - Docs/Chores: docs/update-readme or chore/update-deps

    ```
    git checkout -b feature/your-feature-name
    ```

2. Making Changes

    Write clean, documented code.

    Run ruff check . and ruff format . before committing.

    Add or update pytest cases in the tests/ directory for any new logic.

3. Creating a Pull Request (PR)

    Push your branch to the remote repository:
    ```
    git push origin feature/your-feature-name
    ```

    Open a Pull Request against the master branch.

    Provide a clear description of the changes, the problem solved, and any required testing steps.

4. Merging

    All PRs require at least one approval from a core maintainer.

    CI/CD checks (Ruff and Pytest) must pass.

    We prefer Rebase and Merge to keep the master history linear, clean and readable.
   

### Thank you for contributing to the CAPL Bolt! If you encounter any environmental issues, please reach out to swathi or one of the core maintainers.

