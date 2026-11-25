package poppy

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"net/http"
	"strings"
	"time"
)

const (
	SessionHeader   = "Poppy-Session"
	SessionTokenTyp = "poppy-session+jwt"
	SessionTokenAlg = "ES256"
)

// DiscoveryDocument models /.well-known/poppy.json (Poppy 1.0 minimal subset).
type DiscoveryDocument struct {
	ProtocolVersion string       `json:"protocol_version"`
	Organization    Organization `json:"organization"`
	Auth            AuthConfig   `json:"auth"`
	APIs            []APIRoute   `json:"apis"`
}

type Organization struct {
	Name   string `json:"name"`
	Domain string `json:"domain"`
}

type AuthConfig struct {
	Issuer string            `json:"issuer"`
	Scopes map[string]string `json:"scopes"`
}

type APIRoute struct {
	Type        string `json:"type"`
	URL         string `json:"url"`
	Description string `json:"description"`
}

// SessionHeaderJSON is the JOSE header for Poppy-Session JWTs.
type SessionHeaderJSON struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
	Kid string `json:"kid,omitempty"`
}

// SessionClaims captures core Poppy-Session JWT claims.
// Sub is a pairwise opaque user ID scoped to a single company (aud).
type SessionClaims struct {
	ClientID string `json:"client_id"` // HTTPS CIMD URL
	Sub      string `json:"sub"`       // Pairwise user ID
	Sid      string `json:"sid"`       // Ephemeral task session ID
	Aud      string `json:"aud"`       // Target company domain
	Iat      int64  `json:"iat"`
	Exp      int64  `json:"exp"`
}

// AccessToken models a resource-bound OAuth 2.1 Bearer token.
type AccessToken struct {
	Subject  string
	Resource string
	Scopes   []string
	Expires  time.Time
}

func (t AccessToken) HasScope(want string) bool {
	for _, s := range t.Scopes {
		if s == want {
			return true
		}
	}
	return false
}

// GenerateDelegatedKey creates an ES256 keypair simulating poppy_dlg.
func GenerateDelegatedKey() (*ecdsa.PrivateKey, error) {
	return ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
}

// SignSessionJWT signs a Poppy-Session JWT with ES256 (RFC 7515 raw R||S signature).
func SignSessionJWT(key *ecdsa.PrivateKey, kid string, claims SessionClaims) (string, error) {
	headerBytes, err := json.Marshal(SessionHeaderJSON{
		Alg: SessionTokenAlg,
		Typ: SessionTokenTyp,
		Kid: kid,
	})
	if err != nil {
		return "", err
	}
	payloadBytes, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}

	enc := base64.RawURLEncoding
	signingInput := enc.EncodeToString(headerBytes) + "." + enc.EncodeToString(payloadBytes)
	digest := sha256.Sum256([]byte(signingInput))
	r, s, err := ecdsa.Sign(rand.Reader, key, digest[:])
	if err != nil {
		return "", err
	}

	sig := make([]byte, 64)
	r.FillBytes(sig[:32])
	s.FillBytes(sig[32:])
	return signingInput + "." + enc.EncodeToString(sig), nil
}

// VerifySessionJWT validates typ, alg, ES256 signature, expiry, and target audience.
func VerifySessionJWT(token string, pub *ecdsa.PublicKey, expectedAud string, now time.Time) (SessionClaims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return SessionClaims{}, errors.New("malformed jwt")
	}

	enc := base64.RawURLEncoding
	headerBytes, err := enc.DecodeString(parts[0])
	if err != nil {
		return SessionClaims{}, fmt.Errorf("decode header: %w", err)
	}
	var hdr SessionHeaderJSON
	if err := json.Unmarshal(headerBytes, &hdr); err != nil {
		return SessionClaims{}, fmt.Errorf("parse header: %w", err)
	}
	if hdr.Typ != SessionTokenTyp {
		return SessionClaims{}, fmt.Errorf("unexpected typ %q, want %q", hdr.Typ, SessionTokenTyp)
	}
	if hdr.Alg != SessionTokenAlg {
		return SessionClaims{}, fmt.Errorf("unexpected alg %q, want %q", hdr.Alg, SessionTokenAlg)
	}

	sigBytes, err := enc.DecodeString(parts[2])
	if err != nil || len(sigBytes) != 64 {
		return SessionClaims{}, errors.New("invalid signature encoding")
	}
	digest := sha256.Sum256([]byte(parts[0] + "." + parts[1]))
	r := new(big.Int).SetBytes(sigBytes[:32])
	s := new(big.Int).SetBytes(sigBytes[32:])
	if !ecdsa.Verify(pub, digest[:], r, s) {
		return SessionClaims{}, errors.New("invalid es256 signature")
	}

	payloadBytes, err := enc.DecodeString(parts[1])
	if err != nil {
		return SessionClaims{}, fmt.Errorf("decode payload: %w", err)
	}
	var claims SessionClaims
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return SessionClaims{}, fmt.Errorf("parse claims: %w", err)
	}
	if claims.Aud != expectedAud {
		return SessionClaims{}, fmt.Errorf("audience mismatch: got %q, want %q", claims.Aud, expectedAud)
	}
	if now.Unix() >= claims.Exp {
		return SessionClaims{}, errors.New("session jwt expired")
	}
	if claims.ClientID == "" || claims.Sub == "" || claims.Sid == "" {
		return SessionClaims{}, errors.New("missing required session claims")
	}
	return claims, nil
}

