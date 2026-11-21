package payment

import (
	"context"
	"errors"
	"time"
)

var ErrNotFound = errors.New("payment: not found")

type Payment struct {
	ID        int64
	TenantID  int64
	Status    string
	AmountFen int64
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Repo interface {
	Get(ctx context.Context, tenantID, id int64) (*Payment, error)
	Save(ctx context.Context, v *Payment) error
}

// CreatePayment creates a payment after validating input.
func CreatePayment(ctx context.Context, r Repo, tenantID, id int64) (*Payment, error) {
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

// GetPayment gets a payment after validating input.
func GetPayment(ctx context.Context, r Repo, tenantID, id int64) (*Payment, error) {
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

// CancelPayment cancels a payment after validating input.
func CancelPayment(ctx context.Context, r Repo, tenantID, id int64) (*Payment, error) {
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

// ListPayment lists a payment after validating input.
func ListPayment(ctx context.Context, r Repo, tenantID, id int64) (*Payment, error) {
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

func validatePayment(v *Payment) error {
	if v.AmountFen < 0 {
		return errors.New("negative amount")
	}
	return nil
}
