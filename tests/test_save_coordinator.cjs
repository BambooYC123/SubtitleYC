const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
vm.runInThisContext(fs.readFileSync('static/save-coordinator.js', 'utf8'));

(async () => {
  let value = 'first';
  const requests = [];
  const applied = [];
  let changed = 0;
  const saver = createSubtitleSaveCoordinator({
    snapshot: () => ({ value }),
    write: (data) => new Promise((resolve, reject) => requests.push({ data, resolve, reject })),
    apply: (data) => applied.push(data),
    changed: () => changed++,
  });
  const tick = () => new Promise(resolve => setImmediate(resolve));
  const first = saver.save();
  await tick();
  value = 'second';
  const second = saver.save();
  await tick();
  assert.equal(requests.length, 1, 'only one request in flight');
  requests[0].resolve('old response');
  await first;
  await tick();
  assert.equal(changed, 1);
  assert.deepEqual(applied, []);
  assert.equal(requests[1].data.value, 'second');
  requests[1].resolve('new response');
  await second;
  assert.deepEqual(applied, ['new response']);
  assert.equal(saver.busy, false);

  const failure = saver.save();
  await tick();
  requests[2].reject(new Error('disk full'));
  await assert.rejects(failure, /disk full/);
  const retry = saver.save();
  await tick();
  requests[3].resolve('retry');
  await retry;
  assert.equal(saver.busy, false);

  global.window = {};
  let dirty = true;
  installSubtitleCloseGuard({ dirty: () => dirty, busy: () => false, save: async () => { dirty = false; } });
  window.subtitleycSaveForClose();
  await tick();
  assert.equal(window.subtitleycCloseSaveResult, 'saved');
  installSubtitleCloseGuard({ dirty: () => true, busy: () => false, save: async () => { throw Error('failed'); } });
  window.subtitleycSaveForClose();
  await tick();
  assert.equal(window.subtitleycCloseSaveResult, 'failed');
  console.log('Save queue, edit preservation, failure recovery, and close-save checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
