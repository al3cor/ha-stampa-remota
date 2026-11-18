// Stampa remota - pannello laterale di Home Assistant (web component, nessuna libreria).
// Stile sobrio: elementi e colori del tema di HA (ha-card, ha-icon, ha-switch), accento verde come le plance di casa.
// Le chiamate passano dalle API autenticate di HA.
const I18N = {
  it: {title: 'Stampa', printer: 'Stampante', new: 'Nuova stampa', recent: 'Ultime stampe', none: 'Nessuna stampa ancora',
       pick: 'Scegli un file', pick_s: 'PDF, foto (JPG, PNG, HEIC) o testo · massimo 60 MB', change: 'Cambia',
       copies: 'Copie', mono: 'Bianco e nero', mono_s: 'Usa solo l\'inchiostro nero', fit: 'Adatta al foglio', fit_s: 'Rimpicciolisce la pagina se serve',
       pages: 'Pagine', pages_s: 'Vuoto = tutte, es. 1-3,5', all: 'Tutte', print: 'Stampa',
       sent: 'Inviato alla stampante', uploading: 'Caricamento…', converting: 'Preparazione delle pagine…',
       lost: 'Connessione persa durante il caricamento', weird: 'Risposta inattesa', error: 'Errore', cancel: 'Annulla',
       copy1: 'copia', copyN: 'copie', page1: 'pagina', pageN: 'pagine', unknown: 'Stampante', paper: 'Carta',
       ready: 'Pronta', busy: 'In stampa', stopped: 'Ferma', offline: 'Non raggiungibile', offline_s: 'Le stampe restano in coda e partono quando torna disponibile',
       ink: {Black: 'Nero', Color: 'Colore', Cyan: 'Ciano', Magenta: 'Magenta', Yellow: 'Giallo'},
       st: {conversione: 'Preparazione', in_coda: 'In coda', invio: 'Invio', stampa: 'In stampa', fatto: 'Stampato', annullato: 'Annullato', errore: 'Errore'},
       al: {'media-empty': 'Carta finita', 'media-needed': 'Carta finita', 'media-jam': 'Foglio inceppato',
            'toner-low': 'Toner in esaurimento', 'toner-empty': 'Toner finito', 'marker-supply-low': 'Inchiostro in esaurimento',
            'marker-supply-empty': 'Inchiostro finito', 'door-open': 'Sportello aperto', 'cover-open': 'Coperchio aperto', 'paused': 'In pausa'}},
  en: {title: 'Print', printer: 'Printer', new: 'New print', recent: 'Recent prints', none: 'No prints yet',
       pick: 'Choose a file', pick_s: 'PDF, photos (JPG, PNG, HEIC) or text · up to 60 MB', change: 'Change',
       copies: 'Copies', mono: 'Black and white', mono_s: 'Uses black ink only', fit: 'Fit to page', fit_s: 'Shrinks the page if needed',
       pages: 'Pages', pages_s: 'Empty = all, e.g. 1-3,5', all: 'All', print: 'Print',
       sent: 'Sent to the printer', uploading: 'Uploading…', converting: 'Preparing the pages…',
       lost: 'Connection lost while uploading', weird: 'Unexpected answer', error: 'Error', cancel: 'Cancel',
       copy1: 'copy', copyN: 'copies', page1: 'page', pageN: 'pages', unknown: 'Printer', paper: 'Paper',
       ready: 'Ready', busy: 'Printing', stopped: 'Stopped', offline: 'Not reachable', offline_s: 'Prints stay queued and start when it is back',
       ink: {Black: 'Black', Color: 'Colour', Cyan: 'Cyan', Magenta: 'Magenta', Yellow: 'Yellow'},
       st: {conversione: 'Preparing', in_coda: 'Queued', invio: 'Sending', stampa: 'Printing', fatto: 'Printed', annullato: 'Canceled', errore: 'Error'},
       al: {'media-empty': 'Out of paper', 'media-needed': 'Out of paper', 'media-jam': 'Paper jam', 'toner-low': 'Toner low', 'toner-empty': 'Toner empty',
            'marker-supply-low': 'Ink low', 'marker-supply-empty': 'Ink empty', 'door-open': 'Door open', 'cover-open': 'Cover open', 'paused': 'Paused'}},
};

