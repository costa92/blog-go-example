# Task: Semantic Version comparison

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this function:

```go
func Compare(a, b string) (int, error)
```

`Compare` parses two version strings according to Semantic Versioning 2.0.0 and returns `-1` if `a` has lower precedence than `b`, `0` if they have equal precedence, and `1` if `a` has higher precedence. If either string is invalid, it returns a non-nil error (the int value is then unspecified). The error message text is not checked.

## Syntax

A version string has the form

```
[v]MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
```

- An optional single leading lowercase `v` is allowed and ignored (`v1.2.3` is the same as `1.2.3`). Uppercase `V`, more than one `v`, or any other prefix is invalid. No surrounding whitespace is allowed.
- `MAJOR`, `MINOR`, `PATCH` are all required and are numeric identifiers.
- A **numeric identifier** is a non-empty string of ASCII digits `0-9` with no leading zero, except the single digit `"0"` itself (`0`, `7`, `10` are valid; `01`, `00` are invalid). Numeric identifiers may be arbitrarily long (far beyond 64 bits) and must always be compared by numeric value (for example `1.0.99999999999999999999 < 1.0.100000000000000000000`).
- `PRERELEASE` (after the first `-` that follows PATCH) is one or more identifiers separated by `.`. Each pre-release identifier must be non-empty and consist only of `[0-9A-Za-z-]`. An identifier consisting only of digits is numeric and must not have a leading zero (`01` is invalid, `0` is valid). An identifier containing at least one non-digit is alphanumeric (`0a`, `-`, `x-1`, `--` are valid alphanumeric identifiers). Note that hyphens may appear inside pre-release identifiers: in `1.0.0-x-y.z`, the pre-release identifiers are `x-y` and `z`.
- `BUILD` (after `+`) is one or more identifiers separated by `.`; each must be non-empty and consist only of `[0-9A-Za-z-]` (leading zeros are allowed in build identifiers). A second `+` is invalid. If `-` and `+` are both present, `-PRERELEASE` comes before `+BUILD`; a `-` appearing after the `+` is part of the build metadata.
- Any other deviation is invalid, e.g. missing components (`1.2`), extra components (`1.2.3.4`), empty pre-release or build (`1.2.3-`, `1.2.3+`), empty identifiers (`1.2.3-a..b`), non-ASCII or other characters.

## Precedence

1. Compare MAJOR, then MINOR, then PATCH numerically.
2. If those are equal: a version with a pre-release has **lower** precedence than the same version without one (`1.0.0-alpha < 1.0.0`).
3. If both have pre-releases, compare identifiers left to right:
   - two numeric identifiers compare numerically;
   - two alphanumeric identifiers compare lexically in ASCII byte order;
   - a numeric identifier has lower precedence than an alphanumeric one;
   - if all identifiers of the shorter list equal the corresponding identifiers of the longer one, the shorter list has lower precedence.
4. Build metadata is validated but **ignored** for precedence (`1.0.0+a` and `1.0.0+b` compare equal).

Example chain (each lower than the next):
`1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0`

Return the complete file in a single ```go code block and nothing else.
