# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository is in a pre-code state. At time of writing it contains only `README.md`, `LICENSE`, and a Python-flavored `.gitignore` — there is no source code, no build configuration, and no tests yet.

The `README.md` indicates the intended project is a **mail assistant**. The `.gitignore` is the standard GitHub Python template (covers venv, pytest, mypy, ruff, marimo, streamlit, etc.), which signals the project is expected to be written in Python but does not yet commit to a specific framework, package manager, or layout.

## Working in this repo

Until source files exist, there are no build/lint/test commands to document. When establishing the project:

- Confirm the package manager (pip/uv/poetry/pdm — all are anticipated by `.gitignore`) with the user before scaffolding, rather than assuming.
- Confirm whether the mail assistant will be a CLI, a Streamlit/Marimo app, or a service — `.gitignore` leaves all of these open.
- Once a layout is chosen, replace this section with the real build/test/run commands and the architectural overview.