const CSS = `
:host { --sr-prim: #0c8a6c; --sr-ok: #0d9e80; --sr-warn: #c27a00; --sr-err: var(--error-color, #d23c3c);
  display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color);
  font-family: var(--paper-font-body1_-_font-family, inherit); -webkit-font-smoothing: antialiased; }
* { box-sizing: border-box; }
button { font: inherit; -webkit-tap-highlight-color: transparent; }
.bar { display: flex; align-items: center; gap: 4px; height: var(--header-height, 56px); padding: 0 4px 0 12px;
  background: var(--app-header-background-color); color: var(--app-header-text-color, #fff);
  border-bottom: var(--app-header-border-bottom, none); }
.bar button { display: none; width: 48px; height: 48px; margin-left: -8px; border: 0; background: none; color: inherit; border-radius: 50%; cursor: pointer; }
:host([narrow]) .bar button { display: inline-flex; align-items: center; justify-content: center; }
.bar .t { font-size: 20px; font-weight: 400; margin-left: 8px; }
.wrap { max-width: 640px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
ha-card { padding: 16px; }
h2 { margin: 0 0 12px; font-size: 18px; font-weight: 600; }
.sec { font-size: 14px; color: var(--secondary-text-color); }

.pr-head { display: flex; align-items: center; gap: 12px; }
.ico { flex: none; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  background: rgba(12, 138, 108, .12); color: var(--sr-prim); }
.pr-head .n { flex: 1; min-width: 0; }
.pr-head .n b { display: block; font-size: 16px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pill { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap;
  background: rgba(127, 127, 127, .14); color: var(--secondary-text-color); }
.pill.up { background: rgba(16, 161, 132, .15); color: var(--sr-ok); }
.pill.warn { background: rgba(230, 150, 20, .16); color: var(--sr-warn); }
.pill.down { background: rgba(220, 60, 60, .14); color: var(--sr-err); }
.inks { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 14px; }
.inks:empty { display: none; }
.ink { border: 1px solid var(--divider-color); border-radius: 12px; padding: 10px 12px; }
.ink .r { display: flex; justify-content: space-between; font-size: 13px; color: var(--secondary-text-color); }
.ink .r b { font-size: 14px; font-weight: 600; color: var(--primary-text-color); }
.ink .bar2 { height: 6px; border-radius: 3px; background: var(--divider-color); margin-top: 8px; overflow: hidden; }
.ink .bar2 i { display: block; height: 100%; border-radius: 3px; }
.alerts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.alerts:empty { display: none; }
.note { font-size: 13px; color: var(--secondary-text-color); margin: 10px 0 0; }
.note:empty { display: none; }

.drop { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 22px 16px; text-align: center; cursor: pointer;
  border: 1px dashed var(--divider-color); border-radius: 12px; color: var(--secondary-text-color); }
.drop:hover { border-color: var(--sr-prim); }
.drop ha-icon { --mdc-icon-size: 28px; color: var(--sr-prim); margin-bottom: 4px; }
.drop b { font-size: 15px; font-weight: 500; color: var(--primary-text-color); }
.drop span { font-size: 13px; }
.file { display: none; align-items: center; gap: 12px; padding: 10px 12px; border: 1px solid var(--divider-color); border-radius: 12px; }
.file ha-icon { color: var(--secondary-text-color); flex: none; }
.file .n { flex: 1; min-width: 0; }
.file .n b { display: block; font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file .n span { font-size: 12px; color: var(--secondary-text-color); }
.txt { border: 0; background: none; color: var(--sr-prim); font-weight: 500; font-size: 14px; padding: 8px; border-radius: 8px; cursor: pointer; }
.chosen .drop { display: none; } .chosen .file { display: flex; }
input[type=file] { display: none; }

.opts { margin-top: 8px; }
.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--divider-color); }
.row:last-child { border-bottom: 0; }
.row .l { font-size: 15px; } .row .l small { display: block; font-size: 13px; color: var(--secondary-text-color); margin-top: 1px; }
.step { display: inline-flex; align-items: center; border: 1px solid var(--divider-color); border-radius: 10px; padding: 3px; }
.step button { width: 34px; height: 30px; border: 0; background: none; color: var(--primary-text-color); font-size: 18px; border-radius: 8px; cursor: pointer; }
.step button:hover { background: rgba(127, 127, 127, .12); }
.step output { min-width: 28px; text-align: center; font-size: 15px; font-weight: 600; }
ha-switch { --primary-color: var(--sr-prim); --switch-checked-color: var(--sr-prim);
  --ha-switch-checked-background-color: rgba(12, 138, 108, .14); --ha-switch-checked-border-color: var(--sr-prim);
  --ha-switch-checked-thumb-background-color: var(--sr-prim); --ha-switch-checked-thumb-border-color: var(--sr-prim);
  --ha-switch-checked-thumb-background-color-hover: var(--sr-prim); --ha-switch-checked-thumb-border-color-hover: var(--sr-prim); }
.pg { width: 110px; height: 36px; padding: 0 10px; border: 1px solid var(--divider-color); border-radius: 10px; text-align: center;
  background: none; color: var(--primary-text-color); font: inherit; font-size: 14px; }
.pg:focus { outline: none; border-color: var(--sr-prim); }
.go { position: relative; overflow: hidden; width: 100%; height: 44px; margin-top: 12px; border: 0; border-radius: 10px; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 8px; background: var(--sr-prim); color: #fff; font-size: 15px; font-weight: 600; }
.go:disabled { opacity: .4; cursor: default; }
.go .p { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: rgba(255, 255, 255, .22); transition: width .2s; }
.go > *:not(.p) { position: relative; }
.msg { min-height: 18px; margin: 10px 0 0; font-size: 13px; text-align: center; color: var(--secondary-text-color); }
.msg.ok { color: var(--sr-ok); } .msg.ko { color: var(--sr-err); }

.job { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
.job:last-child { border-bottom: 0; padding-bottom: 0; } .job:first-child { padding-top: 0; }
.job > ha-icon { color: var(--secondary-text-color); flex: none; }
.job .n { flex: 1; min-width: 0; }
.job .n b { display: block; font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.job .n span { display: block; font-size: 12px; color: var(--secondary-text-color); }
.job .n em { display: block; font-size: 12px; font-style: normal; color: var(--sr-warn); margin-top: 1px; }
.x { flex: none; width: 32px; height: 32px; border: 0; background: none; color: var(--secondary-text-color); border-radius: 50%; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; }
.x:hover { background: rgba(127, 127, 127, .12); } .x ha-icon { --mdc-icon-size: 18px; }
.empty { font-size: 14px; color: var(--secondary-text-color); }
`;

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const iconFor = name => /\.pdf$/i.test(name) ? 'mdi:file-pdf-box' : /\.(jpe?g|png|gif|heic|heif|webp|tiff?|bmp)$/i.test(name) ? 'mdi:file-image-outline'
  : /\.(txt|md|csv|log)$/i.test(name) ? 'mdi:file-document-outline' : 'mdi:file-outline';
