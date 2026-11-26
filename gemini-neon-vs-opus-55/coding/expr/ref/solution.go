package solution

import (
	"errors"
	"math"
	"strconv"
)

var (
	errSyntax  = errors.New("syntax error")
	errDivZero = errors.New("division by zero")
)

type token struct {
	op  byte // 0 for number
	num float64
}

func isDigit(c byte) bool { return c >= '0' && c <= '9' }

func lex(s string) ([]token, error) {
	var toks []token
	for i := 0; i < len(s); {
		c := s[i]
		switch {
		case c == ' ' || c == '\t' || c == '\n' || c == '\r':
			i++
		case c == '+' || c == '-' || c == '*' || c == '/' || c == '^' || c == '(' || c == ')':
			toks = append(toks, token{op: c})
			i++
		case isDigit(c) || c == '.':
			j := i
			for j < len(s) && isDigit(s[j]) {
				j++
			}
			intDigits := j - i
			fracDigits := 0
			if j < len(s) && s[j] == '.' {
				j++
				k := j
				for j < len(s) && isDigit(s[j]) {
					j++
				}
				fracDigits = j - k
			}
			if intDigits == 0 && fracDigits == 0 {
				return nil, errSyntax
			}
			v, err := strconv.ParseFloat(s[i:j], 64)
			if err != nil {
				return nil, errSyntax
			}
			toks = append(toks, token{num: v})
			i = j
		default:
			return nil, errSyntax
		}
	}
	return toks, nil
}

type parser struct {
	toks []token
	pos  int
}

func (p *parser) peek() byte {
	if p.pos < len(p.toks) {
		if p.toks[p.pos].op == 0 {
			return 'n'
		}
		return p.toks[p.pos].op
	}
	return 0
}

func (p *parser) expr() (float64, error) {
	v, err := p.term()
	if err != nil {
		return 0, err
	}
	for op := p.peek(); op == '+' || op == '-'; op = p.peek() {
		p.pos++
		r, err := p.term()
		if err != nil {
			return 0, err
		}
		if op == '+' {
			v += r
		} else {
			v -= r
		}
	}
	return v, nil
}

func (p *parser) term() (float64, error) {
	v, err := p.unary()
	if err != nil {
		return 0, err
	}
	for op := p.peek(); op == '*' || op == '/'; op = p.peek() {
		p.pos++
		r, err := p.unary()
		if err != nil {
			return 0, err
		}
		if op == '*' {
			v *= r
		} else {
			if r == 0 {
				return 0, errDivZero
			}
			v /= r
		}
	}
	return v, nil
}

func (p *parser) unary() (float64, error) {
	switch p.peek() {
	case '+':
		p.pos++
		return p.unary()
	case '-':
		p.pos++
		v, err := p.unary()
		return -v, err
	}
	return p.power()
}

func (p *parser) power() (float64, error) {
	b, err := p.primary()
	if err != nil {
		return 0, err
	}
	if p.peek() == '^' {
		p.pos++
		e, err := p.unary()
		if err != nil {
			return 0, err
		}
		return math.Pow(b, e), nil
	}
	return b, nil
}

func (p *parser) primary() (float64, error) {
	switch p.peek() {
	case 'n':
		v := p.toks[p.pos].num
		p.pos++
		return v, nil
	case '(':
		p.pos++
		v, err := p.expr()
		if err != nil {
			return 0, err
		}
		if p.peek() != ')' {
			return 0, errSyntax
		}
		p.pos++
		return v, nil
	}
	return 0, errSyntax
}

func Eval(s string) (float64, error) {
	toks, err := lex(s)
	if err != nil {
		return 0, err
	}
	p := &parser{toks: toks}
	v, err := p.expr()
	if err != nil {
		return 0, err
	}
	if p.pos != len(toks) {
		return 0, errSyntax
	}
	return v, nil
}