// Server simulates a Poppy-enabled merchant endpoint enforcing dual-layer auth.
type Server struct {
	Domain      string
	ResourceURL string
	AgentKeys   map[string]*ecdsa.PublicKey // client_id (CIMD URL) -> public key
	Tokens      map[string]AccessToken      // bearer token -> scoped token metadata
	Now         func() time.Time
}

func (s *Server) now() time.Time {
	if s.Now != nil {
		return s.Now()
	}
	return time.Now()
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /.well-known/poppy.json", s.handleDiscovery)
	mux.HandleFunc("GET /v1/policies/returns", s.handlePublicPolicy)
	mux.HandleFunc("POST /v1/orders/{id}/cancel", s.handleCancelOrder)
	return mux
}

func (s *Server) handleDiscovery(w http.ResponseWriter, _ *http.Request) {
	doc := DiscoveryDocument{
		ProtocolVersion: "1.0",
		Organization: Organization{
			Name:   "Example Commerce",
			Domain: s.Domain,
		},
		Auth: AuthConfig{
			Issuer: "https://auth." + s.Domain,
			Scopes: map[string]string{
				"orders:read":  "View order history and shipment status",
				"orders:write": "Cancel pending orders with explicit user consent",
			},
		},
		APIs: []APIRoute{
			{
				Type:        "mcp",
				URL:         s.ResourceURL,
				Description: "Order query and cancellation remote MCP endpoint",
			},
		},
	}
	writeJSON(w, http.StatusOK, doc)
}

func (s *Server) verifySessionFromRequest(r *http.Request) (SessionClaims, error) {
	raw := r.Header.Get(SessionHeader)
	if raw == "" {
		return SessionClaims{}, errors.New("missing Poppy-Session header")
	}
	// Peek client_id to select the corresponding public key (simulating CIMD JWKS lookup).
	parts := strings.Split(raw, ".")
	if len(parts) != 3 {
		return SessionClaims{}, errors.New("malformed Poppy-Session header")
	}
	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return SessionClaims{}, errors.New("invalid Poppy-Session payload")
	}
	var peek struct {
		ClientID string `json:"client_id"`
	}
	if err := json.Unmarshal(payloadBytes, &peek); err != nil || peek.ClientID == "" {
		return SessionClaims{}, errors.New("missing client_id in Poppy-Session")
	}
	pub, ok := s.AgentKeys[peek.ClientID]
	if !ok {
		return SessionClaims{}, fmt.Errorf("unknown agent client_id %q", peek.ClientID)
	}
	return VerifySessionJWT(raw, pub, s.Domain, s.now())
}

// handlePublicPolicy allows guest (signed-out) reads as long as agent identity is verified.
func (s *Server) handlePublicPolicy(w http.ResponseWriter, r *http.Request) {
	claims, err := s.verifySessionFromRequest(r)
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"mode":            "guest_signed_out",
		"agent_client_id": claims.ClientID,
		"pairwise_sub":    claims.Sub,
		"return_window":   "7 days unopened",
	})
}

// handleCancelOrder enforces dual-layer auth: verified Poppy-Session + resource-bound OAuth orders:write.
func (s *Server) handleCancelOrder(w http.ResponseWriter, r *http.Request) {
	claims, err := s.verifySessionFromRequest(r)
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": err.Error()})
		return
	}

	authz := r.Header.Get("Authorization")
	if !strings.HasPrefix(authz, "Bearer ") {
		writeJSON(w, http.StatusUnauthorized, map[string]string{
			"error": "oauth bearer token required to cross execution line",
		})
		return
	}
	rawToken := strings.TrimPrefix(authz, "Bearer ")
	tok, ok := s.Tokens[rawToken]
	if !ok || s.now().After(tok.Expires) {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid or expired bearer token"})
		return
	}
	if tok.Resource != s.ResourceURL {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "token resource mismatch (confused deputy blocked)"})
		return
	}
	if !tok.HasScope("orders:write") {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "insufficient scope: orders:write required"})
		return
	}

	orderID := r.PathValue("id")
	writeJSON(w, http.StatusOK, map[string]any{
		"status":          "cancelled",
		"order_id":        orderID,
		"agent_client_id": claims.ClientID,
		"session_id":      claims.Sid,
		"user_subject":    tok.Subject,
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
