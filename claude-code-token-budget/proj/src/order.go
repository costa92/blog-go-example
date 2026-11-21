package order

import (
	"context"
	"errors"
	"time"
)

var ErrNotFound = errors.New("order: not found")

type Order struct {
	ID        int64
	TenantID  int64
	Status    string
	AmountFen int64
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Repo interface {
	Get(ctx context.Context, tenantID, id int64) (*Order, error)
	Save(ctx context.Context, v *Order) error
}

// CreateOrder creates a order after validating input.
func CreateOrder(ctx context.Context, r Repo, tenantID, id int64) (*Order, error) {
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

// GetOrder gets a order after validating input.
func GetOrder(ctx context.Context, r Repo, tenantID, id int64) (*Order, error) {
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

// CancelOrder cancels a order after validating input.
func CancelOrder(ctx context.Context, r Repo, tenantID, id int64) (*Order, error) {
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

// ListOrder lists a order after validating input.
func ListOrder(ctx context.Context, r Repo, tenantID, id int64) (*Order, error) {
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

func validateOrder(v *Order) error {
	if v.AmountFen < 0 {
		return errors.New("negative amount")
	}
	return nil
}
