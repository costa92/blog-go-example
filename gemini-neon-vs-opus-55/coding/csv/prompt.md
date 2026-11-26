# Task: Strict CSV parser with line-numbered errors

Write a Go file in `package solution` (Go 1.27, standard library only; do **not** use `encoding/csv`) that exports exactly this API:

```go
type ParseError struct {
	Line int
}

func (e *ParseError) Error() string

func Parse(s string) ([][]string, error)
```

## Records

- The input is a sequence of records. Each record is terminated by a **line end**, which is either `"\n"` or `"\r\n"`, except that the last record may also be terminated by the end of the input.
- Empty input `""` has **zero records**: return a slice of length 0 (nil or empty) and a nil error.
- A line end at the very end of the input terminates the last record and does **not** start another one: `"a\n"` → `[["a"]]`, `"a\r\n"` → `[["a"]]`.
- An empty line is a record with exactly one empty field: `"\n"` → `[[""]]`, `"a\n\nb"` → `[["a"], [""], ["b"]]`, `"a\n\n"` → `[["a"], [""]]`.
- Fields within a record are separated by `,`. `"a,,b"` → `[["a", "", "b"]]`, `","` → `[["", ""]]`. Records may have different numbers of fields.
- Spaces are ordinary characters and are never trimmed.
- Outside quoted fields, a `\r` that is not immediately followed by `\n` is an ordinary field character.

## Fields

- **Unquoted field**: a field whose first character is not `"`. It extends up to the next `,`, line end, or end of input. It must not contain `"` anywhere; a `"` inside an unquoted field (for example `a"b` or ` "a"` with a leading space) is an error.
- **Quoted field**: a field whose first character is `"`. Its value is everything up to the matching closing `"`, where each `""` inside represents one literal `"`. Inside the quotes, `,`, `"\n"`, `"\r\n"` and `\r` are kept verbatim as part of the value. `"a""b"` → `a"b`, `""` → empty string.
- After the closing quote of a quoted field, the next thing must be `,`, a line end (`"\n"` or `"\r\n"`), or the end of the input. Anything else is an error (for example `"a"b`, `"a" ,`, or a `\r` not followed by `\n`).
- A quoted field with no closing quote before the end of input is an error.

## Errors

On error, return `(nil, err)` where `err` is a `*ParseError` (returned directly, so `errors.As(err, &pe)` with `pe *ParseError` succeeds). `Line` is the 1-based line number of the offending position, where the line number of a position is `1 +` the number of `"\n"` characters before it in the input (newlines inside quoted fields count too):

- stray `"` inside an unquoted field: the line of that `"`;
- unexpected character after a closing quote: the line of that character;
- unterminated quoted field: the line of its **opening** quote.

`Error()` must return a non-empty string; its exact text is not checked.

Return the complete file in a single ```go code block and nothing else.
