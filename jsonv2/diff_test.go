//go:build goexperiment.jsonv2 && go1.27

package jsonv2

import (
	jsonv1 "encoding/json"
	"encoding/json/jsontext"
	jsonv2 "encoding/json/v2"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"
)

type User struct {
	UserName string `json:"user_name"`
	Age      int    `json:"age"`
}

func marshalBoth(t *testing.T, v any) (string, string) {
	t.Helper()
	b1, err := jsonv1.Marshal(v)
	if err != nil {
		t.Fatalf("v1: %v", err)
	}
	b2, err := jsonv2.Marshal(v)
	if err != nil {
		t.Fatalf("v2: %v", err)
	}
	return string(b1), string(b2)
}

func expect(t *testing.T, name, got, want string) {
	t.Helper()
	if got != want {
		t.Errorf("%s = %s, want %s", name, got, want)
	}
}

func expectErr(t *testing.T, err error, substr string) {
	t.Helper()
	if err == nil || !strings.Contains(err.Error(), substr) {
		t.Errorf("err = %v, want containing %q", err, substr)
	}
}

func TestNilSliceAndMap(t *testing.T) {
	type Nil struct {
		Tags  []string
		Attrs map[string]int
	}
	v1, v2 := marshalBoth(t, Nil{})
	expect(t, "v1", v1, `{"Tags":null,"Attrs":null}`)
	expect(t, "v2", v2, `{"Tags":[],"Attrs":{}}`)

	b, _ := jsonv2.Marshal(Nil{}, jsonv2.FormatNilSliceAsNull(true), jsonv2.FormatNilMapAsNull(true))
	expect(t, "v2+FormatNil*AsNull", string(b), `{"Tags":null,"Attrs":null}`)
}

func TestCaseSensitiveNames(t *testing.T) {
	in := []byte(`{"USER_NAME":"alice","Age":30}`)
	var u1, u2, u3 User
	if err := jsonv1.Unmarshal(in, &u1); err != nil {
		t.Fatal(err)
	}
	if err := jsonv2.Unmarshal(in, &u2); err != nil {
		t.Fatal(err)
	}
	if u1 != (User{"alice", 30}) || u2 != (User{}) {
		t.Errorf("v1=%+v v2=%+v", u1, u2)
	}
	if err := jsonv2.Unmarshal(in, &u3, jsonv2.MatchCaseInsensitiveNames(true)); err != nil || u3 != (User{"alice", 30}) {
		t.Errorf("MatchCaseInsensitiveNames: %+v %v", u3, err)
	}

	// v2 的不敏感匹配还忽略 - 和 _
	var u4 User
	jsonv2.Unmarshal([]byte(`{"userName":"bob"}`), &u4, jsonv2.MatchCaseInsensitiveNames(true))
	expect(t, "camelCase", u4.UserName, "bob")

	var l struct {
		UserName string `json:"user_name,case:ignore"`
	}
	jsonv2.Unmarshal([]byte(`{"UserName":"carol"}`), &l)
	expect(t, "case:ignore", l.UserName, "carol")
}

func TestDuplicateNames(t *testing.T) {
	in := []byte(`{"user_name":"a","user_name":"b"}`)
	var u1, u2, u3 User
	if err := jsonv1.Unmarshal(in, &u1); err != nil || u1.UserName != "b" {
		t.Errorf("v1: %+v %v", u1, err)
	}
	expectErr(t, jsonv2.Unmarshal(in, &u2), `duplicate object member name "user_name"`)
	if err := jsonv2.Unmarshal(in, &u3, jsontext.AllowDuplicateNames(true)); err != nil {
		t.Errorf("AllowDuplicateNames: %v", err)
	}
}

func TestInvalidUTF8(t *testing.T) {
	in := []byte("{\"user_name\":\"a\xffb\"}")
	var u1, u2 User
	if err := jsonv1.Unmarshal(in, &u1); err != nil || u1.UserName != "a\ufffdb" {
		t.Errorf("v1: %q %v", u1.UserName, err)
	}
	expectErr(t, jsonv2.Unmarshal(in, &u2), `invalid UTF-8 within "/user_name"`)
}

