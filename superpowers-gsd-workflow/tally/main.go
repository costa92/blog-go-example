// tally counts lines and words read from stdin.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
)

type Counts struct {
	Lines int
	Words int
}

func Count(r io.Reader) (Counts, error) {
	var c Counts
	sc := bufio.NewScanner(r)
	for sc.Scan() {
		c.Lines++
		c.Words += len(strings.Fields(sc.Text()))
	}
	return c, sc.Err()
}

func main() {
	flag.Parse()
	c, err := Count(os.Stdin)
	if err != nil {
		fmt.Fprintln(os.Stderr, "tally:", err)
		os.Exit(1)
	}
	fmt.Printf("lines=%d words=%d\n", c.Lines, c.Words)
}
