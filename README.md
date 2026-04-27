Welcome to the **CAPL Generation Tool** repository. This tool is designed to automate the generation of CAPL scripts for CAN and SOME/IP testing by parsing Excel requirement sheets and utilizing Jinja2 templates.

It features both a **Command-Line Interface (CLI)** for CI/CD pipeline integration and a modern **Tkinter Graphical User Interface (GUI)**.

## 🚀 Getting Started (Environment Setup)

We use uv, an extremely fast Python package and project manager written in Rust. It replaces standard pip and handles our pyproject.toml seamlessly.

### 1. Install uv

If you do not have uv installed globally:

    macOS / Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

    Windows (PowerShell): powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    Alternative (via pip): pip install uv

### 2. Create and Activate the Virtual Environment

Create an isolated environment using uv:

  ```
  uv venv
  ```

Activate the environment:

Windows: 
  ```
  .venv\Scripts\activate
  ```

Linux / macOS: 
  ```
  source .venv/bin/activate
  ```

### 3. Install Dependencies

We have two distinct installation modes depending on what you are trying to do.

👉 Development Setup (For Contributors)

Installs the core application plus development tools like Ruff, Pytest, and PyInstaller. This command reads pyproject.toml and syncs your .venv perfectly with the uv.lock file.
  ```
  uv sync --extra dev
  ```

(Note: If you add new dependencies to pyproject.toml, run this command again to update the lockfile).

👉 Production / Standard Setup

If you only want to run the tool via Python without the development overhead (e.g., in a lightweight CI/CD runner):

  ```
  uv pip install .
  ```

## 🛠 Development Tools

As a contributor, you are expected to use the following tools to maintain code quality.
Code Linting & Formatting (Ruff)

We use Ruff to replace Flake8, Black, and isort. Its configuration is located at the bottom of the pyproject.toml.

  Check for issues (Lint): 
  ```
  ruff check .
  ```
    
  Auto-fix fixable issues: 
  ```
  ruff check . --fix
  ```

  Format the code (Auto-formatting):
  ```
  ruff format .
  ```

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


## 📦 Building the Executable (.exe)

To ship the tool to clients or users without Python installed, we package the application using PyInstaller. The configuration is managed in build_config.spec, which ensures UI assets (gui/images/) and templates (templates/) are bundled correctly.

  Ensure your virtual environment is active and dev dependencies are installed.

  Run the build command:
  ```
  pyinstaller build_config.spec --clean
  ```

  The standalone executable will be generated inside the dist/ folder as CAPL_Gen_Tool.exe.

## 🤝 Contributing Guidelines

We follow a standard Git Feature Branch Workflow.

1. Branch Naming Convention

Create a branch off main for your work. Use descriptive prefixes:

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

    Open a Pull Request against the main branch.

    Provide a clear description of the changes, the problem solved, and any testing steps.

4. Merging

    All PRs require at least one approval from a core maintainer.

    CI/CD checks (Ruff and Pytest) must pass.

    We prefer Rebase and Merge to keep the main history clean and readable.
   

### Thank you for contributing to the CAPL Generation Tool! If you encounter any environmental issues, please reach out to one of the maintainers.

