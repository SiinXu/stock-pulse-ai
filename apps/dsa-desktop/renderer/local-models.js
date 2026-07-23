(function initializeLocalModelCenter() {
  const bridge = window.stockPulseLocalModels;
  const statusMarker = document.getElementById('statusMarker');
  const statusText = document.getElementById('statusText');
  const statusMessage = document.getElementById('statusMessage');
  const detectButton = document.getElementById('detectButton');
  const startButton = document.getElementById('startButton');
  const stopButton = document.getElementById('stopButton');
  const installGuideButton = document.getElementById('installGuideButton');
  const presetList = document.getElementById('presetList');
  const installedList = document.getElementById('installedList');
  const installedEmpty = document.getElementById('installedEmpty');
  const pullProgress = document.getElementById('pullProgress');
  const pullProgressFill = document.getElementById('pullProgressFill');
  const pullProgressText = document.getElementById('pullProgressText');

  const STATUS_LABELS = {
    unknown: 'Checking…',
    'not-installed': 'Ollama not installed',
    stopped: 'Service stopped',
    starting: 'Starting service…',
    running: 'Service running',
    error: 'Service error',
  };

  let busy = false;
  let latestState = { status: 'unknown', installedModels: [], registeredModels: [] };

  function setMessage(text = '', kind = 'info') {
    statusMessage.textContent = text;
    statusMessage.className = `message ${kind}`;
  }

  function isRunning(state) {
    return state.status === 'running';
  }

  function renderPresets(state) {
    const installed = new Set(state.installedModels || []);
    presetList.replaceChildren();
    (bridge.presets || []).forEach((preset) => {
      const row = document.createElement('div');
      row.className = 'preset';

      const copy = document.createElement('div');
      copy.className = 'preset-copy';
      const name = document.createElement('p');
      name.className = 'preset-name';
      name.textContent = preset.label;
      const meta = document.createElement('p');
      meta.className = 'preset-meta';
      meta.textContent = `${preset.id} · ~${preset.approxSizeGb} GB · ${preset.minRamGb} GB RAM · ${preset.guidance}`;
      copy.append(name, meta);
      row.append(copy);

      if (installed.has(preset.id)) {
        const badge = document.createElement('span');
        badge.className = 'installed-badge';
        badge.textContent = 'Installed';
        row.append(badge);
      } else {
        const action = document.createElement('button');
        action.className = 'button';
        action.type = 'button';
        action.textContent = 'Install';
        action.disabled = busy || !isRunning(state);
        action.addEventListener('click', () => {
          void runCommand(() => bridge.pull(preset.id), `Downloading ${preset.id}…`);
        });
        row.append(action);
      }
      presetList.append(row);
    });
  }

  function renderInstalled(state) {
    const models = state.installedModels || [];
    const registered = new Set(state.registeredModels || []);
    installedList.replaceChildren();
    installedEmpty.hidden = models.length > 0;
    models.forEach((modelId) => {
      const item = document.createElement('li');
      item.className = 'list-item';
      const name = document.createElement('span');
      name.className = 'list-name';
      name.textContent = modelId;
      item.append(name);

      if (registered.has(modelId)) {
        const badge = document.createElement('span');
        badge.className = 'installed-badge';
        badge.textContent = 'Available for analysis';
        item.append(badge);
      } else {
        const action = document.createElement('button');
        action.className = 'button';
        action.type = 'button';
        action.textContent = 'Make available';
        action.disabled = busy;
        action.addEventListener('click', () => {
          void runCommand(() => bridge.register(modelId), '');
        });
        item.append(action);
      }
      installedList.append(item);
    });
  }

  function renderProgress(state) {
    const progress = state.operation === 'pull' ? state.progress : null;
    pullProgress.hidden = !progress;
    if (!progress) {
      pullProgressFill.style.width = '0%';
      pullProgressText.textContent = '';
      return;
    }
    const percent = Number.isFinite(progress.percent) ? progress.percent : null;
    pullProgressFill.style.width = percent === null ? '0%' : `${percent}%`;
    const status = progress.status || 'Downloading';
    pullProgressText.textContent = percent === null
      ? `${progress.modelId}: ${status}`
      : `${progress.modelId}: ${status} (${percent}%)`;
  }

  function renderState(state = {}) {
    latestState = { installedModels: [], registeredModels: [], ...state };
    const status = Object.prototype.hasOwnProperty.call(STATUS_LABELS, latestState.status)
      ? latestState.status
      : 'unknown';
    statusMarker.className = `status-marker ${status}`;
    statusText.textContent = STATUS_LABELS[status];

    startButton.hidden = status === 'running' || status === 'not-installed';
    startButton.disabled = busy || status === 'starting';
    stopButton.hidden = !(status === 'running' && latestState.managed === true);
    stopButton.disabled = busy;
    installGuideButton.hidden = status !== 'not-installed';
    detectButton.disabled = busy;

    if (latestState.message) {
      setMessage(latestState.message, status === 'error' ? 'error' : 'info');
    } else if (status === 'not-installed') {
      setMessage('Install Ollama to download and run local models.', 'info');
    } else {
      setMessage('', 'info');
    }

    renderPresets(latestState);
    renderInstalled(latestState);
    renderProgress(latestState);
  }

  function setBusy(nextBusy) {
    busy = nextBusy;
    renderState(latestState);
  }

  async function runCommand(command, pendingMessage) {
    setBusy(true);
    if (pendingMessage) {
      setMessage(pendingMessage, 'info');
    }
    try {
      const result = await command();
      if (result && result.ok === false) {
        setMessage(result.message || 'The requested action failed.', 'error');
      } else if (result && typeof result.status === 'string') {
        renderState(result);
      }
    } catch (_error) {
      setMessage('The requested action is unavailable.', 'error');
    } finally {
      setBusy(false);
    }
  }

  if (!bridge) {
    setMessage('Desktop bridge unavailable.', 'error');
    return;
  }

  detectButton.addEventListener('click', () => {
    void runCommand(() => bridge.detect(), 'Checking local runtime…');
  });
  startButton.addEventListener('click', () => {
    void runCommand(() => bridge.start(), 'Starting local model service…');
  });
  stopButton.addEventListener('click', () => {
    void runCommand(() => bridge.stop(), '');
  });
  installGuideButton.addEventListener('click', () => {
    void bridge.openInstallGuide();
  });

  bridge.onStateChange(renderState);
  void bridge.getState().then(renderState).catch(() => {
    renderState({ status: 'unknown' });
  });
}());
