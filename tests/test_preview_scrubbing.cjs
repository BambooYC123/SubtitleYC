const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/app.js', 'utf8');
const names = ['cancelPreviewScrubUi', 'schedulePreviewScrubUi', 'seekTo', 'finishPreviewScrub'];
const functions = names.map(name => {
  const start = source.indexOf(`function ${name}(`);
  return source.slice(start, source.indexOf('\nfunction ', start + 1));
}).join('\n');
let frame = null;
const seeks = [];
const state = { session: {}, previewScrubbing: true, previewScrubUiFrame: null, previewTime: 0 };
const context = {
  state, elements: { seekSlider: { value: 'dragging' } },
  window: { requestAnimationFrame: fn => { frame = fn; return 1; }, cancelAnimationFrame: () => { frame = null; } },
  nativePreviewEnabled: () => true, sessionDuration: () => 100,
  updateTimeUI: () => {}, syncNativePreviewSurface: () => seeks.push(state.previewTime),
  requestPreviewFrame: time => seeks.push(time), cancelPreviewScrubSync: () => {},
};
vm.runInNewContext(functions, context);
for (let i = 1; i <= 50; i++) context.seekTo(i);
assert.equal(seeks.length, 0, 'Pointer events must not flood the native bridge');
frame();
assert.deepEqual(seeks, [50], 'One frame sends only the latest position');
assert.equal(context.elements.seekSlider.value, 'dragging', 'Do not fight the native slider during a drag');
context.seekTo(75);
context.finishPreviewScrub();
assert.equal(frame, null, 'Release cancels a queued animation frame');
assert.deepEqual(seeks, [50, 75], 'Release flushes the exact final position');
assert.equal(state.previewScrubbing, false);
console.log('Scrub batching and final-position checks passed.');
