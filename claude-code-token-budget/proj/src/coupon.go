package coupon

import (
	"context"
	"errors"
	"time"
)

var ErrNotFound = errors.New("coupon: not found")

type Coupon struct {
	ID        int64
	TenantID  int64
	Status    string
	AmountFen int64
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Repo interface {
	Get(ctx context.Context, tenantID, id int64) (*Coupon, error)
	Save(ctx context.Context, v *Coupon) error
}

// CreateCoupon creates a coupon after validating input.
func CreateCoupon(ctx context.Context, r Repo, tenantID, id int64) (*Coupon, error) {
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

// GetCoupon gets a coupon after validating input.
func GetCoupon(ctx context.Context, r Repo, tenantID, id int64) (*Coupon, error) {
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

// CancelCoupon cancels a coupon after validating input.
func CancelCoupon(ctx context.Context, r Repo, tenantID, id int64) (*Coupon, error) {
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

// ListCoupon lists a coupon after validating input.
func ListCoupon(ctx context.Context, r Repo, tenantID, id int64) (*Coupon, error) {
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

func validateCoupon(v *Coupon) error {
	if v.AmountFen < 0 {
		return errors.New("negative amount")
	}
	return nil
}
