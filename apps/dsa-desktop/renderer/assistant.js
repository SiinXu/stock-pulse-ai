(function initializeDesktopAssistant() {
  const bridge = window.stockPulseAssistant;
  const serviceStatus = document.getElementById('serviceStatus');
  const serviceMarker = document.getElementById('serviceMarker');
  const lastReadyStatus = document.getElementById('lastReadyStatus');
  const form = document.getElementById('stockLookupForm');
  const formError = document.getElementById('formError');
  const stockCodeInput = document.getElementById('stockCodeInput');
  const closeButton = document.getElementById('closeButton');
  const showMainButton = document.getElementById('showMainButton');
  const hideMainButton = document.getElementById('hideMainButton');
  const actionButtons = [...document.querySelectorAll('[data-action]')];
  const allCommandButtons = [
    ...actionButtons,
    form.querySelector('button[type="submit"]'),
  ];
  let commandBusy = false;
  let latestState = {};

  function setBusy(isBusy) {
    commandBusy = isBusy;
    allCommandButtons.forEach((button) => {
      button.disabled = isBusy;
    });
    showMainButton.disabled = isBusy || latestState.mainWindowVisible === true;
    hideMainButton.disabled = isBusy || latestState.mainWindowVisible !== true;
  }

  function setError(message = '') {
    formError.textContent = message;
  }

  function formatReadyTime(value) {
    if (!value) {
      return '';
    }
    const readyAt = new Date(value);
    if (Number.isNaN(readyAt.getTime())) {
      return '';
    }
    return new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(readyAt);
  }

  function renderState(state = {}) {
    latestState = state;
    const statusLabels = {
      ready: 'Ready',
      starting: 'Starting',
      unavailable: 'Unavailable',
    };
    const normalizedStatus = Object.prototype.hasOwnProperty.call(
      statusLabels,
      state.serviceStatus
    )
      ? state.serviceStatus
      : 'unavailable';

    serviceStatus.textContent = statusLabels[normalizedStatus];
    serviceMarker.className = `status-marker ${normalizedStatus}`;
    showMainButton.disabled = commandBusy || state.mainWindowVisible === true;
    hideMainButton.disabled = commandBusy || state.mainWindowVisible !== true;

    const readyTime = formatReadyTime(state.lastReadyAt);
    lastReadyStatus.textContent = readyTime ? `Last ready ${readyTime}` : '';
  }

  async function runCommand(command) {
    setBusy(true);
    setError();
    try {
      const result = await command();
      if (result && result.ok === false) {
        setError('The requested action is unavailable.');
      } else if (result && result.serviceStatus) {
        renderState(result);
      }
    } catch (_error) {
      setError('The requested action is unavailable.');
    } finally {
      setBusy(false);
    }
  }

  if (!bridge) {
    renderState({ serviceStatus: 'unavailable', mainWindowVisible: false });
    setError('Desktop bridge unavailable.');
    setBusy(true);
    return;
  }

  actionButtons.forEach((button) => {
    button.addEventListener('click', () => {
      void runCommand(() => bridge.openAction(button.dataset.action));
    });
  });

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const stockCode = stockCodeInput.value.trim().toUpperCase();
    if (!/^[A-Z0-9.]{1,16}$/.test(stockCode)) {
      setError('Use 1-16 letters, numbers, or dots.');
      stockCodeInput.focus();
      return;
    }
    void runCommand(() => bridge.openAction('stock', stockCode));
  });

  showMainButton.addEventListener('click', () => {
    void runCommand(() => bridge.setMainWindowVisible(true));
  });
  hideMainButton.addEventListener('click', () => {
    void runCommand(() => bridge.setMainWindowVisible(false));
  });
  closeButton.addEventListener('click', () => {
    void bridge.hide();
  });

  bridge.onStateChange(renderState);
  void bridge.getState().then(renderState).catch(() => {
    renderState({ serviceStatus: 'unavailable', mainWindowVisible: false });
  });
}());
