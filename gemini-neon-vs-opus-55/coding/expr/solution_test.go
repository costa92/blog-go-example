package solution

import (
	"math"
	"testing"
)

type evalCase struct {
	in   string
	want float64
}

func runEval(t *testing.T, cases []evalCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.in, func(t *testing.T) {
			got, err := Eval(c.in)
			if err != nil {
				t.Fatalf("Eval(%q) error: %v", c.in, err)
			}
			if math.Abs(got-c.want) > 1e-9*math.Max(1, math.Abs(c.want)) {
				t.Fatalf("Eval(%q) = %v, want %v", c.in, got, c.want)
			}
		})
	}
}

func TestNumbers(t *testing.T) {
	runEval(t, []evalCase{
		{"3", 3}, {"2.5", 2.5}, {".5", 0.5}, {"5.", 5}, {"042", 42},
		{"0", 0}, {"123456.789", 123456.789}, {"  7  ", 7}, {"0.125", 0.125},
	})
}

func TestBasicArithmetic(t *testing.T) {
	runEval(t, []evalCase{
		{"1+2", 3}, {"1-2-3", -4}, {"8/4/2", 1}, {"2*3+4*5", 26}, {"2+3*4", 14},
		{"10-4/2", 8}, {"7/2", 3.5}, {"1.5*4", 6}, {".5+5.", 5.5}, {"6/4*2", 3},
	})
}

func TestPowerAssociativity(t *testing.T) {
	runEval(t, []evalCase{
		{"2^3^2", 512}, {"(2^3)^2", 64}, {"2^10", 1024}, {"4^0.5", 2},
		{"2^2^0", 2}, {"3*2^2", 12}, {"2^3*2", 16}, {"2^1^3^2", 2},
	})
}

func TestUnary(t *testing.T) {
	runEval(t, []evalCase{
		{"-2^2", -4}, {"2^-1", 0.5}, {"-3*-2", 6}, {"2*-3", -6}, {"2^-2^2", 0.0625},
		{"--2", 2}, {"-+-2", 2}, {"+5", 5}, {"-(2+3)", -5}, {"1--1", 2},
		{"-2^-2", -0.25}, {"(-2)^2", 4}, {"4/-2", -2}, {"1 - -2^2", 5},
	})
}

func TestParenthesesAndWhitespace(t *testing.T) {
	runEval(t, []evalCase{
		{"(1+2)*3", 9}, {"((((5))))", 5}, {"2*(3+(4-1))/3", 4},
		{" \t1 +\n2 *\r3 ", 7}, {"( 1 + 2 ) ^ 2", 9}, {"-(-(-1))", -1},
	})
}

func TestDivisionByZero(t *testing.T) {
	for _, in := range []string{"1/0", "0/0", "1/(1-1)", "5/-0", "1+2/(3*0)", "1/0.0"} {
		t.Run(in, func(t *testing.T) {
			if _, err := Eval(in); err == nil {
				t.Errorf("Eval(%q) returned nil error", in)
			}
		})
	}
}

func TestMalformed(t *testing.T) {
	for _, in := range []string{
		"", "   ", "1+", "(1", "1)", "1 2", "2^^3", "()", "1..2", "abc", ".",
		"*1", "1e3", "(1)(2)", "2(3)", "1 .5", "1+*2", "^2", "2^", "(", ")",
		"1,5", "3%2", "1.2.3", "((1)", "-", "2 ^ * 3",
	} {
		t.Run(in, func(t *testing.T) {
			if _, err := Eval(in); err == nil {
				t.Errorf("Eval(%q) returned nil error", in)
			}
		})
	}
}
