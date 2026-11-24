// Package config holds gw runtime settings.
package config

// Config is the gw runtime configuration.
type Config struct {
	ListenAddr string `json:"listen_addr"`
	DataDir    string `json:"data_dir"`
	MaxKeys    int    `json:"max_keys"`
}

// Default returns the built-in configuration.
func Default() Config {
	return Config{ListenAddr: ":8080", DataDir: "./data", MaxKeys: 10000}
}
