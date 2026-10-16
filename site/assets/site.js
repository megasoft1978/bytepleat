(() => {
  const root = document.documentElement;
  root.classList.add('js');

  /* Menu */
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#nav-links');
  const setMenuOpen = open => {
    menu.setAttribute('aria-expanded', String(open));
    nav.classList.toggle('open', open);
  };
  if (menu && nav) {
    menu.addEventListener('click', () => setMenuOpen(menu.getAttribute('aria-expanded') !== 'true'));
    nav.addEventListener('click', event => { if (event.target.closest('a')) setMenuOpen(false); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') setMenuOpen(false); });
  }

  /* Theme: follows the system unless the visitor picks one. */
  const themeButton = document.querySelector('#theme-toggle');
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  const currentTheme = () => root.dataset.theme || (systemDark.matches ? 'dark' : 'light');
  try { const saved = localStorage.getItem('bytepleat-theme'); if (saved === 'light' || saved === 'dark') root.dataset.theme = saved; } catch (_) { /* storage unavailable */ }
  if (themeButton) {
    themeButton.hidden = false;
    themeButton.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem('bytepleat-theme', next); } catch (_) { /* ignore */ }
    });
  }

  /* Release data from project.json */
  const releases = 'https://github.com/megasoft1978/bytepleat/releases';
  const targets = {
    mac: { triple: 'aarch64-apple-darwin', name: 'macOS' },
    linux: { triple: 'x86_64-unknown-linux-gnu', name: 'Linux' },
    windows: { triple: 'x86_64-pc-windows-msvc', name: 'Windows' }
  };
  const $ = selector => document.querySelector(selector);
  const download = $('[data-release-link]');
  const installLabel = $('#install-label');
  const installCommand = $('#install-command');
  const details = $('#download-details');
  const picker = $('[data-js-only]');
  const copyStatus = $('#copy-status');
  let config = null;

  const platformText = navigator.userAgentData?.platform || navigator.platform || '';
  let selected = /win/i.test(platformText) ? 'windows'
    : /linux/i.test(platformText) && !/android/i.test(navigator.userAgent) ? 'linux' : 'mac';

  const safeReleaseUrl = value => {
    if (typeof value !== 'string') return null;
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.origin !== 'https://github.com' || url.username || url.password || url.search || url.hash) return null;
      if (/^\/megasoft1978\/bytepleat\/releases\/download\/[A-Za-z0-9._-]+\/[A-Za-z0-9._+-]+$/.test(url.pathname)) return url.href;
    } catch (_) { /* invalid URL */ }
    return null;
  };
  const validAsset = asset => {
    if (!asset || typeof asset !== 'object' || asset.available !== true) return null;
    const url = safeReleaseUrl(asset.url);
    const filename = typeof asset.filename === 'string' && /^[A-Za-z0-9][A-Za-z0-9._+-]{0,150}$/.test(asset.filename) ? asset.filename : null;
    if (!url || !filename || !new URL(url).pathname.endsWith(`/${filename}`)) return null;
    const sha256 = typeof asset.sha256 === 'string' && /^[a-fA-F0-9]{64}$/.test(asset.sha256) ? asset.sha256.toLowerCase() : null;
    return { url, filename, sha256 };
  };
  const assetFor = key => {
    const row = config?.targets?.find(item => item?.triple === targets[key].triple);
    return config?.release_status === 'available' ? validAsset(row?.asset) : null;
  };

  const installFor = (key, asset) => {
    const { url, filename, sha256 } = asset;
    const stem = filename.replace(/\.(tar\.gz|zip)$/, '');
    if (key === 'windows') {
      const check = sha256 ? `; if ((Get-FileHash .\\${filename} -Algorithm SHA256).Hash.ToLower() -ne '${sha256}') { throw 'SHA-256 mismatch' }` : '';
      return `Invoke-WebRequest -Uri '${url}' -OutFile .\\${filename}${check}; Expand-Archive -LiteralPath .\\${filename} -DestinationPath .\\bytepleat; .\\bytepleat\\${stem}\\bytepleat.exe --help`;
    }
    const hasher = key === 'mac' ? 'shasum -a 256' : 'sha256sum';
    const check = sha256 ? ` && echo '${sha256}  ${filename}' | ${hasher} -c -` : '';
    return `curl -fsSLO '${url}'${check} && mkdir -p ./bytepleat && tar -xzf '${filename}' -C ./bytepleat && ./bytepleat/${stem}/bytepleat --help`;
  };

  const render = () => {
    if (!picker) return;
    const asset = assetFor(selected);
    picker.hidden = !config;
    document.querySelectorAll('.platform').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.target === selected)));
    if (!asset) {
      if (download) { download.href = releases; download.textContent = 'See releases on GitHub'; }
      if (details) details.hidden = true;
      return;
    }
    if (download) {
      download.href = asset.url;
      download.textContent = `Download the CLI for ${targets[selected].name} (v${config.version})`;
      download.setAttribute('aria-label', `${download.textContent}, file ${asset.filename}`);
    }
    if (installLabel) installLabel.textContent = `Download, verify and run (${targets[selected].name})`;
    if (installCommand) installCommand.textContent = installFor(selected, asset);
    if (details) {
      details.hidden = false;
      details.textContent = `File: ${asset.filename}${asset.sha256 ? `. SHA-256: ${asset.sha256}` : ''}`;
    }
  };

  document.querySelectorAll('.platform').forEach(button => button.addEventListener('click', () => {
    selected = button.dataset.target in targets ? button.dataset.target : 'mac';
    render();
  }));

  /* Copy buttons */
  const fallbackCopy = value => {
    const field = document.createElement('textarea');
    field.value = value;
    field.setAttribute('readonly', '');
    field.style.cssText = 'position:fixed;opacity:0';
    document.body.append(field);
    field.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
    field.remove();
    return ok;
  };
  document.querySelectorAll('[data-copy-target]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', async () => {
      const value = document.getElementById(button.dataset.copyTarget)?.textContent || '';
      let ok = false;
      try {
        if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(value); ok = true; }
        else ok = fallbackCopy(value);
      } catch (_) { ok = fallbackCopy(value); }
      const original = button.dataset.label || button.textContent;
      button.dataset.label = original;
      button.textContent = ok ? 'Copied' : 'Select and copy';
      if (copyStatus) copyStatus.textContent = ok ? 'Copied to clipboard.' : 'Copy is unavailable here. Select the text and copy it.';
      setTimeout(() => { button.textContent = original; }, 2000);
    });
  });

  render();
  const configUrl = new URL('../project.json', document.currentScript.src);
  fetch(configUrl, { credentials: 'same-origin' })
    .then(response => { if (!response.ok) throw new Error('unavailable'); return response.json(); })
    .then(data => {
      if (!data || !Array.isArray(data.targets) || !['pending', 'available'].includes(data.release_status)) throw new Error('invalid');
      config = data;
      render();
    })
    .catch(() => { /* Static links keep working without the config. */ });
})();
