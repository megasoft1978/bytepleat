(() => {
  const repo = 'https://github.com/megasoft1978/arqlet';
  const releases = `${repo}/releases`;
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#nav-links');
  if (menu && nav) menu.addEventListener('click', () => {
    const expanded = menu.getAttribute('aria-expanded') === 'true';
    menu.setAttribute('aria-expanded', String(!expanded));
    nav.classList.toggle('open', !expanded);
  });

  const targets = {
    mac: { triple: 'aarch64-apple-darwin', label: 'macOS · Apple silicon' },
    linux: { triple: 'x86_64-unknown-linux-gnu', label: 'Linux · x86-64' },
    windows: { triple: 'x86_64-pc-windows-msvc', label: 'Windows · x86-64' }
  };
  const status = document.querySelector('#copy-status');
  const output = document.querySelector('#target-triple');
  const targetStatus = document.querySelector('#target-status');
  const details = document.querySelector('#download-details');
  const commands = document.querySelector('#install-commands');
  const download = document.querySelector('[data-release-link]');
  const releaseNote = document.querySelector('[data-release-note]');
  const installSummary = document.querySelector('[data-install-summary]');
  const releaseStatus = document.querySelector('[data-release-status]');
  const releaseFaq = document.querySelector('[data-release-faq]');
  const shaCommand = document.querySelector('#checksum-command');
  const extractCommand = document.querySelector('#extract-command');
  const shaCopy = document.querySelector('#copy-checksum');
  const installCopy = document.querySelector('#copy-install');
  let config = null;
  const platform = navigator.userAgentData?.platform || navigator.platform || '';
  let selected = /win/i.test(platform) ? 'windows' : /linux/i.test(platform) && !/android/i.test(navigator.userAgent) ? 'linux' : 'mac';
  const configUrl = new URL('../project.json', document.currentScript.src);

  const safeReleaseUrl = value => {
    if (typeof value !== 'string') return null;
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.origin !== 'https://github.com' || url.username || url.password || url.search || url.hash) return null;
      if (url.pathname === '/megasoft1978/arqlet/releases' || /^\/megasoft1978\/arqlet\/releases\/tag\/[A-Za-z0-9._-]+$/.test(url.pathname)) return url.href;
      if (/^\/megasoft1978\/arqlet\/releases\/download\/[A-Za-z0-9._-]+\/[A-Za-z0-9._+-]+$/.test(url.pathname)) return url.href;
    } catch (_) { return null; }
    return null;
  };
  const validAsset = asset => {
    if (!asset || typeof asset !== 'object' || Array.isArray(asset)) return null;
    if (asset.available !== true) return null;
    const url = safeReleaseUrl(asset.url);
    const filename = typeof asset.filename === 'string' && /^[A-Za-z0-9][A-Za-z0-9._+-]{0,150}$/.test(asset.filename) ? asset.filename : null;
    if (!url || !filename || !new URL(url).pathname.endsWith(`/${filename}`)) return null;
    const sha256 = typeof asset.sha256 === 'string' && /^[a-fA-F0-9]{64}$/.test(asset.sha256) ? asset.sha256.toLowerCase() : null;
    const checksumUrl = asset.checksum_url == null ? null : safeReleaseUrl(asset.checksum_url);
    return { url, filename, sha256, checksumUrl };
  };
  const targetData = key => {
    const fallback = targets[key];
    const row = config?.targets?.find(item => item?.triple === fallback.triple);
    return { ...fallback, status: row?.status || 'planned', asset: validAsset(row?.asset) };
  };
  const prettyStatus = value => ({ passed: 'Native CI passed', verified: 'Native CI passed', pending: 'Native CI pending', planned: 'Planned target', failed: 'Native CI failed' }[value] || 'Status unavailable');
  const copyCommands = (checksum, extraction) => {
    if (shaCommand) shaCommand.textContent = checksum;
    if (extractCommand) extractCommand.textContent = extraction;
    if (shaCopy) shaCopy.dataset.copy = checksum;
    if (installCopy) installCopy.dataset.copy = extraction;
  };
  const render = () => {
    const item = targetData(selected);
    document.querySelectorAll('.platform').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.target === selected)));
    if (output) output.textContent = item.triple;
    if (targetStatus) targetStatus.textContent = prettyStatus(item.status);
    document.querySelectorAll('[data-target-status]').forEach(node => {
      const target = targetData(node.dataset.targetStatus);
      node.textContent = prettyStatus(target.status);
    });
    const available = config?.release_status === 'available' && item.asset;
    if (download) {
      download.href = available ? item.asset.url : releases;
      download.textContent = available ? `Download for ${selected === 'windows' ? 'Windows' : selected === 'linux' ? 'Linux' : 'macOS'}` : 'View release status ↗';
      download.setAttribute('aria-label', available ? `Download ${item.asset.filename}` : 'View release status on GitHub');
    }
    if (details) {
      details.hidden = !available;
      details.textContent = available ? `Selected build: ${item.asset.filename}${item.asset.sha256 ? ` · SHA-256 ${item.asset.sha256}` : ''}${item.asset.checksumUrl ? ` · Checksums: ${item.asset.checksumUrl}` : ''}` : '';
    }
    if (config?.release_status === 'available') {
      if (releaseNote) releaseNote.textContent = `Version ${config.version || '0.5.0'} · first public release available · source is open on GitHub`;
      if (releaseStatus) releaseStatus.textContent = `First public release available. Native CI: ${config.native_ci_status || 'status unavailable'}.`;
      if (releaseFaq) releaseFaq.textContent = 'The first public release is available. Choose a platform above to see its published asset and checksum details.';
      if (installSummary) installSummary.textContent = 'Choose a target to view its published package, checksum, and installation commands.';
    } else if (config?.release_status === 'pending') {
      if (releaseNote) releaseNote.textContent = `Version ${config.version || '0.5.0'} · first public release pending · source is open on GitHub`;
      if (installSummary) installSummary.textContent = 'The first public release is pending. Target CI status is shown below; no package is downloadable until an asset is published.';
    }
    if (commands) commands.hidden = !available;
    if (available) {
      const file = item.asset.filename;
      const unixHash = selected === 'mac' ? 'shasum -a 256' : 'sha256sum';
      const stem = file.endsWith('.tar.gz') ? file.slice(0, -7) : file.endsWith('.zip') ? file.slice(0, -4) : file;
      const hashCmd = item.asset.sha256
        ? selected === 'windows' ? `if ((Get-FileHash .\\${file} -Algorithm SHA256).Hash.ToLower() -ne '${item.asset.sha256}') { throw 'SHA-256 mismatch' }` : `echo '${item.asset.sha256}  ${file}' | ${unixHash} -c -`
        : item.asset.checksumUrl
          ? (() => {
            const sumFile = decodeURIComponent(new URL(item.asset.checksumUrl).pathname.split('/').pop());
            return selected === 'windows' ? `Invoke-WebRequest -Uri '${item.asset.checksumUrl}' -OutFile '.\\${sumFile}'; Get-Content '.\\${sumFile}'` : `curl -fsSLO '${item.asset.checksumUrl}'; cat '${sumFile}'`;
          })()
          : selected === 'windows' ? `Get-FileHash .\\${file} -Algorithm SHA256` : `${unixHash} ./${file}`;
      const extractCmd = selected === 'windows'
        ? `Expand-Archive -LiteralPath .\\${file} -DestinationPath .\\arqlet; .\\arqlet\\${stem}\\arqlet.exe --help`
        : `mkdir -p ./arqlet && tar -xzf '${file}' -C ./arqlet && chmod +x ./arqlet/${stem}/arqlet && ./arqlet/${stem}/arqlet --help`;
      copyCommands(hashCmd, extractCmd);
    }
  };

  document.querySelectorAll('.platform').forEach(button => button.addEventListener('click', () => {
    selected = button.dataset.target in targets ? button.dataset.target : 'mac';
    document.querySelectorAll('.platform').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    render();
  }));

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
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(value); copied = true; }
      else copied = fallbackCopy(value);
    } catch (_) { copied = fallbackCopy(value); }
    if (status) status.textContent = copied ? 'Command copied.' : `Copy is unavailable here. Select and copy: ${value}`;
  }));

  render();
  fetch(configUrl, { credentials: 'same-origin' }).then(response => {
    if (!response.ok) throw new Error('Configuration unavailable');
    return response.json();
  }).then(data => {
    if (!data || !Array.isArray(data.targets) || !['pending', 'available'].includes(data.release_status)) throw new Error('Invalid configuration');
    config = data;
    render();
  }).catch(() => { /* Static pending content remains usable without configuration. */ });
})();