func TestEscapeHTML(t *testing.T) {
	v := map[string]string{"html": `<a href="x">&</a>`}
	v1, v2 := marshalBoth(t, v)
	expect(t, "v1", v1, `{"html":"\u003ca href=\"x\"\u003e\u0026\u003c/a\u003e"}`)
	expect(t, "v2", v2, `{"html":"<a href=\"x\">&</a>"}`)

	b, _ := jsonv2.Marshal(v, jsontext.EscapeForHTML(true))
	expect(t, "v2+EscapeForHTML", string(b), v1)
}

func TestOmitEmptyAndOmitZero(t *testing.T) {
	type Omit struct {
		Name  string    `json:"name,omitempty"`
		Count int       `json:"count,omitempty"`
		Ptr   *string   `json:"ptr,omitempty"`
		When  time.Time `json:"when,omitempty"`
		Zero  time.Time `json:"zero,omitzero"`
		Obj   struct{}  `json:"obj,omitempty"`
	}
	v1, v2 := marshalBoth(t, Omit{})
	expect(t, "v1", v1, `{"when":"0001-01-01T00:00:00Z","obj":{}}`)
	expect(t, "v2", v2, `{"count":0,"when":"0001-01-01T00:00:00Z"}`)
}

func TestDuration(t *testing.T) {
	type Job struct {
		Timeout time.Duration `json:"timeout"`
	}
	j := Job{Timeout: 1500 * time.Millisecond}

	b, _ := jsonv1.Marshal(j)
	expect(t, "v1", string(b), `{"timeout":1500000000}`)

	_, err := jsonv2.Marshal(j)
	expectErr(t, err, "no default representation")

	b, _ = jsonv2.Marshal(j, jsonv1.FormatDurationAsNano(true))
	expect(t, "FormatDurationAsNano", string(b), `{"timeout":1500000000}`)

	durStr := jsonv2.MarshalToFunc(func(enc *jsontext.Encoder, d time.Duration) error {
		return enc.WriteToken(jsontext.String(d.String()))
	})
	b, _ = jsonv2.Marshal(j, jsonv2.WithMarshalers(durStr))
	expect(t, "MarshalToFunc", string(b), `{"timeout":"1.5s"}`)

	// Go 1.25/1.26 的 format tag 在 1.27 已移除
	type Old struct {
		D time.Duration `json:"d,format:units"`
	}
	_, err = jsonv2.Marshal(Old{})
	expectErr(t, err, "unsupported `format` tag option")
}

func TestByteArrayAndArrayLength(t *testing.T) {
	type Hash struct {
		Sum [4]byte `json:"sum"`
	}
	v1, v2 := marshalBoth(t, Hash{[4]byte{1, 2, 3, 4}})
	expect(t, "v1", v1, `{"sum":[1,2,3,4]}`)
	expect(t, "v2", v2, `{"sum":"AQIDBA=="}`)

	type Arr struct {
		A [2]int `json:"a"`
	}
	in := []byte(`{"a":[1,2,3]}`)
	var a1, a2 Arr
	if err := jsonv1.Unmarshal(in, &a1); err != nil {
		t.Errorf("v1: %v", err)
	}
	expectErr(t, jsonv2.Unmarshal(in, &a2), "too many array elements")
}

func TestMapOrder(t *testing.T) {
	m := map[string]int{"b": 2, "a": 1, "c": 3, "d": 4, "e": 5}
	b1, _ := jsonv1.Marshal(m)
	expect(t, "v1", string(b1), `{"a":1,"b":2,"c":3,"d":4,"e":5}`)
	b2, _ := jsonv2.Marshal(m, jsonv2.Deterministic(true))
	expect(t, "v2+Deterministic", string(b2), string(b1))
	// v2 默认不保证顺序，因此这里不断言默认输出。
}

type ID struct{ v int64 }

func (i *ID) MarshalJSON() ([]byte, error) { return []byte(fmt.Sprintf(`"id-%d"`, i.v)), nil }

func TestPointerReceiverMethod(t *testing.T) {
	type Wrap struct{ I ID }
	v1, v2 := marshalBoth(t, Wrap{I: ID{42}})
	expect(t, "v1", v1, `{"I":{}}`)
	expect(t, "v2", v2, `{"I":"id-42"}`)
}

