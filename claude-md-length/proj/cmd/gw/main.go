package main

import (
	"net/http"
	"os"

	"example.com/gw/internal/config"
	"example.com/gw/internal/store"
)

func main() {
	cfg := config.Default()
	s := store.New()
	_ = s
	if err := http.ListenAndServe(cfg.ListenAddr, http.NotFoundHandler()); err != nil {
		os.Exit(1)
	}
}
