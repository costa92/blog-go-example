package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestV2ReferenceAndBuggyGates(t *testing.T) {
	counts := map[string]int{"bytesize": 58, "retry-delay": 40, "csv-record": 26}
	for _, task := range taskIDs {
		t.Run(task, func(t *testing.T) {
			good := gradeSourceV2(context.Background(), task, asset(task, "reference.go.txt"))
			if !good.Passed || !good.Scorable || good.Expected != counts[task] || good.PassedCases != counts[task] || good.NotRun != 0 {
				t.Fatalf("reference rejected: %+v\n%s", good, good.Log)
			}
			bad := gradeSourceV2(context.Background(), task, asset(task, "solution.go.txt"))
			if bad.Passed || !bad.Scorable || bad.PassedCases+bad.FailedCases+bad.NotRun != bad.Expected {
				t.Fatalf("invalid buggy grade: %+v\n%s", bad, bad.Log)
			}
		})
	}
}

func TestV2RejectsPositiveOverflowMissedByV1(t *testing.T) {
	source := []byte(`package exercise
import "time"
func Delay(attempt int,base,limit time.Duration)time.Duration{
 if attempt<=0||base<=0||limit<=0{return 0};if base>=limit{return limit}
 shift:=uint(attempt-1);if shift>62{return limit}
 d:=base<<shift;if d<=0||d>limit{return limit};return d
}`)
	if v1 := gradeSource(context.Background(), "retry-delay", source); !v1.Passed {
		t.Fatal("regression fixture should pass historical V1")
	}
	v2 := gradeSourceV2(context.Background(), "retry-delay", source)
	if v2.Passed || !v2.Scorable {
		t.Fatalf("missed positive overflow: %+v", v2)
	}
	found := false
	for _, c := range v2.Cases {
		if c.Name == "positive_wrap_4" && c.Status == "failed" {
			found = true
		}
	}
	if !found {
		t.Fatal("positive wrap case did not reject fixture")
	}
}

func TestV2AccountingKeepsUnexecutedCases(t *testing.T) {
	names := []string{"a", "b", "c"}
	events := `{"Action":"run","Test":"TestAcceptanceV2/a"}
{"Action":"pass","Test":"TestAcceptanceV2/a"}
{"Action":"run","Test":"TestAcceptanceV2/b"}
{"Action":"fail","Test":"TestAcceptanceV2/b"}
{"Action":"fail","Test":"TestAcceptanceV2"}
{"Action":"fail"}`
	g, complete, build, err := parseV2Events([]byte(events), names)
	if err != nil || complete || build || g.PassedCases != 1 || g.FailedCases != 1 || g.NotRun != 1 || g.Expected != 3 {
		t.Fatalf("wrong accounting: %+v %v", g, err)
	}
	g, _, build, err = parseV2Events([]byte(`{"Action":"build-fail"}`), names)
	if err != nil || !build || g.PassedCases != 0 || g.FailedCases != 0 || g.NotRun != 3 {
		t.Fatalf("build failure hid denominator: %+v", g)
	}
	for _, bad := range []string{`not JSON`, `{"Action":"run","Test":"TestAcceptanceV2/unknown"}`, `{"Action":"pass","Test":"TestAcceptanceV2/a"}`} {
		if _, _, _, err := parseV2Events([]byte(bad), names); err == nil {
			t.Fatalf("accepted invalid event stream: %s", bad)
		}
	}
}

func TestV2BuildFailureIsNotExecutedCaseFailure(t *testing.T) {
	g := gradeSourceV2(context.Background(), "bytesize", []byte("package exercise\nfunc broken(\n"))
	if !g.Scorable || g.Status != "build_failed" || g.PassedCases != 0 || g.FailedCases != 0 || g.NotRun != 58 {
		t.Fatalf("bad build failure accounting: %+v\n%s", g, g.Log)
	}
}