func TestSemanticError(t *testing.T) {
	var v struct {
		Items []struct {
			Price int `json:"price"`
		} `json:"items"`
	}
	in := []byte(`{"items":[{"price":1},{"price":"9"}]}`)
	expectErr(t, jsonv1.Unmarshal(in, &v), "Go struct field .items.1.price of type int")

	err := jsonv2.Unmarshal(in, &v)
	var se *jsonv2.SemanticError
	if !errors.As(err, &se) {
		t.Fatalf("want *SemanticError, got %T", err)
	}
	expect(t, "JSONPointer", string(se.JSONPointer), "/items/1/price")
	if se.ByteOffset != 31 {
		t.Errorf("ByteOffset = %d", se.ByteOffset)
	}
}

func TestEmbed(t *testing.T) {
	type Meta struct {
		Env string `json:"env"`
	}
	type Svc struct {
		ID   int  `json:"id"`
		Meta Meta `json:",embed"`
	}
	b, _ := jsonv2.Marshal(Svc{ID: 1, Meta: Meta{Env: "prod"}})
	expect(t, "embed struct", string(b), `{"id":1,"env":"prod"}`)

	type Cfg struct {
		Name  string         `json:"name"`
		Extra jsontext.Value `json:",embed"`
	}
	in := `{"name":"svc","timeout":30,"debug":true}`
	var c Cfg
	if err := jsonv2.Unmarshal([]byte(in), &c); err != nil {
		t.Fatal(err)
	}
	expect(t, "fallback", string(c.Extra), `{"timeout":30,"debug":true}`)
	b, _ = jsonv2.Marshal(c)
	expect(t, "roundtrip", string(b), in)

	var u User
	expectErr(t, jsonv2.Unmarshal([]byte(`{"user_name":"a","nick":"x"}`), &u, jsonv2.RejectUnknownMembers(true)),
		`unknown object member name "nick"`)
}

type Celsius float64

func (c Celsius) MarshalJSONTo(enc *jsontext.Encoder) error {
	return enc.WriteToken(jsontext.String(fmt.Sprintf("%.1f°C", float64(c))))
}

func TestMarshalJSONTo(t *testing.T) {
	b, _ := jsonv2.Marshal(map[string]Celsius{"bj": 21.5})
	expect(t, "MarshalJSONTo", string(b), `{"bj":"21.5°C"}`)
}

func TestJSONTextStream(t *testing.T) {
	dec := jsontext.NewDecoder(strings.NewReader(
		`{"logs":[{"lvl":"info"},{"lvl":"error"},{"lvl":"error"}]}`))
	n := 0
	for {
		tok, err := dec.ReadToken()
		if err != nil {
			break
		}
		if tok.Kind() == '"' && tok.String() == "lvl" {
			val, _ := dec.ReadToken()
			if val.String() == "error" {
				n++
			}
		}
	}
	if n != 2 {
		t.Errorf("errors = %d, want 2", n)
	}

	raw := jsontext.Value(`{"b":1,"a":[1, 2 ]}`)
	if err := raw.Canonicalize(); err != nil {
		t.Fatal(err)
	}
	expect(t, "Canonicalize", string(raw), `{"a":[1,2],"b":1}`)
}

func TestDefaultOptionsV1(t *testing.T) {
	type U struct {
		UserName string   `json:"user_name"`
		Tags     []string `json:"tags"`
	}
	var u U
	jsonv2.Unmarshal([]byte(`{"USER_NAME":"alice"}`), &u, jsonv1.DefaultOptionsV1())
	expect(t, "unmarshal", u.UserName, "alice")

	b, _ := jsonv2.Marshal(U{}, jsonv1.DefaultOptionsV1())
	expect(t, "v1 opts", string(b), `{"user_name":"","tags":null}`)
	b, _ = jsonv2.Marshal(U{}, jsonv1.DefaultOptionsV1(), jsonv2.FormatNilSliceAsNull(false))
	expect(t, "override", string(b), `{"user_name":"","tags":[]}`)
}
