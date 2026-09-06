// Serialize requests and never apply an old response over newer edits.
function createSubtitleSaveCoordinator({ snapshot, write, apply, changed }) {
  let pending = Promise.resolve();
  let active = 0;
  return {
    get busy() { return active > 0; },
    save() {
      const captured = JSON.stringify(snapshot());
      active += 1;
      const result = pending.catch(() => {}).then(async () => {
        const payload = await write(JSON.parse(captured));
        if (JSON.stringify(snapshot()) === captured) apply(payload);
        else changed();
        return payload;
      });
      pending = result.finally(() => { active -= 1; });
      pending.catch(() => {});
      return pending;
    },
  };
}

// Qt polls this status because runJavaScript does not await JS promises.
function installSubtitleCloseGuard({ dirty, save, busy }) {
  window.subtitleycCloseState = () => ({ dirty: dirty(), busy: busy() });
  window.subtitleycSaveForClose = () => {
    window.subtitleycCloseSaveResult = "pending";
    Promise.resolve().then(save).then(() => {
      window.subtitleycCloseSaveResult = dirty() || busy() ? "changed" : "saved";
    }).catch((error) => {
      window.subtitleycCloseSaveResult = String(error.message || error);
    });
  };
}