func TestV2DoesNotTrustProcessExit(t *testing.T) {
	source := []byte("package exercise\nimport \"os\"\nfunc init(){os.Exit(0)}\nfunc ParseBytes(string)(uint64,error){return 0,nil}\n")
	g := gradeSourceV2(context.Background(), "bytesize", source)
	if g.Passed || g.PassedCases != 0 {
		t.Fatalf("exit without cases passed: %+v", g)
	}
}

func TestRegradeInputHashAndIdentityValidation(t *testing.T) {
	root := t.TempDir()
	var saved []savedTrial
	for _, condition := range []string{"base", "adapter"} {
		source := asset("bytesize", "reference.go.txt")
		tr := Trial{Task: "bytesize", Condition: condition, Repetition: 1, Model: condition, Status: "completed", Scorable: true, Passed: true, FinalSourceHash: digest(source)}
		dir := filepath.Join(root, "01-bytesize-"+condition)
		if err := os.Mkdir(dir, 0700); err != nil {
			t.Fatal(err)
		}
		if err := writeJSON(filepath.Join(dir, "result.json"), tr); err != nil {
			t.Fatal(err)
		}
		for name, data := range map[string][]byte{"solution.go.txt": source, "events.jsonl": []byte("saved events\n"), "grade.jsonl": []byte("saved grade\n")} {
			if err := writeFile(filepath.Join(dir, name), data); err != nil {
				t.Fatal(err)
			}
		}
		hashes := map[string]string{}
		for _, name := range []string{"result.json", "solution.go.txt", "events.jsonl", "grade.jsonl"} {
			b, err := os.ReadFile(filepath.Join(dir, name))
			if err != nil {
				t.Fatal(err)
			}
			hashes[name] = digest(b)
		}
		saved = append(saved, savedTrial{Trial: tr, Artifacts: hashes})
	}
	evidence := filepath.Join(root, "evidence.json")
	if err := writeJSON(evidence, map[string]any{"trials": saved}); err != nil {
		t.Fatal(err)
	}
	answers, hash, err := loadRegradeAnswers(evidence, []string{root})
	if err != nil || len(answers) != 2 || hash == "" {
		t.Fatalf("valid input rejected: %v", err)
	}
	if _, _, err := loadRegradeAnswers(evidence, []string{root, root}); err == nil {
		t.Fatal("ambiguous saved snapshots accepted")
	}
	duplicate := append(append([]savedTrial{}, saved...), saved[0])
	if err := writeJSON(evidence, map[string]any{"trials": duplicate}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := loadRegradeAnswers(evidence, []string{root}); err == nil {
		t.Fatal("duplicate trial identity accepted")
	}
	if err := writeJSON(evidence, map[string]any{"trials": saved}); err != nil {
		t.Fatal(err)
	}
	if err := writeFile(filepath.Join(root, "01-bytesize-base/solution.go.txt"), []byte("changed")); err != nil {
		t.Fatal(err)
	}
	if _, _, err := loadRegradeAnswers(evidence, []string{root}); err == nil || !strings.Contains(err.Error(), "hash mismatch") {
		t.Fatalf("changed original accepted: %v", err)
	}
}

func TestRegradeSummaryUsesV2SuccessPairs(t *testing.T) {
	trials := []RegradedTrial{
		{Original: Trial{Task: "x", Repetition: 1, Condition: "base", Status: "completed", Scorable: true, Passed: true}, V2: DetailedGrade{Scorable: true, Expected: 2, PassedCases: 1, FailedCases: 1}},
		{Original: Trial{Task: "x", Repetition: 1, Condition: "adapter", Status: "completed", Scorable: true, Passed: true}, V2: DetailedGrade{Scorable: true, Passed: true, Expected: 2, PassedCases: 2}},
	}
	s := regradeSummary(trials)
	if s.Conditions["base"].OriginalPassed != 1 || s.Conditions["base"].Passed != 0 || s.V2Efficiency.CompletePairs != 0 || s.Tasks["x"]["adapter"].PassedCases != 2 {
		b, _ := json.Marshal(s)
		t.Fatalf("wrong V2 summary: %s", b)
	}
}
