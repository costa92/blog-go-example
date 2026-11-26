package solution

import (
	"context"
	"errors"
	"sync"
)

var ErrBadLimit = errors.New("parmap: limit must be positive")

func Map[T, R any](ctx context.Context, in []T, limit int, f func(context.Context, T) (R, error)) ([]R, error) {
	if limit <= 0 {
		return nil, ErrBadLimit
	}
	if len(in) == 0 {
		return []R{}, nil
	}
	wctx, cancel := context.WithCancel(ctx)
	defer cancel()

	out := make([]R, len(in))
	sem := make(chan struct{}, limit)
	var (
		mu       sync.Mutex
		firstErr error
		wg       sync.WaitGroup
	)
	started := 0
	for i := range in {
		sem <- struct{}{}
		// The failing call records firstErr before releasing its slot, so this check
		// sees it whenever the slot we just got came from that call.
		mu.Lock()
		stop := firstErr != nil || ctx.Err() != nil
		mu.Unlock()
		if stop {
			break
		}
		started++
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			r, err := f(wctx, in[i])
			mu.Lock()
			out[i] = r
			if err != nil && firstErr == nil {
				firstErr = err
				cancel()
			}
			mu.Unlock()
			<-sem
		}(i)
	}
	wg.Wait()
	switch {
	case firstErr != nil:
		return nil, firstErr
	case started < len(in):
		return nil, ctx.Err()
	}
	return out, nil
}
