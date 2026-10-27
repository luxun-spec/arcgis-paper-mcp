# ArcGIS Paper MCP Implementation Plan

> Execute inline using superpowers:executing-plans; use test-driven-development for behavior.

**Goal:** Provide a working ArcGIS Pro MCP for two editable scientific map templates and publish it to GitHub.
**Architecture:** Validated JSON jobs, a stdio MCP front end, and ArcPy backend reachable through either local file queue or ArcGIS Python subprocess. No arbitrary code execution tools.
**Tech Stack:** Python 3.11+, MCP SDK 1.x, ArcPy 3.4+.
**Spec:** ../specs/2026-10-27-paper-maps-design.md

## Constraints / review focus
Unknown CRS, relative paths, non-metre hydrology inputs, expired jobs and overwriting source APRX must fail clearly. Optional layers, offline operation and missing cartographic styles must be accounted for. Publication excludes real datasets and machine-specific paths.

## Task 1 — Validated jobs and transport
Files: src/arcgis_paper_mcp/{config,transport,cli,server}.py, tests/test_core.py, pyproject.toml.
- [x] Write and run failing tests for JSON normalization, layout positions, invalid values, queue expiry and allowlisted dispatch.
- [x] Implement configuration, template geometry, atomic transport and MCP operations.
- [x] Run unit tests and real stdio MCP smoke test.

## Task 2 — Native ArcGIS cartography and analysis
Files: src/arcgis_paper_mcp/{backend,bridge,demo}.py, tests/test_backend.py.
- [x] Write failing tests for ArcPy preflight and dispatch contract using minimal dependency fakes where ArcPy is unavailable.
- [x] Implement Pro bridge main-thread timer, headless runner, two map templates, style/CRS checks, native map surrounds, export manifests and Spatial Analyst hydrology.
- [x] Generate synthetic data and test both templates with installed ArcGIS Python; inspect PNGs and fix observed issues.

## Task 3 — Portable release
Files: README.md, docs/, examples/, .github/workflows/tests.yml, LICENSE.
- [x] Document installation, bridge lifecycle, client configuration, data provenance and verified limitations.
- [x] Verify install, CLI, tests, protocol, archive and source exclusions.
- [x] Initialize dedicated git repository, commit and create/push GitHub repository; verify remote contents and report live URL.
