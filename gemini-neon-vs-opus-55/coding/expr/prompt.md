# Task: Arithmetic expression evaluator

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this function:

```go
func Eval(s string) (float64, error)
```

`Eval` parses and evaluates an arithmetic expression using `float64` arithmetic. On any error it returns a non-nil error (the float value is then unspecified). The error message text is not checked.

## Tokens

- **Whitespace**: space, tab, `\n`, `\r` may appear anywhere between tokens and are ignored. Whitespace is not allowed inside a number (`1 .5` is two numbers, which is an error).
- **Number**: one of
  - digits, e.g. `3`, `042`
  - digits `.` digits, e.g. `2.5`
  - `.` digits, e.g. `.5`
  - digits `.`, e.g. `5.`
  
  where digits means one or more ASCII `0-9`. A lone `.` is not a number. There is no exponent notation, no sign inside a number literal, no hex, no `_` separators. A number token is the longest sequence matching the forms above; e.g. `1..2` is the number `1.` immediately followed by the number `.2`, which is an error (two adjacent numbers).
- **Operators**: `+ - * / ^` and parentheses `( )`.
- Any other character (letters, `%`, `,`, etc.) makes the input invalid.

## Grammar and precedence (from loosest to tightest)

1. Binary `+` and `-`: left-associative (`1-2-3 = -4`).
2. Binary `*` and `/`: left-associative (`8/4/2 = 1`).
3. Unary prefix `+` and `-`: may be repeated (`--2 = 2`, `-+-2 = 2`). Unary binds **looser** than `^` but **tighter** than `*` and `/`.
4. Binary `^` (exponentiation, computed as `math.Pow`): **right-associative** and binds tightest. Its right operand may itself start with unary signs.
5. Primary: a number, or `(` expression `)`.

Equivalent grammar:

```
expr    := term   { ("+" | "-") term }
term    := unary  { ("*" | "/") unary }
unary   := ("+" | "-") unary | power
power   := primary [ "^" unary ]
primary := number | "(" expr ")"
```

Consequences you must honor:

| input | value |
|---|---|
| `-2^2` | -4 |
| `2^-1` | 0.5 |
| `2^3^2` | 512 |
| `(2^3)^2` | 64 |
| `-3*-2` | 6 |
| `2*-3` | -6 |
| `2^-2^2` | 0.0625 (= 2^(-(2^2))) |
| `1-2-3` | -4 |
| `2*3+4*5` | 26 |

## Errors

- **Division by zero**: if the right operand of `/` evaluates to exactly `0` (including `-0`), return an error. This includes `0/0`.
- **Malformed input**: anything that does not match the grammar in full returns an error. Examples: `""`, `"   "`, `"1+"`, `"(1"`, `"1)"`, `"1 2"`, `"2^^3"`, `"()"`, `"1..2"`, `"abc"`, `"."`, `"*1"`, `"1e3"`, `"(1)(2)"`, `"2(3)"`.

Implicit multiplication does not exist. Results are compared with a relative tolerance of 1e-9.

Return the complete file in a single ```go code block and nothing else.
