const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const native = Boolean(window.__TAURI__?.core?.invoke);
const invoke = native ? window.__TAURI__.core.invoke : async () => { throw new Error('Native desktop backend required'); };
const listen = native ? window.__TAURI__.event.listen : async () => () => {};
let mode = 'create';
let selected = [];
let destination = null;
let currentJobs = [];
let lastJobsFingerprint = null;
let pollHandle = null;
let selectedEntries = [];
let selectiveExtraction = false;
let inspectionRequest = 0;
let inspectionInFlight = false;

const esc = (value) => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const basename = path => path.replace(/[\\/]$/, '').split(/[\\/]/).pop() || path;
function status(message, error=false) { const el=$('#status-message'); el.textContent=message; el.style.color=error?'#b34c42':''; }
function resetInspection() {
  inspectionRequest++;
  if(inspectionInFlight)status('');
  inspectionInFlight=false;
  selectedEntries=[]; selectiveExtraction=false;
  $('#archive-inspection').hidden=true;
  $('#inspection-summary').textContent='';
  $('#entry-list').replaceChildren();
}
function showSelection(paths, append=false) {
  const singleArchive = mode==='extract'||mode==='open';
  const incoming = paths;
  selected = singleArchive ? [...incoming] : [...(append?selected:[]), ...incoming];
  resetInspection();
  if(singleArchive&&selected.length>1)status(`Selected ${selected.length} archives. Multiarchive ${mode} is unsupported; select exactly one archive. No archive was processed.`,true);
  else status('');
  const host=$('#selection');
  if (!selected.length) { host.innerHTML='<div class="selection-empty"><span class="tiny-folder" aria-hidden="true">＋</span><span>No files selected yet</span></div>'; }
  else host.innerHTML=selected.map((path,i)=>`<div class="selected-item"><span class="file-glyph" aria-hidden="true">${path.endsWith('/')?'▰':'▱'}</span><span class="file-details"><strong>${esc(basename(path))}</strong><small title="${esc(path)}">${esc(path)}</small></span><button class="remove-item" type="button" data-remove="${i}" aria-label="Remove ${esc(basename(path))}">×</button></div>`).join('');
  host.querySelectorAll('[data-remove]').forEach(btn=>btn.addEventListener('click',()=>{selected.splice(Number(btn.dataset.remove),1);showSelection(selected);updateRunState();}));
  updateRunState();
}
function updateRunState() { const busy=currentJobs.some(job=>['queued','running','cancelling'].includes(job.state)); const unsupportedMulti=(mode==='open'||mode==='extract')&&selected.length>1; const emptyExtract=mode==='extract'&&selectiveExtraction&&selectedEntries.length===0; $('#run-job').disabled=!native || busy || inspectionInFlight || selected.length===0 || unsupportedMulti || emptyExtract || (mode!=='open'&&!destination); $('#run-job').title=unsupportedMulti?'Select one archive at a time':emptyExtract?'Select at least one entry to extract':inspectionInFlight?'Reading archive listing…':busy?'One archive job can run at a time':''; $('#selection-count').textContent=selected.length?`${selected.length} ${selected.length===1?'item':'items'} selected`:''; $('#extract-selected').disabled=selectedEntries.length===0; }
function setMode(next) {
  mode=next; destination=null; $('#destination-path').textContent='No location chosen';
  $$('.mode-tab').forEach(btn=>{const active=btn.dataset.mode===mode;btn.classList.toggle('active',active);btn.setAttribute('aria-selected',String(active));});
  $('#view-label').textContent=mode==='create'?'Create archive':mode==='extract'?'Extract archive':'Open archive';
  $('#input-title').textContent=mode==='create'?'Choose what to archive':mode==='extract'?'Choose an archive to extract':'Choose an archive to inspect';
  $('#input-hint').textContent=mode==='create'?'Select files or folders from your device.':'Select one supported archive from your device.';
  $('#format-section').hidden=mode!=='create'; $('#destination-section').hidden=mode==='open';
  resetInspection();
  $('#destination-title').textContent=mode==='create'?'Save archive as':'Extract to folder';
  $('#destination-hint').textContent=mode==='create'?'Choose where the finished archive will go.':'Choose where extracted files will be written.';
  $('#destination-step').textContent=mode==='create'?'03':'02';
  $('#run-label').textContent=mode==='create'?'Create archive':mode==='extract'?'Extract archive':'Inspect archive';
  showSelection([]); status('');
}
$$('.mode-tab').forEach(btn=>btn.addEventListener('click',()=>setMode(btn.dataset.mode)));
$$('input[name="format"]').forEach(input=>input.addEventListener('change',()=>{$$('.format-option').forEach(el=>el.classList.toggle('selected',el.contains(input)&&input.checked));destination=null;$('#destination-path').textContent='No location chosen';updateRunState();}));
$('#browse-inputs').addEventListener('click',async()=>{if(!native){status('Open this screen in the Bytepleat desktop app to browse files.',true);return;}try{const paths=await invoke('choose_inputs');showSelection(paths,true);}catch(e){status(String(e),true);}});
$('#browse-folder').addEventListener('click',async()=>{if(!native){status('Native folder access requires the desktop app.',true);return;}try{const path=await invoke('choose_input_directory');if(path)showSelection([path],true);}catch(e){status(String(e),true);}});
$('#drop-zone').addEventListener('click',e=>{if(e.target.closest('button'))return;$('#browse-inputs').click();});
$('#drop-zone').addEventListener('keydown',e=>{if(e.target!==e.currentTarget)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();$('#browse-inputs').click();}});
$('#choose-destination').addEventListener('click',async()=>{if(!native){status('Native save and folder dialogs require the desktop app.',true);return;}try{const value=mode==='create'?await invoke('choose_output',{format:$$('input[name="format"]').find(i=>i.checked).value}):await invoke('choose_directory');if(value){destination=value;$('#destination-path').textContent=value;updateRunState();}}catch(e){status(String(e),true);}});
$('#run-job').addEventListener('click',async()=>{
  if(!native){status('Native backend required. No archive operation was started.',true);return;}
  if((mode==='open'||mode==='extract')&&selected.length>1){status('Select exactly one archive. Multiarchive open and extraction are not supported; no archive was processed.',true);return;}
  if(mode==='extract'&&selectiveExtraction&&selectedEntries.length===0){status('Select at least one entry to extract. No archive operation was started.',true);updateRunState();return;}
  if(mode==='open'&&inspectionInFlight)return;
  try {
    if(mode==='open'){const isTar=/\.tar\.(zst|gz|lz4)$/i.test(selected[0]);const requestId=++inspectionRequest;const archivePath=selected[0];inspectionInFlight=true;updateRunState();status(isTar?'Reading TAR archive; listing fully decodes into private staging…':'Reading archive listing…');try{const listing=await invoke('inspect_archive',{path:archivePath});if(requestId!==inspectionRequest||mode!=='open'||selected.length!==1||selected[0]!==archivePath)return;renderArchiveListing(listing);status(`${listing.entries.length} of ${listing.total_entries} entries${listing.truncated?' (preview truncated)':''} · ${formatBytes(listing.total_bytes)} · listing only; contents have not been integrity-tested.`);}catch(error){if(requestId===inspectionRequest)status(String(error),true);}finally{if(requestId===inspectionRequest){inspectionInFlight=false;updateRunState();}}return;}
    const format=$$('input[name="format"]').find(i=>i.checked)?.value;
    const target=mode==='extract'?`${destination.replace(/[\\/]$/,'')}/${basename(selected[0]).replace(/\.(tar\.(?:zst|gz|lz4)|zip|7z)$/i,'')}-extracted`:destination;
    const request={action:mode==='create'?'create':'extract',inputs:selected.map(path=>path),destination:target,format:mode==='create'?format:null,selected_entries:mode==='extract'?[...selectedEntries]:[],max_output_bytes:1073741824};
    const id=await invoke('start_job',{request});status(`Job ${id} started.`);await refreshJobs();
  } catch(error){status(String(error),true);}
});
function renderArchiveListing(listing){
  const section=$('#archive-inspection');section.hidden=false;const total=listing.total_entries??listing.entries.length;const shown=Math.min(listing.entries.length,5000);$('#inspection-summary').textContent=`Showing ${shown} of ${total} items · ${formatBytes(listing.total_bytes)}${listing.truncated?' · preview limited':''}`;
  const host=$('#entry-list');host.innerHTML=listing.entries.slice(0,shown).map((entry,index)=>`<label class="entry-row"><input type="checkbox" data-entry="${index}"><span class="entry-name">${esc(entry.name)}</span><span class="entry-size">${entry.is_dir?'Folder':formatBytes(entry.size)}</span></label>`).join('') || '<p class="selection-empty">No entries listed.</p>';
  if(total>shown){const note=document.createElement('p');note.className='entry-limit';note.textContent=`Showing ${shown} of ${total} entries. Only listed entries can be selected for extraction.`;host.append(note);}
  host.querySelectorAll('[data-entry]').forEach(box=>box.addEventListener('change',()=>{const entry=listing.entries[Number(box.dataset.entry)].name;if(box.checked){selectedEntries.push(entry);}else{selectedEntries=selectedEntries.filter(name=>name!==entry);}updateRunState();}));
  $('#extract-selected').onclick=()=>{if(!selected.length||selected.length!==1||selectedEntries.length===0)return;const entries=[...selectedEntries];const archive=selected[0];setMode('extract');showSelection([archive]);selectedEntries=entries;selectiveExtraction=true;updateRunState();status(`${entries.length} selected entries will be retained after full archive decoding.`);};
}
function formatBytes(n){if(n===0)return '0 B';if(!n)return 'size unavailable';const units=['B','KB','MB','GB','TB'];let u=0,x=n;while(x>=1000&&u<units.length-1){x/=1000;u++;}return `${x.toFixed(u?1:0)} ${units[u]}`;}
function renderJobs(jobs){
  currentJobs=jobs;updateRunState();const fingerprint=JSON.stringify(jobs);if(fingerprint===lastJobsFingerprint)return;lastJobsFingerprint=fingerprint;const host=$('#job-list');if(!jobs.length){host.innerHTML='<p class="empty-history">Your archive jobs will appear here.</p>';return;}
  host.innerHTML=jobs.map(job=>{const progress=job.total_bytes&&!['failed','cancelled','cancelling'].includes(job.state)&&!['compressing','decoding','starting','failed','cancelled','cancelling'].includes(job.phase)?`<div class="progress-track" aria-label="${formatBytes(job.processed_bytes)} of ${formatBytes(job.total_bytes)}"><span style="width:${Math.min(100,job.processed_bytes/job.total_bytes*100)}%"></span></div>`:'';const actionLabel=job.state==='completed'&&job.action==='inspect'?'':job.state==='completed'?'Open folder':job.state==='running'?'Cancel':job.state==='cancelling'?'Stopping…':'';const terminal={failed:'Failed',cancelled:'Cancelled',completed:'Completed'}[job.state];return `<div class="job-link"><strong>${esc(job.action)} · ${esc(terminal||job.phase)}</strong><small>${esc(job.message||job.state)}${job.error?` — ${esc(job.error)}`:''}</small>${progress}${actionLabel?`<div class="job-actions"><button type="button" data-job="${esc(job.id)}" data-action="${job.state==='completed'?'open':'cancel'}" ${job.state==='cancelling'?'disabled':''}>${actionLabel}</button></div>`:''}</div>`;}).join('');
  host.querySelectorAll('[data-job]').forEach(btn=>btn.addEventListener('click',async()=>{try{if(btn.dataset.action==='cancel')await invoke('cancel_job',{id:btn.dataset.job});else await invoke('open_destination',{id:btn.dataset.job});await refreshJobs();}catch(e){status(String(e),true);}}));
}
async function refreshJobs(){if(!native)return;try{renderJobs(await invoke('jobs'));}catch(e){status(String(e),true);}}
async function receivePaths(action,paths,error){if(error){showSelection([]);status(error,true);return;}if(!paths?.length)return;setMode(action==='create'?'create':action==='extract'?'extract':'open');showSelection(paths);if(action!=='create'&&paths.length>1)status(`Selected ${paths.length} archives. Multiarchive ${action} is unsupported; select exactly one archive. No archive was processed.`,true);}
if(native){
  $('#native-notice').hidden=true;
  listen('selection',event=>receivePaths(event.payload.action,event.payload.paths,event.payload.error));
  listen('jobs-changed',refreshJobs);
  invoke('initial_selection').then(selection=>receivePaths(selection.action,selection.paths,selection.error)).catch(e=>status(String(e),true));
  const win=window.__TAURI__.webviewWindow.getCurrentWebviewWindow();
  win.onDragDropEvent(event=>{const payload=event.payload;if(payload.type==='over')$('#drop-zone').classList.add('drag-over');else{$('#drop-zone').classList.remove('drag-over');if(payload.type==='drop')showSelection(payload.paths,true);}});
  refreshJobs();pollHandle=setInterval(refreshJobs,250);
} else {
  $('#native-notice').hidden=false;
  $('#browse-inputs').disabled=true;$('#browse-folder').disabled=true;$('#choose-destination').disabled=true;
}
function toggleTheme(){const root=document.documentElement;const current=root.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');const next=current==='dark'?'light':'dark';root.dataset.theme=next;localStorage.setItem('bytepleat-theme',next);$('#theme-label').textContent=next.toUpperCase();}
const savedTheme=localStorage.getItem('bytepleat-theme');if(savedTheme){document.documentElement.dataset.theme=savedTheme;$('#theme-label').textContent=savedTheme.toUpperCase();}
$('#theme-toggle').addEventListener('click',toggleTheme);$('#theme-toggle-bottom').addEventListener('click',toggleTheme);
window.addEventListener('beforeunload',()=>{if(pollHandle)clearInterval(pollHandle);});
