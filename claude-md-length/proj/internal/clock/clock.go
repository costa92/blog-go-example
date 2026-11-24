// Package clock is the single source of wall-clock time for gw.
package clock

import "time"

// Now returns the current time. Tests replace it to control time.
var Now = time.Now
