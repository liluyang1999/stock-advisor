# A股策略助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建并交付一个只使用 Python 技术栈的 Windows EXE，用于输入 A 股代码并生成当日买入、卖出或持有建议，同时附带 HTML 说明书和构建说明。

**Architecture:** 使用 Python 标准库实现桌面界面、行情获取、指标计算和建议引擎；核心逻辑与 Tkinter 界面分离，便于测试和打包。使用 PyInstaller 作为 Python 生态打包器生成单文件 EXE。

**Tech Stack:** Python 3.14, Tkinter, urllib, unittest, PyInstaller.

---

### Task 1: Core Tests

**Files:**
- Create: `work/stock_advisor/tests/test_symbols.py`
- Create: `work/stock_advisor/tests/test_engine.py`
- Create: `work/stock_advisor/tests/test_provider.py`

- [x] **Step 1: Write failing tests**

覆盖股票代码解析、行情解析、指标和三类建议。

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest discover -s work/stock_advisor/tests -v`

Expected: FAIL because production modules do not exist yet.

### Task 2: Core Modules

**Files:**
- Create: `work/stock_advisor/src/stock_advisor/__init__.py`
- Create: `work/stock_advisor/src/stock_advisor/models.py`
- Create: `work/stock_advisor/src/stock_advisor/symbols.py`
- Create: `work/stock_advisor/src/stock_advisor/data_provider.py`
- Create: `work/stock_advisor/src/stock_advisor/engine.py`

- [ ] **Step 1: Implement typed dataclasses and symbol parsing**

Define models and code normalization.

- [ ] **Step 2: Implement data provider parsing**

Parse Eastmoney JSON into typed quote and K-line records.

- [ ] **Step 3: Implement indicator and advice engine**

Compute MA, RSI, trend, volume, risk and recommendation.

- [ ] **Step 4: Run tests until green**

Run: `python -m unittest discover -s work/stock_advisor/tests -v`

Expected: PASS.

### Task 3: Desktop App

**Files:**
- Create: `work/stock_advisor/src/stock_advisor/app.py`
- Create: `work/stock_advisor/main.py`

- [ ] **Step 1: Implement Tkinter interface**

Provide code input, analyze button, result table, details panel and disclaimer.

- [ ] **Step 2: Add CLI self-test mode**

`python work/stock_advisor/main.py --self-test` should execute the strategy engine without network.

- [ ] **Step 3: Run syntax and unit checks**

Run: `python -m py_compile work/stock_advisor/main.py work/stock_advisor/src/stock_advisor/*.py`

Expected: exit code 0.

### Task 4: Documentation

**Files:**
- Create: `outputs/stock_advisor_manual.html`

- [ ] **Step 1: Write HTML manual**

Include usage, data source, algorithm structure, risk disclaimer, build and packaging steps.

### Task 5: Packaging

**Files:**
- Create: `work/stock_advisor/build_exe.py`
- Create: `work/stock_advisor/requirements-build.txt`
- Output: `outputs/A股策略助手.exe`

- [ ] **Step 1: Install PyInstaller if missing**

Run: `python -m pip install pyinstaller`

Expected: PyInstaller available in the Python environment.

- [ ] **Step 2: Build EXE**

Run: `python work/stock_advisor/build_exe.py`

Expected: single-file EXE copied to `outputs/A股策略助手.exe`.

- [ ] **Step 3: Verify EXE**

Run: `outputs\A股策略助手.exe --self-test`

Expected: exit code 0 and a sample HOLD/BUY/SELL result printed.
