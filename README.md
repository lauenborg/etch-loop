```
  ███████╗████████╗ ██████╗██╗  ██╗
  ██╔════╝╚══██╔══╝██╔════╝██║  ██║
  █████╗     ██║   ██║     ███████║
  ██╔══╝     ██║   ██║     ██╔══██║
  ███████╗   ██║   ╚██████╗██║  ██║
  ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝  loop
```

> Run Claude Code in a fix-break loop until your codebase is clean.

---

```
  iteration 1
  + fixer     committed   fix(edge): null check on user.id       [0:42]
  + breaker   issues      unguarded access on line 84            [1:03]

  iteration 2
  + fixer     committed   fix(edge): handle empty array          [0:38]
  + breaker   issues      async race in fetchConfig()            [0:51]

  iteration 3
  + fixer     committed   fix(edge): missing env fallback        [0:29]
  > breaker   running     ░░░░░░▓▓▓▒░░░░░░░░░░░░░░░░░░░░░░░░░░

  iterations 3   fixes 3   breaker issues 2   2m 14s elapsed
```

---

## install

```bash
uv tool install etch-loop
```

## usage

```bash
etch init            # scaffold ETCH.md and BREAK.md in current directory
etch run             # start the loop
etch run -n 5        # max 5 iterations
etch run --dry-run   # preview prompt, don't run
etch run --verbose   # show full Claude output
```

---

## how it works

Each iteration has two phases: **fix**, then **break**.

1. Claude reads `ETCH.md` and hunts for edge cases — null checks, unhandled errors, boundary conditions
2. If it finds something, it fixes and commits
3. A second Claude instance reads `BREAK.md` and tries to break the fix — adversarially
4. If the breaker finds nothing, the loop stops
5. If it finds something, the loop runs again from step 1

The loop exits when a full pass produces no changes **and** the breaker finds nothing to challenge.

```
  + clean pass on iteration 4
    breaker found nothing — all clear

  iterations      4
  fixer commits   4
  breaker issues  2
  total duration  3m 02s
```

---

## ETCH.md and BREAK.md

Both files are scaffolded by `etch init` and are meant to be edited.

**`ETCH.md`** — tells the fixer what to look for and how to fix it. Narrow the scope to a directory, module, or theme.

**`BREAK.md`** — tells the breaker how to challenge the fixer's work. It never edits files — only reports. It ends every run with `ETCH_ALL_CLEAR` or `ETCH_ISSUES_FOUND`.

---

## requirements

- Python 3.11+
- [`claude`](https://claude.ai/code) CLI installed and authenticated
- A git repository (etch-loop commits each fix automatically)
