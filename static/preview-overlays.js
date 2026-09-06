/* Native video sits above web content: modal visibility must cross the Qt bridge. */
(() => {
  const selector = 'dialog[open], [aria-modal="true"]';
  window.subtitleycModalOpen = () => [...document.querySelectorAll(selector)].some(element => {
    const rect = element.getBoundingClientRect();
    return !element.hidden && rect.width > 0 && rect.height > 0;
  });
  let frame = null;
  const sync = () => {
    if (frame !== null) return;
    frame = requestAnimationFrame(() => {
      frame = null;
      window.subtitleycSyncNativePreview?.();
    });
  };
  const containsModal = element => element instanceof Element &&
    (element.matches('dialog, [aria-modal="true"]') || element.querySelector('dialog, [aria-modal="true"]'));
  new MutationObserver(records => {
    if (records.some(record => containsModal(record.target))) sync();
  }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open', 'hidden', 'aria-hidden'] });
  document.addEventListener('close', sync, true);
  document.addEventListener('cancel', sync, true);
})();
