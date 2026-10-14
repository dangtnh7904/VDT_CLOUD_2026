import test from 'node:test';
import assert from 'node:assert/strict';
import { CommandAdmission } from './command-admission.js';

test('shared admission preserves FIFO without exceeding active bound', async () => {
  const queue = new CommandAdmission(1, 4);
  const first = await queue.acquire(1000);
  const order = [];
  const second = queue.acquire(1000).then(release => { order.push(2); return release; });
  const third = queue.acquire(1000).then(release => { order.push(3); return release; });
  assert.equal(queue.active, 1); assert.equal(queue.waiting.length, 2);
  first(); const releaseSecond = await second;
  assert.deepEqual(order, [2]); assert.equal(queue.active, 1);
  releaseSecond(); const releaseThird = await third;
  assert.deepEqual(order, [2, 3]); releaseThird(); assert.equal(queue.active, 0);
});

test('full queue fails explicitly without creating another timer or slot', async () => {
  const queue = new CommandAdmission(1, 0);
  const release = await queue.acquire(1000);
  await assert.rejects(queue.acquire(1000), error => error.code === 'SSH_COMMAND_QUEUE_FULL');
  assert.equal(queue.active, 1); assert.equal(queue.waiting.length, 0); release();
});

test('expired queued command is removed and never admitted later', async () => {
  const queue = new CommandAdmission(1, 2);
  const release = await queue.acquire(1000);
  await assert.rejects(queue.acquire(10), error => error.code === 'EXECUTOR_TIMEOUT');
  assert.equal(queue.waiting.length, 0); release(); assert.equal(queue.active, 0);
});

test('duplicate release cannot free another command reservation', async () => {
  const queue = new CommandAdmission(1, 1);
  const release = await queue.acquire(1000);
  const pending = queue.acquire(1000); release(); release();
  const nextRelease = await pending; assert.equal(queue.active, 1);
  nextRelease(); nextRelease(); assert.equal(queue.active, 0);
});

test('invalid bounds and deadlines fail closed', async () => {
  for (const limit of [0, 9, NaN, 1.5]) assert.throws(() => new CommandAdmission(limit));
  const queue = new CommandAdmission();
  await assert.rejects(queue.acquire(0), error => error.code === 'EXECUTOR_NOT_CONFIGURED');
});
