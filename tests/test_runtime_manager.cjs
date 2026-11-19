const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('static/index.html', 'utf8');
const panel = html.slice(html.indexOf('<dialog id="runtimeDialog"'));
assert.ok(panel.indexOf('runtimeIntro') < panel.indexOf('runtimePause'));
assert.ok(panel.indexOf('runtimePause') < panel.indexOf('runtimeEditions'));
assert.ok(panel.indexOf('runtimeEditions') < panel.indexOf('<details'));
assert.ok(panel.includes('<details class="runtime-extra-details">'), 'Details start collapsed');
const catalogue = JSON.parse(fs.readFileSync('assets/runtime-catalog.json', 'utf8'));
for (const edition of Object.values(catalogue)) assert.ok(panel.includes(`href="${edition.url}"`));

class Element {
  constructor() { this.listeners = {}; this.children = []; this.open = false; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  setAttribute() {}
  append(...items) { this.children.push(...items); }
  replaceChildren() { this.children = []; }
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
  async click() { if (!this.disabled) await this.listeners.click?.(); }
}

(async () => {
  const elements = Object.fromEntries(['runtimeDialog', 'runtimeEditions', 'runtimeMessage', 'runtimeProgress', 'runtimePause', 'runtimeClose', 'runtimeTitle', 'runtimeIntro', 'runtimeSkip'].map(id => [id, new Element()]));
  const opener = new Element();
  const calls = [];
  let timer;
  let refreshes = 0;
  let fail = false;
  let response = { status: 'idle', active: false, editions: [
    { id: 'cpu', version: '1.5.1', size_bytes: 500e6, unpacked_bytes: 1e9, installed: false },
    { id: 'gpu-cuda-12.9', version: '1.5.1', size_bytes: 1500e6, unpacked_bytes: 4e9, installed: false, compatibility: { compatible: true } },
  ] };
  const context = {
    document: { querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => [opener], createElement: () => new Element() },
    window: {},
    fetchJson: async (url, options) => { calls.push([url, options?.method]); if (fail) throw new Error('Connection interrupted'); return response; },
    refreshSystemInfo: async () => { refreshes++; },
    setTimeout: fn => { timer = fn; return 1; }, clearTimeout: () => { timer = null; },
  };
  vm.runInNewContext(fs.readFileSync('static/runtime-manager.js', 'utf8'), context);
  await opener.click();
  await Promise.resolve();
  assert.equal(elements.runtimeDialog.open, true);
  assert.equal(elements.runtimeEditions.children.length, 2);
  assert.equal(elements.runtimePause.hidden, false);
  assert.equal(elements.runtimePause.disabled, true, 'Idle pause must be disabled');
  assert.equal(elements.runtimeEditions.children[0].children[0].textContent, 'CPU OCR');
  const sizeText = elements.runtimeEditions.children[1].children[2].textContent;
  assert.ok(!sizeText.includes('SubtitleYC 0.7.0'), 'Keep version metadata out of the main card');
  assert.ok(!sizeText.includes('VideOCR'), 'Engine version belongs in collapsed details');
  assert.ok(sizeText.includes('Download size:') && sizeText.includes('Space after installation:'));
  assert.ok(sizeText.includes('Free space needed to install now:'));
  assert.ok(sizeText.includes('GiB'), 'Binary sizes must use the correct unit');
  assert.deepEqual(calls, [['/api/runtimes', undefined]], 'Opening panel must not download anything');
  const cpuButton = () => elements.runtimeEditions.children[0].children[3];
  const gpuButton = () => elements.runtimeEditions.children[1].children[3];

  fail = true;
  await cpuButton().click();
  assert.equal(elements.runtimeMessage.textContent, 'Connection interrupted');
  assert.equal(cpuButton().disabled, false, 'Failure must allow retry');
  fail = false;
  response = { ...response, status: 'downloading', active: true, edition: 'cpu', bytes: 10, total: 100, speed: 5 };
  await cpuButton().click();
  assert.deepEqual(calls.at(-1), ['/api/runtimes/cpu/download', 'POST']);
  assert.equal(cpuButton().disabled, true);
  assert.equal(gpuButton().disabled, true, 'Only one download may run at a time');
  assert.equal(elements.runtimeProgress.value, 10);
  assert.equal(elements.runtimePause.disabled, false, 'Active download enables pause');
  response = { ...response, status: 'paused', active: false };
  await elements.runtimePause.click();
  assert.equal(elements.runtimePause.disabled, true, 'Paused download disables pause');
  assert.deepEqual(calls.at(-1), ['/api/runtimes/pause', 'POST']);
  await elements.runtimeClose.click();
  assert.equal(elements.runtimeDialog.open, false);
  assert.equal(typeof timer, 'function', 'Closing panel must keep monitoring the download');
  response = { ...response, status: 'ready', active: false, editions: response.editions.map(e => ({ ...e, installed: e.id === 'cpu' })) };
  await timer();
  assert.equal(elements.runtimeEditions.children[0].textContent, 'CPU OCR installed - ready to use');
  assert.equal(elements.runtimeEditions.children[0].children.length, 0, 'Installed CPU has no download card');
  assert.equal(gpuButton().disabled, false);
  assert.equal(refreshes, 1, 'Completion must refresh OCR/GPU availability without restarting');
  response = { ...response, status: 'idle' };
  await context.window.openRuntimeManager();
  assert.equal(elements.runtimeMessage.textContent, '', 'Installed OCR must not prompt users to enable OCR');
  for (const choice of ['skip', 'cpu', 'gpu']) {
    calls.length = 0;
    response = { ...response, status: 'idle', active: false, editions: response.editions.map(e => ({ ...e, installed: false })) };
    context.window = { subtitleycAppReady: Promise.resolve() };
    context.fetchJson = async (url, options) => {
      calls.push([url, options?.method]);
      return url === '/api/onboarding' ? { show_welcome: true } : response;
    };
    vm.runInNewContext(fs.readFileSync('static/runtime-manager.js', 'utf8'), context);
    await context.window.subtitleycWelcomeReady;
    assert.equal(elements.runtimeSkip.hidden, false);
    assert.equal(calls.some(call => call[1] === 'POST'), false, 'Welcome never downloads automatically');
    if (choice === 'skip') await elements.runtimeSkip.click();
    else await (choice === 'cpu' ? cpuButton() : gpuButton()).click();
    await Promise.resolve();
    assert.equal(calls.filter(call => call[0] === '/api/onboarding/complete').length, 1);
    const downloads = calls.filter(call => call[0].endsWith('/download'));
    assert.equal(downloads.length, choice === 'skip' ? 0 : 1);
    if (choice !== 'skip') assert.equal(downloads[0][0], `/api/runtimes/${choice === 'cpu' ? 'cpu' : 'gpu-cuda-12.9'}/download`);
  }
  console.log('Runtime chooser, opt-in download, retry, progress, and completion checks passed.');
  response = { ...response, editions: response.editions.map(e => ({ ...e, compatibility: { compatible: false, reason: 'Update driver' } })) };
  await context.window.openRuntimeManager();
  await Promise.resolve();
  assert.equal(gpuButton().disabled, true);
  assert.equal(cpuButton().disabled, false, 'An incompatible GPU must not block CPU setup');
  const count = calls.length;
  await gpuButton().click();
  assert.equal(calls.length, count, 'Blocked GPU cannot start downloading');
  response = { ...response, editions: response.editions.map(e => ({ ...e, compatibility: { compatible: true } })) };
  await elements.runtimeEditions.children[1].children[5].click();
  assert.equal(gpuButton().disabled, false, 'Recheck can enable GPU after driver update');
})().catch(error => { console.error(error); process.exitCode = 1; });
