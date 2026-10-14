(() => {
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#nav-links');
  if (menu && nav) menu.addEventListener('click', () => {
    const expanded = menu.getAttribute('aria-expanded') === 'true';
    menu.setAttribute('aria-expanded', String(!expanded));
    nav.classList.toggle('open', !expanded);
  });

  const targetCodes = {
    mac: 'aarch64-apple-darwin',
    linux: 'x86_64-unknown-linux-gnu',
    windows: 'x86_64-pc-windows-msvc'
  };
  const output = document.querySelector('#target-triple');
  document.querySelectorAll('.platform').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('.platform').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    if (output) output.textContent = targetCodes[button.dataset.target] || targetCodes.mac;
  }));

  const status = document.querySelector('#copy-status');
  const fallbackCopy = value => {
    const field = document.createElement('textarea');
    field.value = value;
    field.setAttribute('readonly', '');
    field.style.position = 'fixed';
    field.style.opacity = '0';
    document.body.append(field);
    field.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
    field.remove();
    return copied;
  };
  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
    const value = button.dataset.copy;
    let copied = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
        copied = true;
      } else copied = fallbackCopy(value);
    } catch (_) { copied = fallbackCopy(value); }
    if (status) status.textContent = copied ? 'Command copied.' : `Copy is unavailable here. Select and copy: ${value}`;
  }));
})();
