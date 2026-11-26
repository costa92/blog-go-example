# Task: Business-day counter

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this function:

```go
func Count(from, to string, holidays []string) (int, error)
```

## Date format

Every date (`from`, `to`, and each element of `holidays`) must be a string of exactly 10 bytes in the form `YYYY-MM-DD`: four ASCII digits, `-`, two ASCII digits, `-`, two ASCII digits. No other forms are accepted (no single-digit month or day, no whitespace, no time part, no other separators, no sign). The value must be a real date in the proleptic Gregorian calendar: month `01`–`12`, and day from `01` to the number of days in that month, with February having 29 days in leap years (divisible by 4, except centuries not divisible by 400). So `2028-02-29` is valid and `2027-02-29`, `2027-04-31`, `2027-13-01`, `2027-00-10`, `2027-01-00` are invalid.

If `from`, `to`, or **any** element of `holidays` is invalid, return a non-nil error (the int value is then unspecified). This applies even to holidays outside the range. The error message text is not checked. A nil or empty `holidays` slice is fine.

## Counting

- If `from <= to`: return the number of dates `d` with `from <= d < to` (the end date `to` is **excluded**, the start date `from` is included) such that `d` is a Monday, Tuesday, Wednesday, Thursday or Friday, and `d` is not in `holidays`.
- If `to < from`: return `-Count(to, from, holidays)`.
- `from == to` gives 0.
- A date listed several times in `holidays` is excluded only once. Holidays falling on Saturday or Sunday, or outside the range, have no effect.

Examples (2027-01-04 is a Monday):

```
Count("2027-01-04", "2027-01-11", nil)                   →  5
Count("2027-01-11", "2027-01-04", nil)                   → -5
Count("2027-01-04", "2027-01-11", []string{"2027-01-06"}) →  4
Count("2027-01-09", "2027-01-11", nil)                   →  0  (Sat, Sun)
```

Ranges may span many years; the result must be exact.

Return the complete file in a single ```go code block and nothing else.
