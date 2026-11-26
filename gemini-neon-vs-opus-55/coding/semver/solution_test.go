package solution

import "testing"

func mustCompare(t *testing.T, a, b string, want int) {
	t.Helper()
	got, err := Compare(a, b)
	if err != nil {
		t.Fatalf("Compare(%q, %q) error: %v", a, b, err)
	}
	if got != want {
		t.Fatalf("Compare(%q, %q) = %d, want %d", a, b, got, want)
	}
}

func TestSpecOrderingChain(t *testing.T) {
	chain := []string{
		"1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
		"1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0",
	}
	for i := range chain {
		for j := range chain {
			want := 0
			if i < j {
				want = -1
			} else if i > j {
				want = 1
			}
			t.Run(chain[i]+"_vs_"+chain[j], func(t *testing.T) {
				mustCompare(t, chain[i], chain[j], want)
			})
		}
	}
}

func TestCoreNumeric(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"1.0.0", "1.0.0", 0},
		{"1.9.0", "1.10.0", -1},
		{"2.0.0", "1.99.99", 1},
		{"0.0.1", "0.0.0", 1},
		{"1.2.3", "1.2.10", -1},
		{"10.0.0", "9.0.0", 1},
		{"0.10.0", "0.9.9", 1},
	}
	for _, c := range cases {
		t.Run(c.a+"_vs_"+c.b, func(t *testing.T) { mustCompare(t, c.a, c.b, c.want) })
	}
}

func TestVPrefix(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"v1.2.3", "1.2.3", 0},
		{"v1.2.3", "v1.2.4", -1},
		{"1.3.0", "v1.2.9", 1},
		{"v1.0.0-rc.1", "1.0.0", -1},
	}
	for _, c := range cases {
		t.Run(c.a+"_vs_"+c.b, func(t *testing.T) { mustCompare(t, c.a, c.b, c.want) })
	}
}

func TestHugeNumbers(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"1.0.99999999999999999999", "1.0.100000000000000000000", -1},
		{"18446744073709551616.0.0", "18446744073709551615.0.0", 1},
		{"1.18446744073709551616.0", "1.18446744073709551616.0", 0},
		{"1.0.0-99999999999999999999", "1.0.0-100000000000000000000", -1},
		{"1.0.0-100000000000000000000", "1.0.0-a", -1},
		{"99999999999999999999.0.0", "100000000000000000000.0.0", -1},
	}
	for _, c := range cases {
		t.Run(c.a+"_vs_"+c.b, func(t *testing.T) { mustCompare(t, c.a, c.b, c.want) })
	}
}

func TestPrereleaseRules(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"1.0.0-1", "1.0.0-a", -1},
		{"1.0.0-2", "1.0.0-10", -1},
		{"1.0.0-0a", "1.0.0-1", 1},     // 0a is alphanumeric
		{"1.0.0-0a", "1.0.0-0b", -1},   // lexical
		{"1.0.0-B", "1.0.0-a", -1},     // ASCII order: uppercase first
		{"1.0.0-a.b", "1.0.0-a", 1},    // longer set is higher
		{"1.0.0-a.1", "1.0.0-a.a", -1}, // numeric < alphanumeric
		{"1.0.0-x-y.z", "1.0.0-x-y.z", 0},
		{"1.0.0-x-y", "1.0.0-x", 1}, // "x-y" > "x" lexically
		{"1.0.0--", "1.0.0-0", 1},   // "-" is alphanumeric
		{"1.0.0-alpha", "0.9.9", 1}, // core dominates
		{"1.0.0-0", "1.0.0", -1},
	}
	for _, c := range cases {
		t.Run(c.a+"_vs_"+c.b, func(t *testing.T) { mustCompare(t, c.a, c.b, c.want) })
	}
}

func TestBuildMetadataIgnored(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"1.0.0+a", "1.0.0+b", 0},
		{"1.0.0+001", "1.0.0", 0},
		{"1.0.0-alpha+exp.sha.5114f85", "1.0.0-alpha", 0},
		{"1.0.0+build-1", "1.0.0", 0},
		{"1.0.0-rc.1+build.1", "1.0.0+build.0", -1},
		{"v2.0.0+x", "1.9.9+z", 1},
	}
	for _, c := range cases {
		t.Run(c.a+"_vs_"+c.b, func(t *testing.T) { mustCompare(t, c.a, c.b, c.want) })
	}
}

func TestInvalid(t *testing.T) {
	invalid := []string{
		"", "1", "1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.03", "1.2.3-01",
		"1.2.3-", "1.2.3+", "1.2.3-a..b", "1.2.3+a..b", "1.2.3-a.", "1.2.3+a+b",
		"V1.2.3", "vv1.2.3", " 1.2.3", "1.2.3 ", "1.2.3-a b", "1.2.3-α",
		"1.2.3+a_b", "a.b.c", "-1.2.3", "1.-2.3", "1..3", "1.2.3-+x", "x1.2.3",
	}
	for _, s := range invalid {
		t.Run(s, func(t *testing.T) {
			if _, err := Compare(s, "1.0.0"); err == nil {
				t.Errorf("Compare(%q, \"1.0.0\") returned nil error", s)
			}
		})
	}
}

func TestInvalidEitherSide(t *testing.T) {
	cases := []struct{ a, b string }{
		{"1.0.0", "1.0"},
		{"1.0.0", "1.0.0-00"},
		{"1.0", "1.0"},
		{"1.0.0+ok", "1.0.0+"},
	}
	for _, c := range cases {
		t.Run(c.a+"_vs_"+c.b, func(t *testing.T) {
			if _, err := Compare(c.a, c.b); err == nil {
				t.Errorf("Compare(%q, %q) returned nil error", c.a, c.b)
			}
		})
	}
}

func TestValidEdgeForms(t *testing.T) {
	valid := []string{
		"0.0.0", "1.2.3-0", "1.2.3-0a", "1.2.3-x-y-z.--", "1.2.3+0001",
		"1.2.3-alpha+001", "1.2.3+a-b.c", "v0.0.0-0+0",
	}
	for _, s := range valid {
		t.Run(s, func(t *testing.T) {
			if _, err := Compare(s, s); err != nil {
				t.Errorf("Compare(%q, %q) error: %v", s, s, err)
			}
		})
	}
}
