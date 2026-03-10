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
┌─ etch loop v0.2.0  . ───────────────────────────────────────────────┐
│                                                                      │
│  -  iteration  1                                                     │
│  +  scanner    issues found   src/auth.py:42 — no empty token check  │
│  +  fixer      committed      fix(edge): guard empty token in auth   │
│  x  breaker    issues         unguarded access still reachable       │
│                                                                      │
│  -  iteration  2                                                     │
│  +  scanner    issues found   src/auth.py:61 — missing None check    │
│  +  fixer      committed      fix(edge): null guard on session obj   │
│  >  breaker    running        ░░░░░░▓▒ ░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  iterations 2   fixes 2   breaker issues 1   1m 48s elapsed         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## install

```bash
uv tool install etch-loop
```

## usage

```bash
etch init                        # analyze codebase with Claude, write prompt files
etch run                         # start the loop
etch run "the auth module"       # focus on a specific area
etch run -n 5                    # max 5 iterations
etch run --dry-run               # preview prompt, don't run
etch run --verbose               # show full Claude output
```

---

## how it works

Each iteration has three phases: **scan → fix → break**.

1. **Scanner** reads the codebase and outputs a specific list of issues — file paths, line numbers, descriptions
2. If the scanner finds nothing, the loop stops
3. **Fixer** receives the scanner's list and fixes those exact issues, then commits
4. **Breaker** adversarially reviews the full codebase, looking for anything missed or newly introduced
5. If the breaker finds nothing, the loop stops — clean pass
6. If the breaker finds something, it's fed back to the next iteration's fixer

```
┌─ done ───────────────────────────────────────────────────┐
│                                                          │
│  iterations      3                                       │
│  fixes           3                                       │
│  breaker issues  1                                       │
│  elapsed         2m 44s                                  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## etch init

`etch init` runs Claude against your codebase before writing any files. It reads your source, detects the languages and structure, and generates three prompt files tailored to your project — no placeholders to edit.

```
┌─ etch init v0.2.0 ───────────────────────────────────────┐
│  >  analyzing  ░░░░░▓▒ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│  +  analyzed codebase                                    │
│  +  SCAN.md                                              │
│  +  ETCH.md                                              │
│  +  BREAK.md                                             │
└──────────────────────────────────────────────────────────┘
```

**`SCAN.md`** — tells the scanner what to look for and how to report findings.

**`ETCH.md`** — tells the fixer how to fix things: surgical, no refactoring, one fix per commit.

**`BREAK.md`** — tells the breaker to scan the full codebase adversarially and report anything that could go wrong.

All three files are editable. Use `etch run "focus description"` to narrow the scope without editing files.

---

## requirements

- Python 3.11+
- [`claude`](https://claude.ai/code) CLI installed and authenticated
- A git repository (etch-loop commits each fix automatically)
