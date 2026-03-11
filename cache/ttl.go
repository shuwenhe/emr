package cache

import (
	"sync"
	"time"
)

type item struct {
	value     any
	expiresAt time.Time
}

type TTLCache struct {
	ttl   time.Duration
	mu    sync.RWMutex
	store map[string]item
}

func NewTTLCache(ttl time.Duration) *TTLCache {
	return &TTLCache{
		ttl:   ttl,
		store: make(map[string]item),
	}
}

func (c *TTLCache) Get(key string) (any, bool) {
	c.mu.RLock()
	entry, ok := c.store[key]
	c.mu.RUnlock()
	if !ok {
		return nil, false
	}
	if time.Now().After(entry.expiresAt) {
		c.mu.Lock()
		delete(c.store, key)
		c.mu.Unlock()
		return nil, false
	}
	return entry.value, true
}

func (c *TTLCache) Set(key string, value any) {
	c.mu.Lock()
	c.store[key] = item{value: value, expiresAt: time.Now().Add(c.ttl)}
	c.mu.Unlock()
}

func (c *TTLCache) Delete(key string) {
	c.mu.Lock()
	delete(c.store, key)
	c.mu.Unlock()
}
