package poppy

import (
	"crypto/ecdsa"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPoppyExecutionLine(t *testing.T) {
	key, err := GenerateDelegatedKey()
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}

	now := time.Date(2026, 11, 25, 12, 0, 0, 0, time.UTC)
	clientID := "https://muse.example.net/cimd.json"
	resourceURL := "https://mcp.shop.example.com/v1"

	srv := &Server{
		Domain:      "shop.example.com",
		ResourceURL: resourceURL,
		AgentKeys: map[string]*ecdsa.PublicKey{
			clientID: &key.PublicKey,
		},
		Tokens: map[string]AccessToken{
			"tok-read-only": {
				Subject:  "user-42",
				Resource: resourceURL,
				Scopes:   []string{"orders:read"},
				Expires:  now.Add(10 * time.Minute),
			},
			"tok-wrong-resource": {
				Subject:  "user-42",
				Resource: "https://mcp.other.example.com/v1",
				Scopes:   []string{"orders:write"},
				Expires:  now.Add(10 * time.Minute),
			},
			"tok-write-ok": {
				Subject:  "user-42",
				Resource: resourceURL,
				Scopes:   []string{"orders:read", "orders:write"},
				Expires:  now.Add(10 * time.Minute),
			},
		},
		Now: func() time.Time { return now },
	}

	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	// 1. Discovery (/.well-known/poppy.json)
	resp, err := http.Get(ts.URL + "/.well-known/poppy.json")
	if err != nil {
		t.Fatalf("get discovery: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("discovery status = %d, want 200", resp.StatusCode)
	}
	var doc DiscoveryDocument
	if err := json.NewDecoder(resp.Body).Decode(&doc); err != nil {
		t.Fatalf("decode discovery: %v", err)
	}
	if doc.ProtocolVersion != "1.0" || len(doc.APIs) != 1 || doc.APIs[0].Type != "mcp" {
		t.Fatalf("unexpected discovery doc: %+v", doc)
	}

	validJWT, err := SignSessionJWT(key, "poppy_dlg_20261125", SessionClaims{
		ClientID: clientID,
		Sub:      "pairwise-shop-9f8e7d",
		Sid:      "sess-001",
		Aud:      "shop.example.com",
		Iat:      now.Unix(),
		Exp:      now.Add(5 * time.Minute).Unix(),
	})
	if err != nil {
		t.Fatalf("sign session jwt: %v", err)
	}

	// 2. Guest (signed-out) read succeeds with valid Poppy-Session JWT and no Bearer token.
	req, _ := http.NewRequest(http.MethodGet, ts.URL+"/v1/policies/returns", nil)
	req.Header.Set(SessionHeader, validJWT)
	resp2, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("guest read: %v", err)
	}
	resp2.Body.Close()
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("guest read status = %d, want 200", resp2.StatusCode)
	}

	// 3. Guarded write (cancel order) table-driven checks.
	tests := []struct {
		name       string
		sessionJWT string
		bearer     string
		wantStatus int
	}{
		{
			name:       "missing Poppy-Session header",
			sessionJWT: "",
			bearer:     "tok-write-ok",
			wantStatus: http.StatusUnauthorized,
		},
		{
			name:       "signed-out guest cannot cancel order",
			sessionJWT: validJWT,
			bearer:     "",
			wantStatus: http.StatusUnauthorized,
		},
		{
			name:       "read-only scope rejected on destructive write",
			sessionJWT: validJWT,
			bearer:     "tok-read-only",
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "wrong resource token blocked (confused deputy)",
			sessionJWT: validJWT,
			bearer:     "tok-wrong-resource",
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "dual-layer auth with orders:write succeeds",
			sessionJWT: validJWT,
			bearer:     "tok-write-ok",
			wantStatus: http.StatusOK,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			r, _ := http.NewRequest(http.MethodPost, ts.URL+"/v1/orders/ORD-1001/cancel", nil)
			if tc.sessionJWT != "" {
				r.Header.Set(SessionHeader, tc.sessionJWT)
			}
			if tc.bearer != "" {
				r.Header.Set("Authorization", "Bearer "+tc.bearer)
			}
			res, err := http.DefaultClient.Do(r)
			if err != nil {
				t.Fatalf("do request: %v", err)
			}
			res.Body.Close()
			if res.StatusCode != tc.wantStatus {
				t.Fatalf("status = %d, want %d", res.StatusCode, tc.wantStatus)
			}
		})
	}
}
