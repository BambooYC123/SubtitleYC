const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let callback, frame, syncs = 0;
class Element {
  constructor() { this.hidden = false; }
  getBoundingClientRect() { return { width: 600, height: this.hidden ? 0 : 400 }; }
  matches() { return true; }
}
const dialog = new Element();
let matches = [];
const context = {
  Element,
  window: { subtitleycSyncNativePreview: () => syncs++ },
  document: { body: {}, querySelectorAll: () => matches, addEventListener: () => {} },
  MutationObserver: class { constructor(fn) { callback = fn; } observe() {} },
  requestAnimationFrame: fn => { frame = fn; return 1; },
};
vm.runInNewContext(fs.readFileSync('static/preview-overlays.js', 'utf8'), context);
assert.equal(context.window.subtitleycModalOpen(), false);
matches = [dialog];
callback([{ target: dialog }]);
callback([{ target: dialog }]);
frame();
assert.equal(syncs, 1);
assert.equal(context.window.subtitleycModalOpen(), true);
dialog.hidden = true;
callback([{ target: dialog }]);
frame();
assert.equal(context.window.subtitleycModalOpen(), false);
assert.equal(syncs, 2, 'Closing a modal must restore preview visibility');
console.log('Native modal visibility and restoration checks passed.');
