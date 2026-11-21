package inventory

import (
	"context"
	"errors"
	"time"
)

var ErrNotFound = errors.New("inventory: not found")

type Inventory struct {
	ID        int64
	TenantID  int64
	Status    string
	AmountFen int64
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Repo interface {
	Get(ctx context.Context, tenantID, id int64) (*Inventory, error)
	Save(ctx context.Context, v *Inventory) error
}

// CreateInventory creates a inventory after validating input.
func CreateInventory(ctx context.Context, r Repo, tenantID, id int64) (*Inventory, error) {
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

// GetInventory gets a inventory after validating input.
func GetInventory(ctx context.Context, r Repo, tenantID, id int64) (*Inventory, error) {
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

// CancelInventory cancels a inventory after validating input.
func CancelInventory(ctx context.Context, r Repo, tenantID, id int64) (*Inventory, error) {
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

// ListInventory lists a inventory after validating input.
func ListInventory(ctx context.Context, r Repo, tenantID, id int64) (*Inventory, error) {
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

func validateInventory(v *Inventory) error {
	if v.AmountFen < 0 {
		return errors.New("negative amount")
	}
	return nil
}
