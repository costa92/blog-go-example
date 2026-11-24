# tally

## What This Is

A tiny Go CLI that reads text from stdin and reports counts.

## Core Value

One pass over stdin, plain-text output that is easy to grep.

## Constraints

- Go standard library only, no third-party modules.
- Default output (`lines=N words=M`) must not change.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Words are `strings.Fields` tokens | Keep it predictable | Locked |
