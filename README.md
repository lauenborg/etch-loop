```
  ███████╗████████╗ ██████╗██╗  ██╗
  ██╔════╝╚══██╔══╝██╔════╝██║  ██║
  █████╗     ██║   ██║     ███████║
  ██╔══╝     ██║   ██║     ██╔══██║
  ███████╗   ██║   ╚██████╗██║  ██║
  ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝  loop
```

> Run Claude Code in a scan-fix-break loop until your codebase is clean.

---

```
╭───────────────────────── etch loop v0.5.5  my-project ─────────────────────────╮
│ -  iteration  1                                                                 │
│ x  scanner    issues found   3 bugs — null deref auth.py:42, off-by-one...     │
│ +  fixer      committed      fixed 3 issues — null guard in auth.py, bounds... │
│ x  breaker    issues         unguarded access still reachable in session.py     │
│ -  iteration  2                                                                 │
│ +  scanner    all clear      no confirmed bugs found                            │
│ +  runner     all clear      wrote 4 tests, all 31 passed                      │
╰───────────────── iterations 2   fixes 1   breaker issues 1   3m 12s elapsed ───╯
```

---

## install

```bash
uv tool install etch-loop
```

Or with pip:

```bash
pip install etch-loop
```

## usage

```bash
etch init                        # analyze codebase, write prompt files to etch-loop/
etch run                         # start the loop
etch run "the auth module"       # focus on a specific area
etch run -n 5                    # max 5 iterations
etch run --no-commit             # fix without committing
etch run --no-git                # disable all git operations
etch run --dry-run               # preview prompt, don't run
etch run --verbose               # stream full Claude output
```

---

## how it works

Each iteration runs four phases: **scan → fix → break**, then once everything is clean: **run**.

### 1. Scanner
Reads the codebase and produces a precise list of confirmed bugs — file paths, line numbers, one-line descriptions. Only genuine issues, no style notes.

### 2. Fixer
Receives the scanner's list and fixes exactly those issues. Commits each fix with a summary message. Does not refactor or touch code unrelated to the reported bugs.

### 3. Breaker
Adversarially reviews only the files the fixer just changed, looking for anything introduced or missed. If it finds nothing, the loop stops clean. If it finds issues, the next iteration's scanner re-checks those specific spots to confirm what's actually still broken.

### 4. Runner *(final step)*
Runs only when the loop exits cleanly. Writes targeted tests for what was changed, runs the full test suite, then deletes the test files it created. Reports pass/fail.

```
loop exits clean
       │
       ▼
   [ runner ]  →  writes tests  →  runs suite  →  cleans up  →  ETCH_ALL_CLEAR
```

Each agent writes a short `<etch_summary>` that appears directly in the terminal dashboard. The fixer's summary doubles as the git commit message.

---

## etch init

`etch init` runs Claude against your codebase, detects languages and structure, then writes four prompt files tailored to your project into an `etch-loop/` subfolder. No placeholders to fill in.

```
╭─ etch init v0.5.5 ────────────────────────────────╮
│ >  analyzing   ░░░░░▓▒ ░░░░░░░░░░░░░░░░░░░░░░░░   │
│ +  analyzed codebase                               │
│ +  etch-loop/SCAN.md                               │
│ +  etch-loop/ETCH.md                               │
│ +  etch-loop/BREAK.md                              │
│ +  etch-loop/RUN.md                                │
╰────────────────────────────────────────────────────╯
```

| File | Purpose |
|---|---|
| `etch-loop/SCAN.md` | Scanner prompt — what to look for and how to report findings |
| `etch-loop/ETCH.md` | Fixer prompt — surgical fixes only, no refactoring |
| `etch-loop/BREAK.md` | Breaker prompt — adversarial review of changed files |
| `etch-loop/RUN.md` | Runner prompt — write tests, run suite, clean up |

All four files are editable. The `etch-loop/` directory is excluded from analysis so etch never reads its own files as part of your codebase.

Run reports are saved to `etch-loop/etch-reports/` after each run.

---

## reports

After every run, a markdown report is saved to `etch-loop/etch-reports/`:

```
etch-loop/etch-reports/etch-report-2026-03-10-15-31.md
```

It contains the full iteration log — what each phase found, what was fixed, and runner results.

---

## requirements

- Python 3.11+
- [`claude`](https://claude.ai/code) CLI installed and authenticated
- A git repository (optional — use `--no-git` to skip all git operations)
