package solution

import (
	"container/list"
	"time"
)

type entry struct {
	key    string
	val    string
	expiry time.Time
}

type Cache struct {
	capacity int
	ttl      time.Duration
	now      func() time.Time
	ll       *list.List // front = MRU
	items    map[string]*list.Element
}

func New(capacity int, ttl time.Duration, now func() time.Time) *Cache {
	return &Cache{capacity: capacity, ttl: ttl, now: now, ll: list.New(), items: map[string]*list.Element{}}
}

func (c *Cache) expired(e *list.Element, t time.Time) bool {
	return !t.Before(e.Value.(*entry).expiry)
}

func (c *Cache) remove(e *list.Element) {
	c.ll.Remove(e)
	delete(c.items, e.Value.(*entry).key)
}

func (c *Cache) Get(k string) (string, bool) {
	e, ok := c.items[k]
	if !ok {
		return "", false
	}
	if c.expired(e, c.now()) {
		c.remove(e)
		return "", false
	}
	c.ll.MoveToFront(e)
	return e.Value.(*entry).val, true
}

func (c *Cache) Put(k, v string) {
	t := c.now()
	if e, ok := c.items[k]; ok {
		if !c.expired(e, t) {
			en := e.Value.(*entry)
			en.val, en.expiry = v, t.Add(c.ttl)
			c.ll.MoveToFront(e)
			return
		}
		c.remove(e)
	}
	if c.ll.Len() == c.capacity {
		for e := c.ll.Front(); e != nil; {
			next := e.Next()
			if c.expired(e, t) {
				c.remove(e)
			}
			e = next
		}
		if c.ll.Len() == c.capacity {
			c.remove(c.ll.Back())
		}
	}
	c.items[k] = c.ll.PushFront(&entry{key: k, val: v, expiry: t.Add(c.ttl)})
}

func (c *Cache) Len() int {
	t := c.now()
	n := 0
	for e := c.ll.Front(); e != nil; e = e.Next() {
		if !c.expired(e, t) {
			n++
		}
	}
	return n
}
