package main

import (
	"crypto/ecdsa"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"time"

	"github.com/costa92/blog-go-example/execution-line-control-plane/approvals"
	"github.com/costa92/blog-go-example/execution-line-control-plane/poppy"
)

func main() {
	fmt.Println("=== 1. Poppy 1.0 Control Plane Demo (Offline In-Process) ===")
	runPoppyDemo()

	fmt.Println("\n=== 2. Claude Ship Approvals Policy Demo (Offline In-Process) ===")
	runApprovalsDemo()
}

func runPoppyDemo() {
	key, err := poppy.GenerateDelegatedKey()
	if err != nil {
		panic(err)
	}
	now := time.Now().UTC()
	clientID := "https://muse.example.net/cimd.json"
	resourceURL := "https://mcp.shop.example.com/v1"

	srv := &poppy.Server{
		Domain:      "shop.example.com",
		ResourceURL: resourceURL,
		AgentKeys:   map[string]*ecdsa.PublicKey{clientID: &key.PublicKey},
		Tokens: map[string]poppy.AccessToken{
			"tok-read": {
				Subject:  "user-42",
				Resource: resourceURL,
				Scopes:   []string{"orders:read"},
				Expires:  now.Add(15 * time.Minute),
			},
			"tok-write": {
				Subject:  "user-42",
				Resource: resourceURL,
				Scopes:   []string{"orders:read", "orders:write"},
				Expires:  now.Add(15 * time.Minute),
			},
		},
		Now: func() time.Time { return now },
	}

	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	jwt, err := poppy.SignSessionJWT(key, "poppy_dlg_demo", poppy.SessionClaims{
		ClientID: clientID,
		Sub:      "pairwise-shop-9f8e7d",
		Sid:      "sess-demo-01",
		Aud:      "shop.example.com",
		Iat:      now.Unix(),
		Exp:      now.Add(5 * time.Minute).Unix(),
	})
	if err != nil {
		panic(err)
	}

	doReq := func(label, method, path, sessionJWT, bearer string) {
		req, _ := http.NewRequest(method, ts.URL+path, nil)
		if sessionJWT != "" {
			req.Header.Set(poppy.SessionHeader, sessionJWT)
		}
		if bearer != "" {
			req.Header.Set("Authorization", "Bearer "+bearer)
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			panic(err)
		}
		defer resp.Body.Close()
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("[%d] %s -> %s", resp.StatusCode, label, string(body))
	}

	doReq("Guest read return policy (no OAuth)", http.MethodGet, "/v1/policies/returns", jwt, "")
	doReq("Cancel order with orders:read only", http.MethodPost, "/v1/orders/ORD-1001/cancel", jwt, "tok-read")
	doReq("Cancel order with orders:write + Poppy-Session", http.MethodPost, "/v1/orders/ORD-1001/cancel", jwt, "tok-write")
}

func runApprovalsDemo() {
	const policyYAML = `
mode: enforce
rules:
  - name: Routine Code
    paths: ["src/**", "docs/**"]
    if: ["claude/code_review"]
    allow_claude_approval: true
  - name: Sensitive Billing
    paths: ["billing/**"]
    seats:
      - count: 1
        from: [humans, "!pr/author"]
`
	pol, err := approvals.ParsePolicy([]byte(policyYAML))
	if err != nil {
		panic(err)
	}

	cases := []approvals.PullRequest{
		{
			Number:           201,
			Author:           "alice",
			ChangedFiles:     []string{"docs/api.md"},
			ClaudeCodeReview: true,
			RequiredCIPassed: true,
		},
		{
			Number:           202,
			Author:           "alice",
			ChangedFiles:     []string{"billing/charge.go"},
			ClaudeCodeReview: true,
			HumanApprovers:   []string{"alice"},
			RequiredCIPassed: true,
		},
		{
			Number:           203,
			Author:           "alice",
			ChangedFiles:     []string{"billing/charge.go"},
			ClaudeCodeReview: true,
			HumanApprovers:   []string{"bob"},
			RequiredCIPassed: true,
		},
	}

	for _, pr := range cases {
		dec := pol.Evaluate(pr)
		fmt.Printf("PR #%d (%v): check=%s would_approve=%v merge_allowed=%v (%s)\n",
			pr.Number, pr.ChangedFiles, dec.CheckStatus, dec.WouldApprove, dec.BranchMergeAllowed, dec.Reason)
	}
	fmt.Printf("PR Steward attempting approve_pr: %v\n", approvals.ValidateStewardAction(approvals.ActionApprovePR, false))
}
