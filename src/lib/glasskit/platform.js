const focusables = root => [...root.querySelectorAll([
  'a[href]',
  'button:not(:disabled)',
  'input:not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  '[tabindex]:not([tabindex="-1"])'
].join(','))].filter(node => !node.hidden && node.getClientRects().length);

const regularWidth = () => matchMedia('(min-width: 760px) and (min-height: 600px)').matches;
const finePointer = () => matchMedia('(hover: hover) and (pointer: fine)').matches;

function syncEnvironment(root) {
  root.dataset.iosSizeClass = regularWidth() ? 'regular' : 'compact';
  root.dataset.iosInput = finePointer() ? 'pointer' : 'touch';
}

function bindEnvironment(root) {
  syncEnvironment(root);
  const size = matchMedia('(min-width: 760px) and (min-height: 600px)');
  const pointer = matchMedia('(hover: hover) and (pointer: fine)');
  size.addEventListener?.('change', () => syncEnvironment(root));
  pointer.addEventListener?.('change', () => syncEnvironment(root));
}

function bindTabKeyboard(root) {
  root.querySelectorAll('.ios-tabbar').forEach(tabbar => {
    if (tabbar.dataset.iosKeyboardBound) return;
    tabbar.dataset.iosKeyboardBound = 'true';
    tabbar.setAttribute('role', 'tablist');
    tabbar.addEventListener('keydown', event => {
      const current = event.target.closest('[data-ios-tab]');
      if (!current) return;
      const tabs = [...tabbar.querySelectorAll('[data-ios-tab]:not(:disabled)')];
      const index = tabs.indexOf(current);
      if (index < 0) return;

      const previousKeys = regularWidth() ? ['ArrowUp', 'ArrowLeft'] : ['ArrowLeft', 'ArrowUp'];
      const nextKeys = regularWidth() ? ['ArrowDown', 'ArrowRight'] : ['ArrowRight', 'ArrowDown'];
      let next = null;

      if (previousKeys.includes(event.key)) next = tabs[(index - 1 + tabs.length) % tabs.length];
      if (nextKeys.includes(event.key)) next = tabs[(index + 1) % tabs.length];
      if (event.key === 'Home') next = tabs[0];
      if (event.key === 'End') next = tabs[tabs.length - 1];
      if (!next) return;

      event.preventDefault();
      next.focus();
      next.click();
    });
  });
}

function bindMenuKeyboard(root) {
  let lastMenuTrigger = null;

  root.addEventListener('click', event => {
    const trigger = event.target.closest('[data-ios-menu-trigger]');
    if (!trigger) return;
    lastMenuTrigger = trigger;
    queueMicrotask(() => {
      const name = trigger.dataset.iosMenuTrigger;
      const menu = document.querySelector(`[data-ios-menu="${CSS.escape(name)}"].is-open`);
      const first = menu?.querySelector('.ios-menu__item:not(:disabled)');
      if (first && finePointer()) first.focus({ preventScroll: true });
    });
  });

  document.addEventListener('keydown', event => {
    const menu = event.target.closest?.('.ios-menu.is-open');
    if (!menu) return;
    const items = [...menu.querySelectorAll('.ios-menu__item:not(:disabled)')];
    if (!items.length) return;
    const index = items.indexOf(document.activeElement);
    let next = null;

    if (event.key === 'ArrowDown') next = items[(Math.max(index, -1) + 1) % items.length];
    if (event.key === 'ArrowUp') next = items[(index <= 0 ? items.length : index) - 1];
    if (event.key === 'Home') next = items[0];
    if (event.key === 'End') next = items[items.length - 1];
    if (event.key === 'Escape') {
      event.preventDefault();
      document.body.click();
      lastMenuTrigger?.focus({ preventScroll: true });
      return;
    }
    if (!next) return;
    event.preventDefault();
    next.focus({ preventScroll: true });
  });
}

