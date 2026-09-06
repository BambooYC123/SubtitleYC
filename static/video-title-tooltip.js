(() => {
  const title = document.querySelector('#videoMeta');
  const tooltip = document.querySelector('#videoTitleTooltip');
  const sync = () => window.subtitleycSyncNativePreview?.();
  const hide = () => { tooltip.hidden = true; sync(); };
  const show = () => {
    tooltip.textContent = title.textContent;
    tooltip.hidden = !tooltip.textContent.trim();
    sync();
  };
  title.addEventListener('pointerenter', show);
  title.addEventListener('pointerleave', hide);
  title.addEventListener('focus', show);
  title.addEventListener('blur', hide);
  title.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
  new MutationObserver(() => { if (!tooltip.hidden) show(); })
    .observe(title, { childList: true, characterData: true, subtree: true });
})();
