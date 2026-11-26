# Task: Display-width word wrap (mixed CJK / Latin text)

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this function:

```go
func Wrap(s string, width int) []string
```

`Wrap` breaks `s` into lines whose **display width** is at most `width`, following the rules below exactly. `width >= 2` is guaranteed. `s` is valid UTF-8 and contains no control characters other than `\n` (no tabs, no `\r`). The returned slice is never nil and never empty.

## Rune display width

A rune is **wide** (display width 2) if it lies in one of these inclusive ranges; every other rune is **narrow** (display width 1):

```
U+1100–U+115F
U+2E80–U+A4CF
U+AC00–U+D7A3
U+F900–U+FAFF
U+FE30–U+FE4F
U+FF00–U+FF60
U+FFE0–U+FFE6
U+20000–U+3FFFD
```

The width of a string is the sum of the widths of its runes. Only U+0020 (space) is a separator; every other rune, including non-ASCII punctuation such as `，` or `。`, is an ordinary narrow or wide rune according to the table.

## Paragraphs

Split `s` on `\n` into paragraphs (so `n` newlines give `n+1` paragraphs; `""` is one empty paragraph, and `"a\n"` is the paragraphs `"a"` and `""`). Wrap each paragraph independently and concatenate their lines in order. A paragraph that contains no non-space rune produces exactly one line, the empty string `""`.

## Words and units (within one paragraph)

1. **Words**: split the paragraph on spaces; a word is a maximal run of non-space runes. Runs of several spaces count as a single separator; leading and trailing spaces are dropped.
2. **Units**: each word is divided, left to right, into units:
   - each wide rune is a unit by itself;
   - each maximal run of consecutive narrow runes is a unit.
   
   Example: the word `用Go语言,ok` has the units `用`, `Go`, `语`, `言`, `,ok`.
3. **Hard split**: a narrow unit whose width is greater than `width` is replaced by consecutive chunks of exactly `width` runes each, starting from its first rune (the last chunk holds the remainder and may be shorter). Chunks are units of the same word. This split is fixed and does not depend on where the unit would land on a line. Wide units never need splitting.

## Greedy line filling

Process the units of the paragraph in order, building the current line:

- The **joiner** between a unit and the unit before it is one space (`" "`, width 1) if the two units belong to different words, and the empty string if they belong to the same word.
- If the current line is empty, the unit starts the line (no joiner).
- Otherwise, if `width(current line) + width(joiner) + width(unit) <= width`, append the joiner and the unit to the current line.
- Otherwise, emit the current line, and start a new line with the unit alone (the joiner is dropped).

After the last unit, emit the current line. Lines therefore never start or end with a space, and no space is ever added between units that were adjacent without a space in the input.

## Examples

```
Wrap("the quick brown fox jumps over the lazy dog", 10)
  → ["the quick", "brown fox", "jumps over", "the lazy", "dog"]
Wrap("我爱Go语言", 6)            → ["我爱Go", "语言"]
Wrap("使用 Go 编写 服务", 7)      → ["使用 Go", "编写 服", "务"]
Wrap("abcdefghij k", 4)          → ["abcd", "efgh", "ij k"]
Wrap("a\n\nb", 5)                → ["a", "", "b"]
```

Return the complete file in a single ```go code block and nothing else.
