package csvbug

import (
	"bytes"
	"encoding/csv"
)

func Export(rows [][]string) (string, error) {
	var buf bytes.Buffer
	writer := csv.NewWriter(&buf)
	for _, row := range rows {
		if err := writer.Write(row); err != nil {
			return "", err
		}
	}
	return buf.String(), writer.Error()
}
