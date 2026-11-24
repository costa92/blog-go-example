// Package store is an in-memory key/value store.
package store

import (
	"errors"
	"sync"
)

// ErrNotFound is returned when a key does not exist.
var ErrNotFound = errors.New("not found")

// Store holds string values by key. It is safe for concurrent use.
type Store struct {
	mu   sync.RWMutex
	data map[string]string
}

// New returns an empty Store.
func New() *Store {
	return &Store{data: make(map[string]string)}
}

// Get returns the value for key or ErrNotFound.
func (s *Store) Get(key string) (string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	v, ok := s.data[key]
	if !ok {
		return "", ErrNotFound
	}
	return v, nil
}

// Set stores value under key.
func (s *Store) Set(key, value string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data[key] = value
}