const PILL = {fatto: 'up', errore: 'down', annullato: '', in_coda: 'warn', conversione: 'warn', invio: 'warn', stampa: 'warn'};

class StampaRemotaPanel extends HTMLElement {
  set hass(h) { this._hass = h; if (!this._built) this._build(); }
  set narrow(n) { this.toggleAttribute('narrow', !!n); }

  connectedCallback() { if (this._hass && !this._built) this._build(); clearInterval(this._timer); this._timer = setInterval(() => this._load(), 3000); }
  disconnectedCallback() { clearInterval(this._timer); }

  _build() {
    this._built = true;
    const lang = (this._hass.language || navigator.language || 'en').slice(0, 2) === 'it' ? 'it' : 'en';
    const T = this._T = I18N[lang]; this._lang = lang;
    const r = this.attachShadow({mode: 'open'});
    r.innerHTML = `<style>${CSS}</style>
      <div class="bar"><button id="menu" aria-label="Menu"><ha-icon icon="mdi:menu"></ha-icon></button><span class="t">${T.title}</span></div>
      <div class="wrap">
        <ha-card>
          <div class="pr-head"><div class="ico"><ha-icon icon="mdi:printer-outline"></ha-icon></div>
            <div class="n"><b id="pname">${T.unknown}</b><span class="sec" id="pstate">…</span></div><span class="pill" id="ppill"></span></div>
          <div class="inks" id="inks"></div>
          <div class="alerts" id="alerts"></div>
          <p class="note" id="pnote"></p>
        </ha-card>
        <ha-card id="form">
          <h2>${T.new}</h2>
          <label class="drop" for="file"><ha-icon icon="mdi:tray-arrow-up"></ha-icon><b>${T.pick}</b><span>${T.pick_s}</span></label>
          <div class="file"><ha-icon id="ficon" icon="mdi:file-outline"></ha-icon><div class="n"><b id="fname"></b><span id="fsize"></span></div>
            <label class="txt" for="file">${T.change}</label></div>
          <input type="file" id="file">
          <div class="opts">
            <div class="row"><div class="l">${T.copies}</div><div class="step"><button type="button" id="meno" aria-label="-">−</button><output id="cp">1</output><button type="button" id="piu" aria-label="+">+</button></div></div>
            <div class="row" id="rmono"><div class="l">${T.mono}<small>${T.mono_s}</small></div><ha-switch id="bn"></ha-switch></div>
            <div class="row"><div class="l">${T.fit}<small>${T.fit_s}</small></div><ha-switch id="ad" checked></ha-switch></div>
            <div class="row"><div class="l">${T.pages}<small>${T.pages_s}</small></div><input class="pg" id="pg" inputmode="numeric" placeholder="${T.all}"></div>
          </div>
          <button class="go" id="vai" disabled><span class="p" id="pr"></span><ha-icon icon="mdi:printer"></ha-icon><span>${T.print}</span></button>
          <p class="msg" id="msg"></p>
        </ha-card>
        <ha-card><h2>${T.recent}</h2><div id="lista"><div class="empty">…</div></div></ha-card>
      </div>`;
    const $ = this._$ = id => r.getElementById(id);
    $('menu').onclick = () => this.dispatchEvent(new Event('hass-toggle-menu', {bubbles: true, composed: true}));
    // Android: a filtered picker can crash the HA app when coming back, so no "accept" there (the server checks the type)
    if (!/Android/i.test(navigator.userAgent)) $('file').setAttribute('accept', '.pdf,.txt,.heic,.heif,image/*,application/pdf,text/plain');
    this._copies = 1; this._chosen = null; this._monoSet = false;
    $('meno').onclick = () => { this._copies = Math.max(1, this._copies - 1); $('cp').textContent = this._copies; };
    $('piu').onclick = () => { this._copies = Math.min(50, this._copies + 1); $('cp').textContent = this._copies; };
    const kb = n => n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
    $('file').onchange = e => {
      const f = this._chosen = (e.target.files || [])[0] || null;
      $('form').classList.toggle('chosen', !!f);
      if (f) { $('fname').textContent = f.name; $('fsize').textContent = kb(f.size); $('ficon').setAttribute('icon', iconFor(f.name)); }
      $('vai').disabled = !f; this._msg('');
    };
    $('vai').onclick = () => this._print();
    $('lista').onclick = e => { const b = e.target.closest('[data-cancel]'); if (b) this._cancel(b.dataset.cancel); };
    this._load();
  }

