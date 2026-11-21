package shipping

import (
	"context"
	"errors"
	"time"
)

var ErrNotFound = errors.New("shipping: not found")

type Shipping struct {
	ID        int64
	TenantID  int64
	Status    string
	AmountFen int64
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Repo interface {
	Get(ctx context.Context, tenantID, id int64) (*Shipping, error)
	Save(ctx context.Context, v *Shipping) error
}

// CreateShipping creates a shipping after validating input.
func CreateShipping(ctx context.Context, r Repo, tenantID, id int64) (*Shipping, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	v, err := r.Get(ctx, tenantID, id)
	if err != nil {
		return nil, err
	}
	if v == nil {
		return nil, ErrNotFound
	}
	v.UpdatedAt = time.Now().UTC()
	return v, r.Save(ctx, v)
}

// GetShipping gets a shipping after validating input.
func GetShipping(ctx context.Context, r Repo, tenantID, id int64) (*Shipping, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	v, err := r.Get(ctx, tenantID, id)
	if err != nil {
		return nil, err
	}
	if v == nil {
		return nil, ErrNotFound
	}
	v.UpdatedAt = time.Now().UTC()
	return v, r.Save(ctx, v)
}

// CancelShipping cancels a shipping after validating input.
func CancelShipping(ctx context.Context, r Repo, tenantID, id int64) (*Shipping, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	v, err := r.Get(ctx, tenantID, id)
	if err != nil {
		return nil, err
	}
	if v == nil {
		return nil, ErrNotFound
	}
	v.UpdatedAt = time.Now().UTC()
	return v, r.Save(ctx, v)
}

// ListShipping lists a shipping after validating input.
func ListShipping(ctx context.Context, r Repo, tenantID, id int64) (*Shipping, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	v, err := r.Get(ctx, tenantID, id)
	if err != nil {
		return nil, err
	}
	if v == nil {
		return nil, ErrNotFound
	}
	v.UpdatedAt = time.Now().UTC()
	return v, r.Save(ctx, v)
}

func validateShipping(v *Shipping) error {
	if v.AmountFen < 0 {
		return errors.New("negative amount")
	}
	return nil
}
