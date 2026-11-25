package approvals

import "testing"

const samplePolicyYAML = `
mode: enforce
rules:
  - name: Routine Code
    paths:
      - "src/**"
      - "docs/**"
    if:
      - "claude/code_review"
    allow_claude_approval: true

  - name: Sensitive Billing
    paths:
      - "billing/**"
    seats:
      - count: 1
        from: [humans, "!pr/author"]
`

func TestApprovalsPolicyEvaluation(t *testing.T) {
	pol, err := ParsePolicy([]byte(samplePolicyYAML))
	if err != nil {
		t.Fatalf("parse policy: %v", err)
	}

	tests := []struct {
		name               string
		modeOverride       string
		pr                 PullRequest
		wantWouldApprove   bool
		wantCheckStatus    string
		wantMergeAllowed   bool
	}{
		{
			name: "routine src change with clean code review and passing CI",
			pr: PullRequest{
				Number:           101,
				Author:           "alice",
				ChangedFiles:     []string{"src/util/format.go"},
				ClaudeCodeReview: true,
				RequiredCIPassed: true,
			},
			wantWouldApprove: true,
			wantCheckStatus:  "pass",
			wantMergeAllowed: true,
		},
		{
			name: "routine src change passes approvals but CI failed (branch protection blocks)",
			pr: PullRequest{
				Number:           102,
				Author:           "alice",
				ChangedFiles:     []string{"src/util/format.go"},
				ClaudeCodeReview: true,
				RequiredCIPassed: false,
			},
			wantWouldApprove: true,
			wantCheckStatus:  "pass",
			wantMergeAllowed: false,
		},
		{
			name: "billing change with only author self-approval is blocked",
			pr: PullRequest{
				Number:           103,
				Author:           "alice",
				ChangedFiles:     []string{"billing/invoice.go"},
				ClaudeCodeReview: true,
				HumanApprovers:   []string{"alice"},
				RequiredCIPassed: true,
			},
			wantWouldApprove: false,
			wantCheckStatus:  "block",
			wantMergeAllowed: false,
		},
		{
			name: "mixed PR touching src and billing requires human reviewer",
			pr: PullRequest{
				Number:           104,
				Author:           "alice",
				ChangedFiles:     []string{"src/util/format.go", "billing/invoice.go"},
				ClaudeCodeReview: true,
				HumanApprovers:   []string{"bob"},
				RequiredCIPassed: true,
			},
			wantWouldApprove: true,
			wantCheckStatus:  "pass",
			wantMergeAllowed: true,
		},
		{
			name:         "observe mode audits billing gap without blocking check",
			modeOverride: ModeObserve,
			pr: PullRequest{
				Number:           105,
				Author:           "alice",
				ChangedFiles:     []string{"billing/invoice.go"},
				ClaudeCodeReview: true,
				HumanApprovers:   nil,
				RequiredCIPassed: true,
			},
			wantWouldApprove: false,
			wantCheckStatus:  "observe_would_block",
			wantMergeAllowed: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			p := pol
			if tc.modeOverride != "" {
				p.Mode = tc.modeOverride
			}
			got := p.Evaluate(tc.pr)
			if got.WouldApprove != tc.wantWouldApprove {
				t.Errorf("WouldApprove = %v, want %v (reason: %s)", got.WouldApprove, tc.wantWouldApprove, got.Reason)
			}
			if got.CheckStatus != tc.wantCheckStatus {
				t.Errorf("CheckStatus = %q, want %q", got.CheckStatus, tc.wantCheckStatus)
			}
			if got.BranchMergeAllowed != tc.wantMergeAllowed {
				t.Errorf("BranchMergeAllowed = %v, want %v", got.BranchMergeAllowed, tc.wantMergeAllowed)
			}
		})
	}
}

func TestPRStewardGuardrails(t *testing.T) {
	if err := ValidateStewardAction(ActionFixCI, false); err != nil {
		t.Fatalf("fix_ci should be allowed: %v", err)
	}
	if err := ValidateStewardAction(ActionApprovePR, false); err == nil {
		t.Fatal("approve_pr must be forbidden for PR Steward")
	}
	if err := ValidateStewardAction(ActionMergePR, false); err == nil {
		t.Fatal("merge_pr must be forbidden for PR Steward")
	}
	if err := ValidateStewardAction(ActionFixConflict, true); err == nil {
		t.Fatal("stopped steward must refuse all actions")
	}
}
