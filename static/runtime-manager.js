/* OCR packages are downloaded only after the user chooses a download button. */
(() => {
  const dialog = document.querySelector('#runtimeDialog');
  const list = document.querySelector('#runtimeEditions');
  const message = document.querySelector('#runtimeMessage');
  const progress = document.querySelector('#runtimeProgress');
  const pause = document.querySelector('#runtimePause');
  const t = (value) => (window.SubtitleYCI18n?.t(value) || value).replace(/[\u2014\u2013]/g, '-');
  const size = (bytes) => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(2)} GiB` : `${(bytes / 1024 ** 2).toFixed(0)} MiB`;
  let timer;
  let previousStatus;
  let busy = false;
  let welcome = false;
  let dismissal;
  let activeDownload = false;
  let pausePending = false;
  const heading = document.querySelector('#runtimeTitle');
  const intro = document.querySelector('#runtimeIntro');
  const skip = document.querySelector('#runtimeSkip');

  function setWelcome(value) {
    welcome = value;
    heading.textContent = t('GPU OCR');
    intro.textContent = t('Speed up subtitle extraction with your Nvidia GPU.');
    skip.hidden = false;
    skip.textContent = t('Continue to SubtitleYC');
  }

  async function finishWelcome() {
    if (!welcome) return;
    dismissal ||= fetchJson('/api/onboarding/complete', { method: 'POST' });
    try { await dismissal; setWelcome(false); }
    catch (error) { dismissal = null; throw error; }
  }

  function render(data) {
    const storage = document.querySelector('#runtimeStorage');
    if (storage && data.app_size_bytes) {
      storage.textContent = `SubtitleYC ${data.app_version}: ${size(data.app_size_bytes)} ${t('for the app and FFmpeg')} · ${size(data.current_install_bytes)} ${t('including installed OCR packages (estimated). Videos, projects, models and caches are additional.')}`;
    }
    const cpuStorage = document.querySelector('#runtimeCpuStorage');
    const cpu = data.editions.find(edition => edition.id === 'cpu');
    if (cpuStorage) cpuStorage.textContent = cpu ? `${t('OCR engine:')} VideOCR ${cpu.version}. ${t('CPU OCR')}: ${t('Download size:')} ${size(cpu.size_bytes)}; ${t('Space after installation:')} ${size(cpu.unpacked_bytes)}. ` : '';
    const gpuStorage = document.querySelector('#runtimeGpuStorage');
    const gpuEdition = data.editions.find(edition => edition.id === 'gpu-cuda-12.9');
    if (gpuStorage) {
      const devices = gpuEdition?.compatibility?.devices || [];
      gpuStorage.textContent = gpuEdition ? `${t('Nvidia GPU - CUDA 12.9')}. ${t('OCR engine:')} VideOCR ${gpuEdition.version}. ${t('Total app + OCR after this install:')} ${size((data.current_install_bytes || 0) + (gpuEdition.installed ? 0 : gpuEdition.unpacked_bytes))}. ${devices.map(device => `${device.name}, ${device.driver}`).join('; ')}. ` : '';
    }
    list.replaceChildren();
    for (const edition of data.editions) {
      if (edition.id === 'cpu' && edition.installed) {
        const status = document.createElement('p');
        status.className = 'runtime-cpu-status';
        status.textContent = t('CPU OCR installed - ready to use');
        list.append(status);
        continue;
      }
      const row = document.createElement('section');
      row.className = 'runtime-edition';
      const title = document.createElement('h3');
      title.textContent = t(edition.id === 'cpu' ? 'CPU OCR' : 'Nvidia GPU - CUDA 12.9');
      const description = document.createElement('p');
      description.textContent = t(edition.id === 'cpu' ? 'Works without an Nvidia GPU.' : 'Use CUDA acceleration for faster OCR on a compatible Nvidia GPU.');
      const details = document.createElement('p');
      details.className = 'runtime-size-details';
      details.textContent = `${t('Download size:')} ${size(edition.size_bytes)}\n${t('Space after installation:')} ${size(edition.unpacked_bytes)}\n${t('Free space needed to install now:')} ${size(edition.required_free_bytes ?? (edition.installed ? 0 : edition.size_bytes + edition.unpacked_bytes + 256 * 1024 ** 2))}`;
      const button = document.createElement('button');
      const gpu = edition.id === 'gpu-cuda-12.9';
      const blocked = gpu && edition.compatibility?.compatible !== true;
      button.type = 'button';
      const resuming = data.edition === edition.id && ['paused', 'error'].includes(data.status);
      button.textContent = t(edition.installed
        ? (gpu ? 'GPU OCR already installed' : 'CPU OCR already installed')
        : resuming ? 'Resume OCR download' : (gpu ? 'Download Nvidia GPU OCR' : 'Download CPU OCR'));
      if (blocked && !edition.installed) button.textContent = t('GPU setup unavailable');
      button.disabled = data.active || edition.installed || blocked;
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          const data = await fetchJson(`/api/runtimes/${edition.id}/download`, { method: 'POST' });
          render(data);
          schedule();
          await finishWelcome();
          render(data);
          schedule();
        } catch (error) { message.textContent = error.message; button.disabled = false; }
      });
      row.append(title, description, details, button);
      if (gpu) {
        const compatibility = document.createElement('p');
        compatibility.setAttribute('role', 'status');
        compatibility.textContent = t(edition.compatibility?.compatible === true ? 'Compatible Nvidia GPU detected.' : edition.compatibility?.reason || 'Could not verify GPU compatibility. Check again or use CPU OCR.');
        const recheck = document.createElement('button');
        recheck.type = 'button';
        recheck.textContent = t('Check GPU again');
        recheck.disabled = data.active;
        recheck.hidden = edition.compatibility?.compatible === true;
        recheck.addEventListener('click', async () => {
          recheck.disabled = true;
          try { render(await fetchJson('/api/runtimes?recheck=true')); }
          catch (error) { message.textContent = error.message; recheck.disabled = false; }
        });
        row.append(compatibility, recheck);
        const nextStep = document.createElement('p');
        nextStep.className = 'runtime-next-step';
        nextStep.textContent = t('After installation, turn on GPU Acceleration in OCR settings.');
        row.append(nextStep);
      }
      list.append(row);
    }
    progress.hidden = !data.active;
    progress.max = data.total || 1;
    progress.value = data.bytes || 0;
    activeDownload = Boolean(data.active);
    pause.hidden = false;
    pause.disabled = !activeDownload || pausePending;
    const labels = { idle: data.editions.some(edition => edition.installed) ? '' : 'Choose a runtime to enable OCR. The subtitle editor is ready to use.',
      verifying: 'Verifying download…', installing: 'Installing OCR runtime…',
      ready: 'OCR runtime ready. You can now start extraction.',
      paused: 'Download paused. Choose Resume OCR download to continue.' };
    if (!data.editions.length) {
      message.textContent = t('Runtime downloads are not configured in this development build.');
    } else if (data.status === 'downloading') {
      const eta = data.speed > 0 ? Math.ceil((data.total - data.bytes) / data.speed / 60) : null;
      message.textContent = `${t('Downloading')} ${data.edition === 'cpu' ? 'CPU' : 'GPU'}: ${size(data.bytes)} / ${size(data.total)}${data.speed ? ` · ${size(data.speed)}/s` : ''}${eta !== null ? ` · ${eta} ${t('min remaining')}` : ''}`;
    } else {
      message.textContent = data.error || t(labels[data.status] ?? 'Checking GPU OCR…');
    }
    if (data.status === 'ready' && previousStatus !== 'ready') {
      refreshSystemInfo().catch(() => undefined);
    }
    previousStatus = data.status;
    if (data.active) schedule();
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(refresh, 1000);
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    try { render(await fetchJson('/api/runtimes')); }
    catch (error) { message.textContent = error.message; if (dialog.open) schedule(); }
    finally { busy = false; }
  }

  window.openRuntimeManager = () => {
    if (!dialog.open) dialog.showModal();
    return refresh();
  };
  document.querySelectorAll('[data-open-runtimes]').forEach(button => button.addEventListener('click', window.openRuntimeManager));
  document.querySelector('#runtimeClose').addEventListener('click', () => dialog.close());
  skip.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    finishWelcome().catch(error => { message.textContent = error.message; });
  });
  window.subtitleycWelcomeReady = window.subtitleycAppReady?.then(async () => {
    const status = await fetchJson('/api/onboarding');
    if (status.show_welcome) {
      setWelcome(true);
      await window.openRuntimeManager();
    }
  }).catch(error => { message.textContent = error.message; });
  pause.addEventListener('click', async () => {
    pausePending = true;
    pause.disabled = true;
    try { render(await fetchJson('/api/runtimes/pause', { method: 'POST' })); }
    catch (error) { message.textContent = error.message; }
    finally { pausePending = false; pause.disabled = !activeDownload; }
  });
})();
