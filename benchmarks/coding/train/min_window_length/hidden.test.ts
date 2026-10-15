import test from 'node:test';
import assert from 'node:assert/strict';
import { minWindowLength } from './solution.ts';
test('case 0', () => assert.deepEqual(minWindowLength(...[[2, 3, 1, 2, 4, 3], 7] as any), 2));
test('case 1', () => assert.deepEqual(minWindowLength(...[[1, 4, 4], 4] as any), 1));
test('case 2', () => assert.deepEqual(minWindowLength(...[[1, 1], 5] as any), 0));
test('case 3', () => assert.deepEqual(minWindowLength(...[[], 2] as any), 0));
test('case 4', () => assert.deepEqual(minWindowLength(...[[2, 2, 2], 6] as any), 3));
test('case 5', () => assert.deepEqual(minWindowLength(...[[8], 8] as any), 1));
