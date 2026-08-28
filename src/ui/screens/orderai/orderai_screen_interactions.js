/* ORDERAI-UI-W2-01: local-only controls for synthetic screen models. */
(() => {
  const showFeedback = (panel, actionLabel, resultLabel) => {
    const feedback = panel.querySelector('.mc-action-feedback');
    if (!feedback) return;
    feedback.hidden = false;
    feedback.textContent = `${actionLabel}：${resultLabel}`;
  };

  const focusTarget = (targetScreen) => {
    if (!targetScreen) return;
    const target = document.getElementById(targetScreen);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const heading = target.querySelector('h2');
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      heading.focus({ preventScroll: true });
    }
  };

  const runAction = (button) => {
    const panel = button.closest('.mc-orderai-panel');
    if (!panel) return;
    showFeedback(panel, button.dataset.actionLabel || '', button.dataset.resultLabel || button.dataset.resultState || '');
    focusTarget(button.dataset.targetScreen);
  };

  const showConfirmDialog = (button) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'mc-confirm-dialog';
    dialog.innerHTML = `<form method="dialog"><p>${button.dataset.actionLabel || ''}</p><menu><button value="cancel" type="submit">${button.dataset.cancelLabel || ''}</button><button value="confirm" type="submit" autofocus>${button.dataset.confirmLabel || ''}</button></menu></form>`;
    dialog.addEventListener('close', () => {
      if (dialog.returnValue === 'confirm') runAction(button);
      dialog.remove();
    });
    document.body.append(dialog);
    dialog.showModal();
  };

  document.addEventListener('click', (event) => {
    const button = event.target.closest('.mc-action-button');
    if (!button) return;
    if (button.dataset.requiresConfirmation === 'true') {
      showConfirmDialog(button);
      return;
    }
    runAction(button);
  });
})();