function bindModalFocus() {
  document.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const overlay = document.querySelector('.ios-overlay.is-open:not([hidden])');
    if (!overlay) return;
    const items = focusables(overlay);
    if (!items.length) {
      event.preventDefault();
      overlay.focus?.({ preventScroll: true });
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
}

function bindSelectionLists(root) {
  root.querySelectorAll('[data-ios-select-list]').forEach(list => {
    if (list.dataset.iosSelectionBound) return;
    list.dataset.iosSelectionBound = 'true';
    const rows = () => [...list.querySelectorAll('[data-ios-select-row]')];
    list.setAttribute('role', list.getAttribute('role') || 'listbox');

    rows().forEach(row => {
      row.setAttribute('role', row.getAttribute('role') || 'option');
      if (!row.hasAttribute('tabindex')) row.tabIndex = 0;
    });

    const select = row => {
      const multiple = list.hasAttribute('data-ios-multiple');
      if (!multiple) rows().forEach(item => item.setAttribute('aria-selected', String(item === row)));
      else row.setAttribute('aria-selected', String(row.getAttribute('aria-selected') !== 'true'));
      row.dispatchEvent(new CustomEvent('ios:select', { bubbles: true, detail: { value: row.dataset.iosSelectRow } }));
    };

    list.addEventListener('click', event => {
      const row = event.target.closest('[data-ios-select-row]');
      if (row && list.contains(row)) select(row);
    });

    list.addEventListener('keydown', event => {
      const row = event.target.closest('[data-ios-select-row]');
      if (!row) return;
      const items = rows();
      const index = items.indexOf(row);
      let next = null;
      if (event.key === 'ArrowDown') next = items[Math.min(items.length - 1, index + 1)];
      if (event.key === 'ArrowUp') next = items[Math.max(0, index - 1)];
      if (event.key === 'Home') next = items[0];
      if (event.key === 'End') next = items[items.length - 1];
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        select(row);
        return;
      }
      if (!next) return;
      event.preventDefault();
      next.focus();
    });
  });
}

function bindSettingsShortcut(root) {
  if (root.dataset.iosSettingsShortcutBound) return;
  root.dataset.iosSettingsShortcutBound = 'true';
  document.addEventListener('keydown', event => {
    if (!(event.metaKey || event.ctrlKey) || event.key !== ',') return;
    const settings = root.querySelector('[data-ios-tab="settings"]');
    if (!settings) return;
    event.preventDefault();
    settings.click();
    settings.focus({ preventScroll: true });
  });
}

function bindPageControls(root) {
  root.querySelectorAll('[data-ios-page-control]').forEach(control => {
    if (control.dataset.iosPageBound) return;
    control.dataset.iosPageBound = 'true';
    const pages = [...control.querySelectorAll('[data-ios-page]')];
    if (!pages.length) return;
    pages.forEach((page, index) => {
      page.setAttribute('role', 'button');
      page.tabIndex = page.getAttribute('aria-current') === 'true' ? 0 : -1;
      page.setAttribute('aria-label', page.getAttribute('aria-label') || `Page ${index + 1} of ${pages.length}`);
    });
    const activate = page => {
      pages.forEach(item => {
        const active = item === page;
        item.setAttribute('aria-current', String(active));
        item.tabIndex = active ? 0 : -1;
      });
      control.dispatchEvent(new CustomEvent('ios:pagechange', { bubbles: true, detail: { index: pages.indexOf(page) } }));
    };
    control.addEventListener('click', event => {
      const page = event.target.closest('[data-ios-page]');
      if (page) activate(page);
    });
    control.addEventListener('keydown', event => {
      const page = event.target.closest('[data-ios-page]');
      if (!page) return;
      const index = pages.indexOf(page);
      let next = null;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = pages[Math.min(pages.length - 1, index + 1)];
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = pages[Math.max(0, index - 1)];
      if (!next) return;
      event.preventDefault();
      activate(next);
      next.focus();
    });
  });
}

export function initIOSPlatform(root = document.querySelector('[data-ios-app]')) {
  if (!root) return null;
  if (root.__iosPlatform) {
    root.__iosPlatform.refresh();
    return root.__iosPlatform;
  }

  bindEnvironment(root);
  bindTabKeyboard(root);
  bindMenuKeyboard(root);
  bindModalFocus();
  bindSettingsShortcut(root);

  const refresh = () => {
    bindTabKeyboard(root);
    bindSelectionLists(root);
    bindPageControls(root);
  };

  refresh();

  const observer = new MutationObserver(records => {
    if (records.some(record => record.addedNodes.length || record.removedNodes.length)) refresh();
  });
  observer.observe(root, { childList: true, subtree: true });

  root.__iosPlatform = {
    sync: () => syncEnvironment(root),
    refresh,
    disconnect: () => observer.disconnect()
  };
  return root.__iosPlatform;
}

function autoInit() {
  document.querySelectorAll('[data-ios-app]').forEach(initIOSPlatform);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', autoInit, { once: true });
else autoInit();
