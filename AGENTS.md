# Agent instructions

## Experiments and the research log

Every experiment has two homes that share one name, `<date>-<name-of-experiment>` (date as
`YYYY-MM-DD`, name in kebab-case):

- `experiments/<date>-<name-of-experiment>/` holds the one-off scripts written for that experiment and
  the artifacts specific to that run (eval logs, console output, plots, result tables). Scripts here
  are throwaway by design: they import reusable code from `src/ooc_arena/` and are not imported by
  anything else. Run them from the repo root.
- `research-log/<date>-<name-of-experiment>.md` documents the experiment. Start from
  `research-log/template.md`: context, a falsifiable hypothesis with accept/reject/inconclusive
  conditions decided before running, expected outcome, actual outcome, the exact command and
  parameters, and pointers to the artifacts in the experiment folder.

Rules of thumb:

- Do not add one-off run scripts to the repo root. Code that more than one experiment needs belongs in
  `src/ooc_arena/`.
- Point each script's eval logs at a `logs/` directory inside its experiment folder. `logs/` is
  gitignored at every depth, so eval logs stay local; anything that should be versioned (small result
  tables, plots) goes directly in the experiment folder.
- "Expected Outcome" in a research-log entry is for the human to fill in. Leave it as
  `<human fills in>` rather than writing a prediction.
- Write the research-log entry before running, and record the actual outcome in the same file after.
