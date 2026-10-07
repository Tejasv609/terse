# terse — token-saving skill for coding agents

Make your AI agent write shorter replies and read less noise, without losing
meaning. Target: **~30%+ fewer output tokens** on typical dev answers, up to
~99% off noisy tool output (logs, JSON dumps, CSVs).

Two small pieces, zero infrastructure:

| Piece | What it does | Size |
|---|---|---|
| `terse/SKILL.md` | Output rules the agent follows: answer-first, one idea per sentence, never drop negations/numbers, code stays verbatim | ~4.5 KB Markdown |
| `terse/shrink.py` | Input filter: folds repeated log lines, keeps head+tail, summarizes JSON/CSV structure before it reaches the model | ~7 KB Python (stdlib only) |

Inspired by the public [caveman](https://github.com/juliusbrussee/caveman)
project (Apache-2.0). Reimplemented from scratch — none of its code, proxy,
CLI, or binaries are used or needed.

## Setup

### 1. The skill (output side)

Copy the `terse/` folder into your agent's skills directory:

**Claude Code**
```bash
mkdir -p ~/.claude/skills && cp -r terse ~/.claude/skills/
```

**Codex CLI**
```bash
mkdir -p ~/.codex/skills && cp -r terse ~/.codex/skills/
```

**Cursor** — copy `terse/SKILL.md` to `.cursor/rules/terse.md` (project rule)
or into your global rules.

**Gemini CLI**
```bash
mkdir -p ~/.gemini/skills && cp -r terse ~/.gemini/skills/
```

**Any other agent** — paste `terse/SKILL.md` into its system prompt, memory
file, or custom instructions. It works anywhere text instructions work.

Then, in any session:

- `/terse` — standard mode (or just ask for terse replies)
- `/terse-max` — maximum brevity; fragments allowed, meaning still protected
- `/terse-off` — back to normal replies

### 2. The filter (input side)

No install. Pipe anything noisy through it:

```bash
pytest 2>&1 | python3 terse/shrink.py
python3 terse/shrink.py build.log --stats     # see before/after savings
some_command 2>&1 | python3 terse/shrink.py --max-lines 80
```

Works on logs, test output, JSON, and CSV. Small outputs pass through
untouched.

## What it does

**Output side** — eight rules the agent applies to its own prose:

1. Answer first: `[thing] [action] [reason]. [next step].` No greeting, no recap.
2. One idea per sentence, short sentences, active voice.
3. Never drop meaning: `not`/`never`/`no`/`only`, numbers, units, and names
   always stay exact.
4. Payload verbatim: code, commands, paths, and error messages are never
   paraphrased or shortened.
5. Quiet tool runs: no narration between tool calls.
6. Full sentences return for security warnings, destructive actions, and
   confused users.
7. No roleplay or affectation.
8. Your prompts are never rewritten.

A pre-send checklist (no announcing-the-plan openers, no recap closers, every
negation/path/number intact) runs before every reply.

**Input side** — `shrink.py` compresses what the agent reads:

- *Logs:* folds consecutive duplicate lines (`heartbeat ok [repeated x47]`),
  keeps the head and tail with an explicit `N lines omitted` marker.
- *JSON:* prints a structural summary (keys, types, array lengths, samples).
- *CSV:* header plus first/last sample rows with a row count.

Measured on synthetic fixtures: 78% off a noisy 600-line log, 99% off a
200-object JSON blob and a 1000-row CSV. Run with `--stats` for your own
numbers.

## Security

Built for machines where trust is earned, not assumed:

- **Two files, fully auditable.** Read `SKILL.md` and `shrink.py` end to end in
  about ten minutes. That is the entire codebase.
- **No network calls.** The skill is text the agent reads; `shrink.py` reads
  stdin (or a file you name) and writes stdout. Neither can phone home —
  there is no socket code, no URL, no hostname anywhere in the repo.
- **No telemetry.** There is nothing to phone home *with*.
- **No binaries, no installer, no dependencies.** `shrink.py` imports only the
  Python standard library. Nothing to `pip install`, nothing to compile,
  nothing signed by a stranger to trust.
- **No proxy in the middle.** Your prompts and API keys go straight to your
  LLM provider, exactly as before. Nothing intercepts, logs, or relays them.
- **No file writes.** `shrink.py` never modifies files — stats go to stderr,
  compressed output to stdout.
- **Nothing sensitive leaves the machine.** The skill contains no credentials
  and asks for none. `shrink.py` only ever sees what you explicitly pipe into
  it.
- **Safe failure modes.** Unknown input falls back to plain head/tail
  truncation; small inputs pass through byte-identical. The skill's own rules
  forbid touching code, commands, paths, and error output.

Threat model in one line: the worst this software can do is print a shorter
version of text you gave it.

## Layout

```
terse/
├── README.md          # this file
├── LICENSE            # MIT
└── terse/
    ├── SKILL.md       # the skill
    └── shrink.py      # the input filter
```

## License

MIT — see [LICENSE](LICENSE). The approach is inspired by the caveman project
(Apache-2.0); this implementation is original work.