  _msg(t, ok) { const m = this._$('msg'); m.textContent = t; m.className = 'msg' + (ok === true ? ' ok' : ok === false ? ' ko' : ''); }

  async _token() {
    const a = this._hass.auth;
    if (a.expired) await a.refreshAccessToken();
    return a.data.access_token;
  }

  async _print() {
    const $ = this._$, T = this._T;
    if (!this._chosen) return;
    const fd = new FormData();
    fd.append('copie', this._copies); fd.append('bianco_nero', $('bn').checked ? '1' : '0');
    fd.append('adatta', $('ad').checked ? '1' : '0'); fd.append('pagine', $('pg').value.trim());
    fd.append('file', this._chosen, this._chosen.name);
    const x = new XMLHttpRequest();
    x.open('POST', '/api/stampa_remota/stampa');
    x.setRequestHeader('Authorization', 'Bearer ' + await this._token());
    x.upload.onprogress = ev => { if (ev.lengthComputable) $('pr').style.width = (ev.loaded / ev.total * 100) + '%'; };
    x.upload.onload = () => this._msg(T.converting);
    x.onload = () => {
      $('pr').style.width = '0';
      let r; try { r = JSON.parse(x.responseText); } catch (e) { r = {ok: false, errore: T.weird + ' (' + x.status + ')'}; }
      if (r.ok) { $('file').value = ''; $('file').onchange({target: {files: []}}); this._msg(T.sent, true); }
      else { $('vai').disabled = false; this._msg(r.errore || T.error, false); }
      this._load();
    };
    x.onerror = () => { $('pr').style.width = '0'; $('vai').disabled = false; this._msg(T.lost, false); };
    $('vai').disabled = true; this._msg(T.uploading); x.send(fd);
  }

