import test from 'node:test';
import assert from 'node:assert/strict';
import { maxWindowSum } from './solution.ts';
test('case 0', () => assert.deepEqual(maxWindowSum(...[[1, 2, 3, 4], 2] as any), 7));
test('case 1', () => assert.deepEqual(maxWindowSum(...[[-5, -2, -8], 2] as any), -7));
test('case 2', () => assert.deepEqual(maxWindowSum(...[[], 1] as any), null));
test('case 3', () => assert.deepEqual(maxWindowSum(...[[1], 0] as any), null));
test('case 4', () => assert.deepEqual(maxWindowSum(...[[1], 2] as any), null));
test('case 5', () => assert.deepEqual(maxWindowSum(...[[3, 1], 2] as any), 4));
