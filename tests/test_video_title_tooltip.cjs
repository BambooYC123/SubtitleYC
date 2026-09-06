const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const events = {};
const title = { textContent: 'A long video title.mp4 | 1920x1080', addEventListener: (name, fn) => events[name] = fn };
const tooltip = { hidden: true };
let changed;
vm.runInNewContext(fs.readFileSync('static/video-title-tooltip.js', 'utf8'), {
 document: { querySelector: s => s === '#videoMeta' ? title : tooltip }, window: {},
 MutationObserver: class { constructor(fn) { changed = fn; } observe() {} }
});
events.pointerenter();
assert.equal(tooltip.textContent, title.textContent);
assert.equal(tooltip.hidden, false);
title.textContent = 'Another video'; changed();
assert.equal(tooltip.textContent, 'Another video');
events.pointerleave(); assert.equal(tooltip.hidden, true);
events.focus(); assert.equal(tooltip.hidden, false);
events.keydown({ key: 'Escape' }); assert.equal(tooltip.hidden, true);
console.log('Video title tooltip hover, focus, updates and dismissal passed.');
