package approvals

import (
	"fmt"
	"path"
	"strings"

	"gopkg.in/yaml.v3"
)

const (
	ModeObserve = "observe"
	ModeEnforce = "enforce"
)

// Policy models a minimal subset of .claude/approvals.yml.
type Policy struct {
	Mode  string `yaml:"mode"`
	Rules []Rule `yaml:"rules"`
}

type Rule struct {
	Name                string            `yaml:"name"`
	Paths               []string          `yaml:"paths"`
	If                  []string          `yaml:"if"`
	Seats               []SeatRequirement `yaml:"seats"`
	AllowClaudeApproval bool              `yaml:"allow_claude_approval"`
}

type SeatRequirement struct {
	Count int      `yaml:"count"`
	From  []string `yaml:"from"`
}

// PullRequest captures the inputs evaluated by Claude Approvals.
// Note: CI test status is intentionally separate and enforced by GitHub branch protection.
type PullRequest struct {
	Number            int
	Author            string
	ChangedFiles      []string
	ClaudeCodeReview  bool // claude/code_review signal passed cleanly
	HumanApprovers    []string
	RequiredCIPassed  bool // enforced by GitHub Branch Protection, not approvals.yml
}

type Decision struct {
	Mode               string
	MatchedRules       []string
	WouldApprove       bool
	CheckStatus        string // "pass", "block", "observe_pass", "observe_would_block"
	Reason             string
	BranchMergeAllowed bool
}

func ParsePolicy(data []byte) (Policy, error) {
	var p Policy
	if err := yaml.Unmarshal(data, &p); err != nil {
		return Policy{}, err
	}
	if p.Mode == "" {
		p.Mode = ModeEnforce
	}
	if p.Mode != ModeObserve && p.Mode != ModeEnforce {
		return Policy{}, fmt.Errorf("unsupported mode %q", p.Mode)
	}
	return p, nil
}

// Evaluate checks all matching rules (strictest requirement wins) and combines with branch protection.
func (p Policy) Evaluate(pr PullRequest) Decision {
	var matched []Rule
	for _, r := range p.Rules {
		if matchesAnyPath(pr.ChangedFiles, r.Paths) {
			matched = append(matched, r)
		}
	}

	if len(matched) == 0 {
		return Decision{
			Mode:               p.Mode,
			WouldApprove:       false,
			CheckStatus:        statusForMode(p.Mode, false),
			Reason:             "no matching approval rule; defaulting to human review",
			BranchMergeAllowed: false,
		}
	}

	matchedNames := make([]string, 0, len(matched))
	var failures []string

	for _, r := range matched {
		matchedNames = append(matchedNames, r.Name)

		// Check required signals (e.g. claude/code_review).
		signalsOK := true
		for _, cond := range r.If {
			if cond == "claude/code_review" && !pr.ClaudeCodeReview {
				signalsOK = false
				failures = append(failures, fmt.Sprintf("rule %q requires clean claude/code_review", r.Name))
			}
		}

		// Check human seat requirements.
		if len(r.Seats) > 0 {
			for _, seat := range r.Seats {
				eligible := countEligibleHumans(pr.Author, pr.HumanApprovers, seat.From)
				if eligible < seat.Count {
					failures = append(failures, fmt.Sprintf("rule %q needs %d human approval(s), got %d", r.Name, seat.Count, eligible))
				}
			}
		} else if !r.AllowClaudeApproval || !signalsOK {
			failures = append(failures, fmt.Sprintf("rule %q does not allow automatic Claude approval", r.Name))
		}
	}

	wouldApprove := len(failures) == 0
	reason := "all matched policy rules satisfied"
	if !wouldApprove {
		reason = strings.Join(failures, "; ")
	}

	checkStatus := statusForMode(p.Mode, wouldApprove)
	// Even if Claude Approvals passes (or is in observe mode), GitHub branch protection still gates CI.
	policyGatePassed := p.Mode == ModeObserve || wouldApprove
	branchMergeAllowed := policyGatePassed && pr.RequiredCIPassed

	return Decision{
		Mode:               p.Mode,
		MatchedRules:       matchedNames,
		WouldApprove:       wouldApprove,
		CheckStatus:        checkStatus,
		Reason:             reason,
		BranchMergeAllowed: branchMergeAllowed,
	}
}

func statusForMode(mode string, wouldApprove bool) string {
	if mode == ModeObserve {
		if wouldApprove {
			return "observe_pass"
		}
		return "observe_would_block"
	}
	if wouldApprove {
		return "pass"
	}
	return "block"
}

func countEligibleHumans(author string, approvers []string, from []string) int {
	excludeAuthor := false
	for _, f := range from {
		if f == "!pr/author" {
			excludeAuthor = true
		}
	}
	seen := make(map[string]struct{})
	for _, a := range approvers {
		if excludeAuthor && a == author {
			continue
		}
		seen[a] = struct{}{}
	}
	return len(seen)
}

func matchesAnyPath(files []string, patterns []string) bool {
	for _, f := range files {
		for _, pat := range patterns {
			if matchGlob(pat, f) {
				return true
			}
		}
	}
	return false
}

// matchGlob supports "**" prefix/directory globs (e.g. "billing/**", "src/**", "**").
func matchGlob(pattern, file string) bool {
	if pattern == "**" {
		return true
	}
	if strings.HasSuffix(pattern, "/**") {
		prefix := strings.TrimSuffix(pattern, "/**")
		return file == prefix || strings.HasPrefix(file, prefix+"/")
	}
	ok, _ := path.Match(pattern, file)
	return ok
}

// StewardAction models PR Steward's strict capability boundary.
type StewardAction string

const (
	ActionFixCI        StewardAction = "fix_ci"
	ActionFixConflict  StewardAction = "fix_conflict"
	ActionAddressNotes StewardAction = "address_review"
	ActionApprovePR    StewardAction = "approve_pr"
	ActionMergePR      StewardAction = "merge_pr"
)

// ValidateStewardAction enforces PR Steward guardrails:
// 1. Stops immediately when @claude stop is present.
// 2. Hard-blocks approve and merge actions.
func ValidateStewardAction(action StewardAction, stoppedByUser bool) error {
	if stoppedByUser {
		return fmt.Errorf("steward halted by @claude stop; refusing action %q", action)
	}
	switch action {
	case ActionFixCI, ActionFixConflict, ActionAddressNotes:
		return nil
	case ActionApprovePR, ActionMergePR:
		return fmt.Errorf("steward is forbidden from executing %q", action)
	default:
		return fmt.Errorf("unknown steward action %q", action)
	}
}
