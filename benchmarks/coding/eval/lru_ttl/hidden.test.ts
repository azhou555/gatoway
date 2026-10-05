import test from 'node:test';
import assert from 'node:assert/strict';
import { LRUCache } from './solution.ts';
test('trace 0', () => {
  const obj = new LRUCache(...[2] as any);
  assert.deepEqual(obj.put(...["a", 1, 10, 0] as any), undefined);
  assert.deepEqual(obj.put(...["b", 2, 10, 0] as any), undefined);
  assert.deepEqual(obj.get(...["a", 1] as any), 1);
  assert.deepEqual(obj.put(...["c", 3, 10, 1] as any), undefined);
  assert.deepEqual(obj.get(...["b", 1] as any), undefined);
  assert.deepEqual(obj.get(...["c", 1] as any), 3);
});
test('trace 1', () => {
  const obj = new LRUCache(...[1] as any);
  assert.deepEqual(obj.put(...["a", 1, 5, 0] as any), undefined);
  assert.deepEqual(obj.get(...["a", 4] as any), 1);
  assert.deepEqual(obj.get(...["a", 5] as any), undefined);
});
test('trace 2', () => {
  const obj = new LRUCache(...[2] as any);
  assert.deepEqual(obj.put(...["a", 1, 100, 0] as any), undefined);
  assert.deepEqual(obj.put(...["b", 2, 1, 0] as any), undefined);
  assert.deepEqual(obj.put(...["c", 3, 10, 2] as any), undefined);
  assert.deepEqual(obj.get(...["a", 2] as any), 1);
});
test('trace 3', () => {
  const obj = new LRUCache(...[0] as any);
  assert.deepEqual(obj.put(...["a", 1, 10, 0] as any), undefined);
  assert.deepEqual(obj.get(...["a", 0] as any), undefined);
});
test('trace 4', () => {
  const obj = new LRUCache(...[1] as any);
  assert.deepEqual(obj.put(...["a", 1, 1, 0] as any), undefined);
  assert.deepEqual(obj.put(...["a", 2, 10, 1] as any), undefined);
  assert.deepEqual(obj.get(...["a", 2] as any), 2);
});
test('trace 5', () => {
  const obj = new LRUCache(...[1] as any);
  assert.deepEqual(obj.put(...["a", 1, 5, 0] as any), undefined);
  assert.deepEqual(obj.put(...["a", 2, 0, 1] as any), undefined);
  assert.deepEqual(obj.get(...["a", 1] as any), undefined);
});
