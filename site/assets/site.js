(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const $ = selector => document.querySelector(selector);
  const $$ = selector => Array.from(document.querySelectorAll(selector));

  /* Menu (narrow screens) */
  const menu = $('.menu-toggle');
  const nav = $('#nav-links');
  if (menu && nav) {
    menu.hidden = false;
    const setMenuOpen = open => {
      menu.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('open', open);
    };
    menu.addEventListener('click', () => setMenuOpen(menu.getAttribute('aria-expanded') !== 'true'));
    nav.addEventListener('click', event => { if (event.target.closest('a')) setMenuOpen(false); });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') { setMenuOpen(false); menu.focus(); }
    });
  }

  /* Theme: follows the system unless the visitor picks one (saved locally). */
  const themeButton = $('#theme-toggle');
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  const currentTheme = () => root.dataset.theme || (systemDark.matches ? 'dark' : 'light');
  const labelTheme = () => {
    if (themeButton) themeButton.setAttribute('aria-label', currentTheme() === 'dark' ? 'Use light theme' : 'Use dark theme');
  };
  if (themeButton) {
    themeButton.hidden = false;
    labelTheme();
    systemDark.addEventListener?.('change', labelTheme);
    themeButton.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem('bytepleat-theme', next); } catch (_) { /* storage unavailable */ }
      labelTheme();
    });
  }

  /* Release data from project.json */
  const releases = 'https://github.com/megasoft1978/bytepleat/releases';
  const targets = {
    mac: { triple: 'aarch64-apple-darwin', name: 'macOS', tab: 'macos' },
    linux: { triple: 'x86_64-unknown-linux-gnu', name: 'Linux', tab: 'linux' },
    windows: { triple: 'x86_64-pc-windows-msvc', name: 'Windows', tab: 'windows' }
  };
  const download = $('[data-release-link]');
  const meta = $('#download-meta');
  const installLabel = $('#install-label');
  const installCommand = $('#install-command');
  const copyStatus = $('#copy-status');
  const fullCommand = $('.full-command');
  const quickLabel = $('#quick-label');
  const quickCommand = $('#quick-command');
  let config = null;

  const platformText = navigator.userAgentData?.platform || navigator.platform || '';
  const selected = /win/i.test(platformText) ? 'windows'
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
    const checksum = safeReleaseUrl(asset.checksum_url);
    const checksumUrl = checksum && new URL(checksum).pathname.endsWith(`/${filename}.sha256`) ? checksum : null;
    return { url, filename, sha256, checksumUrl };
  };
  const assetFor = key => {
    const row = config?.targets?.find(item => item?.triple === targets[key].triple);
    return config?.release_status === 'available' ? validAsset(row?.asset) : null;
  };
  const stemOf = filename => filename.replace(/\.(tar\.gz|zip)$/, '');

  /* One-line download, verify and run command for the hero. */
  const installFor = (key, asset) => {
    const { url, filename, sha256 } = asset;
    const stem = stemOf(filename);
    if (key === 'windows') {
      const check = sha256 ? `; if ((Get-FileHash .\\${filename} -Algorithm SHA256).Hash.ToLower() -ne '${sha256}') { throw 'SHA-256 mismatch' }` : '';
      return `Invoke-WebRequest -Uri '${url}' -OutFile .\\${filename}${check}; Expand-Archive -LiteralPath .\\${filename} -DestinationPath .\\bytepleat; .\\bytepleat\\${stem}\\bytepleat.exe --help`;
    }
    const hasher = key === 'mac' ? 'shasum -a 256' : 'sha256sum';
    const check = sha256 ? ` &&\necho '${sha256}  ${filename}' | ${hasher} -c -` : '';
    return `curl -fsSLO '${url}'${check} &&\nmkdir -p ./bytepleat && tar -xzf '${filename}' -C ./bytepleat &&\n./bytepleat/${stem}/bytepleat --help`;
  };

  /* Short extract-and-run form for the hero; the verified form sits under "Show the full command". */
  const quickFor = (key, asset) => {
    const stem = stemOf(asset.filename);
    return key === 'windows'
      ? `Expand-Archive .\\${asset.filename} -DestinationPath .\n.\\${stem}\\bytepleat.exe --help`
      : `tar -xzf ${asset.filename}\n./${stem}/bytepleat --help`;
  };

  /* The three install steps per system (download, check, open). */
  const stepsFor = (key, asset) => {
    const { url, filename, checksumUrl } = asset;
    const stem = stemOf(filename);
    const sidecar = checksumUrl || `${url}.sha256`;
    if (key === 'windows') {
      const pattern = filename.replace(/\./g, '\\.');
      return [
        `Invoke-WebRequest -Uri '${url}' -OutFile ${filename}\nInvoke-WebRequest -Uri '${sidecar}' -OutFile ${filename}.sha256`,
        `$asset = '${filename}'\n$entry = Get-Content -LiteralPath "$asset.sha256" -Raw\nif ($entry -notmatch '^([0-9a-fA-F]{64})\\s+${pattern}\\s*$') { throw 'Invalid checksum sidecar or filename' }\nif ((Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash -ne $Matches[1]) { throw 'SHA-256 mismatch' }\n'SHA-256 verified'`,
        `Expand-Archive -LiteralPath .\\${filename} -DestinationPath .\n.\\${stem}\\bytepleat.exe --help`
      ];
    }
    return [
      `curl -fL --remote-name-all \\\n${url} \\\n${sidecar}`,
      `${key === 'mac' ? 'shasum -a 256' : 'sha256sum'} -c ${filename}.sha256`,
      `tar -xzf ${filename} && ./${stem}/bytepleat --help`
    ];
  };

  const render = () => {
    const asset = assetFor(selected);
    if (download) {
      if (asset) {
        download.href = asset.url;
        download.textContent = `Download for ${targets[selected].name}`;
        download.setAttribute('aria-label', `Download Bytepleat ${config.version} for ${targets[selected].name}, file ${asset.filename}`);
      } else if (config) {
        download.href = releases;
        download.textContent = 'See releases on GitHub';
        download.removeAttribute('aria-label');
      }
    }
    if (asset && meta) {
      const row = config.targets.find(item => item?.triple === targets[selected].triple);
      const label = typeof row?.label === 'string' ? row.label : targets[selected].name;
      meta.textContent = `Version ${config.version} · command-line tool · ${label} · `;
      const link = document.createElement('a');
      link.href = asset.checksumUrl || `${asset.url}.sha256`;
      link.textContent = 'SHA-256 checksum';
      meta.append(link);
    }
    if (asset && installLabel) installLabel.textContent = `Download, verify and run on ${targets[selected].name}`;
    if (asset && installCommand) installCommand.textContent = installFor(selected, asset);
    if (asset && fullCommand) fullCommand.hidden = false;
    if (asset && quickLabel) quickLabel.textContent = 'After the download, in the same folder';
    if (asset && quickCommand) quickCommand.textContent = quickFor(selected, asset);

    Object.keys(targets).forEach(key => {
      const item = assetFor(key);
      if (!item) return;
      const link = $(`[data-asset-link="${key}"]`);
      if (link) link.href = item.url;
      const sum = $(`[data-checksum-link="${key}"]`);
      if (sum) sum.href = item.checksumUrl || `${item.url}.sha256`;
      stepsFor(key, item).forEach((text, index) => {
        const code = document.getElementById(`${key}-${index + 1}`);
        if (code) code.textContent = text;
      });
    });
  };

  /* Install tabs (ARIA tabs; without JS all panels are shown stacked). */
  const tablist = $('.tabs');
  const tabs = $$('.tabs [role="tab"]');
  const selectTab = (tab, focus) => {
    tabs.forEach(item => {
      const on = item === tab;
      item.setAttribute('aria-selected', String(on));
      item.tabIndex = on ? 0 : -1;
      const panel = document.getElementById(item.getAttribute('aria-controls'));
      if (panel) panel.hidden = !on;
    });
    if (focus) tab.focus();
  };
  if (tablist && tabs.length) {
    tablist.hidden = false;
    tabs.forEach(tab => {
      const panel = document.getElementById(tab.getAttribute('aria-controls'));
      if (panel) {
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', tab.id);
        panel.tabIndex = 0;
      }
      tab.addEventListener('click', () => selectTab(tab, false));
      tab.addEventListener('keydown', event => {
        const index = tabs.indexOf(tab);
        const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 }[event.key];
        if (next === undefined) return;
        event.preventDefault();
        selectTab(tabs[(next + tabs.length) % tabs.length], true);
      });
    });
    const fromHash = tabs.find(tab => `#${tab.getAttribute('aria-controls')}` === location.hash);
    selectTab(fromHash || tabs.find(tab => tab.id === `tab-${targets[selected].tab}`) || tabs[0], false);
    window.addEventListener('hashchange', () => {
      const tab = tabs.find(item => `#${item.getAttribute('aria-controls')}` === location.hash);
      if (tab) selectTab(tab, false);
    });
  }

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
  $$('[data-copy-target]').forEach(button => {
    button.hidden = false;
    let timer = 0;
    button.addEventListener('click', async () => {
      const value = document.getElementById(button.dataset.copyTarget)?.textContent || '';
      let ok = false;
      try {
        if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(value); ok = true; }
        else ok = fallbackCopy(value);
      } catch (_) { ok = fallbackCopy(value); }
      button.textContent = ok ? 'Copied' : 'Select and copy';
      button.classList.toggle('is-done', ok);
      if (copyStatus) copyStatus.textContent = ok ? 'Copied to clipboard.' : 'Copy is unavailable here. Select the text and copy it.';
      clearTimeout(timer);
      timer = setTimeout(() => { button.textContent = 'Copy'; button.classList.remove('is-done'); }, 2000);
    });
  });

  /* Hero fold: split the sheet into eight strips that gather into pleats once,
     about 600ms after first paint. The toggle replays it on request only. */
  const fold = $('#fold');
  const strips = fold?.querySelector('.fold-strips');
  const toggle = fold?.querySelector('.fold-toggle');
  if (fold && strips && toggle) {
    const first = strips.querySelector('.strip');
    const widths = [0.098, 0.086, 0.076, 0.068, 0.061, 0.055, 0.05, 0.046];
    const total = widths.reduce((sum, w) => sum + w, 0);
    let x = (1 - total) / 2;
    for (let i = 1; i < 8; i += 1) strips.append(first.cloneNode(true));
    Array.from(strips.children).forEach((strip, i) => {
      strip.style.setProperty('--i', i);
      strip.style.setProperty('--dx', (8 * x - i).toFixed(4));
      strip.style.setProperty('--s', (8 * widths[i]).toFixed(4));
      strip.style.setProperty('--delay', `${i * 22}ms`);
      x += widths[i];
    });
    fold.classList.add('is-split');
    toggle.hidden = false;
    const setFolded = folded => {
      fold.classList.toggle('is-folded', folded);
      toggle.textContent = folded ? 'Unfold' : 'Fold';
    };
    setFolded(false);
    let touched = false;
    toggle.addEventListener('click', () => { touched = true; setFolded(!fold.classList.contains('is-folded')); });
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const start = () => (reduced ? setFolded(true) : setTimeout(() => { if (!touched) setFolded(true); }, 600));
    if (document.readyState === 'complete') requestAnimationFrame(start);
    else window.addEventListener('load', () => requestAnimationFrame(start), { once: true });
  }

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