  async _cancel(id) {
    try { await this._hass.callApi('POST', 'stampa_remota/annulla', {id}); } catch (e) { /* refreshed below */ }
    this._load();
  }

  async _load() {
    if (!this._built || this._busy) return;
    this._busy = true;
    const $ = this._$, T = this._T;
    try {
      const r = await this._hass.callApi('GET', 'stampa_remota/stato');
      if (!this._monoSet) { $('bn').checked = !!r.bianco_nero_predefinito; this._monoSet = true; }
      $('rmono').style.display = r.colore === false ? 'none' : '';
      $('pname').textContent = r.stampante || T.unknown;
      const L = (r.lavori || []).slice(0, 8);
      const printing = L.some(j => j.stato === 'stampa' || j.stato === 'invio');
      const [st, cls] = !r.raggiungibile ? [T.offline, 'down'] : r.stato === 'stopped' ? [T.stopped, 'down']
        : (printing || r.stato === 'processing') ? [T.busy, 'warn'] : [T.ready, 'up'];
      $('pstate').textContent = r.carta ? `${T.paper} ${r.carta}` : '';
      $('ppill').textContent = st; $('ppill').className = 'pill ' + cls;
      $('pnote').textContent = r.raggiungibile ? '' : T.offline_s;
      $('inks').innerHTML = r.raggiungibile ? (r.inchiostri || []).filter(i => i.livello !== null && i.livello >= 0).map(i => {
        const low = i.livello < 15;
        const fill = low ? 'var(--sr-err)' : (/black/i.test(i.nome) ? 'var(--primary-text-color)' : 'var(--sr-prim)');
        return `<div class="ink"><div class="r"><span>${esc(T.ink[i.nome] || i.nome)}</span><b>${i.livello}%</b></div>
          <div class="bar2"><i style="width:${Math.max(2, Math.min(100, i.livello))}%;background:${fill}"></i></div></div>`;
      }).join('') : '';
      const al = r.raggiungibile ? [...new Set((r.avvisi || []).map(a => T.al[a.replace(/-(warning|error|report)$/, '')]).filter(Boolean))] : [];
      $('alerts').innerHTML = al.map(a => `<span class="pill warn">${esc(a)}</span>`).join('');
      $('lista').innerHTML = L.length ? L.map(j => {
        const when = new Date(j.ora * 1000).toLocaleString(this._lang, {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
        const pag = j.pagine ? ` · ${j.pagine} ${j.pagine > 1 ? T.pageN : T.page1}` : '';
        const act = ['in_coda', 'invio', 'stampa', 'conversione'].includes(j.stato);
        return `<div class="job"><ha-icon icon="${iconFor(j.nome)}"></ha-icon>
          <div class="n"><b>${esc(j.nome)}</b><span>${when} · ${j.copie} ${j.copie > 1 ? T.copyN : T.copy1}${pag}${j.utente ? ' · ' + esc(j.utente) : ''}</span>${j.errore ? `<em>${esc(j.errore)}</em>` : ''}</div>
          <span class="pill ${PILL[j.stato] ?? ''}">${T.st[j.stato] || esc(j.stato)}</span>
          ${act ? `<button class="x" data-cancel="${esc(j.id)}" aria-label="${T.cancel}" title="${T.cancel}"><ha-icon icon="mdi:close"></ha-icon></button>` : ''}</div>`;
      }).join('') : `<div class="empty">${T.none}</div>`;
    } catch (e) { /* HA restarting or offline: try again at the next round */ }
    this._busy = false;
  }
}
customElements.define('stampa-remota-panel', StampaRemotaPanel);
