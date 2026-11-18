// Stampa remota - pannello laterale di Home Assistant (web component, nessuna libreria).
// Grafica ripresa da "Remote Print" di Gapman1980 (MIT). Le chiamate passano dalle API autenticate di HA.
const I18N = {
  it: {title: 'Stampa da remoto', subtitle: 'Scegli un file: la stampante di casa lo stampa, anche se sei fuori.',
       pick: 'Tocca per scegliere il file', pick_s: 'PDF, foto (JPG, PNG, HEIC) o testo', change: 'tocca per cambiarlo',
       copies: 'Copie', mono: 'Bianco e nero', mono_s: 'risparmia l\'inchiostro a colori', fit: 'Adatta al foglio', fit_s: 'rimpicciolisce se serve',
       pages: 'Pagine', pages_s: 'vuoto = tutte · es. 1-3,5', all: 'tutte', print: '🖨️ STAMPA A CASA', recent: 'Ultime stampe', none: 'Nessuna stampa ancora',
       sent: '✓ Inviato! La stampante di casa sta per stamparlo', uploading: 'Caricamento…', converting: 'Preparo le pagine…',
       lost: '✗ Connessione persa durante il caricamento', weird: 'Risposta inattesa', error: 'Errore',
       copy1: 'copia', copyN: 'copie', page1: 'pagina', pageN: 'pagine', ink: 'Inchiostro', unreachable: 'Stampante non raggiungibile: stamperà appena si riaccende',
       st: {conversione: 'Preparo…', in_coda: 'In coda', invio: 'Invio…', stampa: 'Stampa…', fatto: 'Stampato ✓', annullato: 'Annullato', errore: 'Errore'},
       al: {'media-empty': 'Carta finita: aggiungi fogli', 'media-needed': 'Carta finita: aggiungi fogli', 'media-jam': 'Foglio inceppato',
            'toner-low': 'Toner in esaurimento', 'toner-empty': 'Toner finito', 'marker-supply-low': 'Inchiostro in esaurimento',
            'marker-supply-empty': 'Inchiostro finito', 'door-open': 'Sportello aperto', 'cover-open': 'Coperchio aperto',
            'offline': 'Stampante spenta o non raggiungibile', 'paused': 'Stampante in pausa'}},
  en: {title: 'Remote Print', subtitle: 'Pick a file: your home printer prints it, even when you are away.',
       pick: 'Tap to choose a file', pick_s: 'PDF, photos (JPG, PNG, HEIC) or text', change: 'tap to change it',
       copies: 'Copies', mono: 'Black and white', mono_s: 'saves colour ink', fit: 'Fit to page', fit_s: 'shrinks it if needed',
       pages: 'Pages', pages_s: 'empty = all · e.g. 1-3,5', all: 'all', print: '🖨️ PRINT AT HOME', recent: 'Recent prints', none: 'No prints yet',
       sent: '✓ Sent! Your home printer is about to print it', uploading: 'Uploading…', converting: 'Preparing the pages…',
       lost: '✗ Connection lost while uploading', weird: 'Unexpected answer', error: 'Error',
       copy1: 'copy', copyN: 'copies', page1: 'page', pageN: 'pages', ink: 'Ink', unreachable: 'Printer not reachable: it will print when it comes back',
       st: {conversione: 'Preparing…', in_coda: 'Queued', invio: 'Sending…', stampa: 'Printing…', fatto: 'Printed ✓', annullato: 'Canceled', errore: 'Error'},
       al: {'media-empty': 'Out of paper', 'media-needed': 'Out of paper', 'media-jam': 'Paper jam', 'toner-low': 'Toner low', 'toner-empty': 'Toner empty',
            'marker-supply-low': 'Ink low', 'marker-supply-empty': 'Ink empty', 'door-open': 'Door open', 'cover-open': 'Cover open',
            'offline': 'Printer off or unreachable', 'paused': 'Printer paused'}},
};

const CSS = `
:host { --a: #30D158; --b: #00CFFF; --bg: #0b0e1a; --t: #fff; --m: #8a94a8; display: block; min-height: 100vh;
  background: radial-gradient(120% 60% at 50% 0%, #1b2440 0%, var(--bg) 60%); color: var(--t);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
.bar { display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 8px; }
.bar button { width: 44px; height: 44px; border: none; background: none; color: #fff; border-radius: 50%; }
.bar button svg { width: 24px; height: 24px; } .bar span { font-size: 20px; font-weight: 700; }
.wrap { max-width: 560px; margin: 0 auto; padding: 4px 16px 40px; display: flex; flex-direction: column; gap: 14px; }
.box { border-radius: 20px; padding: 16px; background: linear-gradient(160deg, #161a2e, #0b0e1a);
       box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--a) 40%, transparent), 0 0 20px color-mix(in srgb, var(--a) 18%, transparent); }
.hd { display: flex; align-items: center; gap: 14px; }
.hd svg { width: 84px; height: 60px; flex: none; filter: drop-shadow(0 0 6px var(--a)); }
.hd b { display: block; font-size: 22px; } .hd span { color: var(--m); font-size: 13px; }
.co { fill: #24213a; stroke: var(--a); stroke-width: 1.6; } .fo { fill: #eef2f7; } .fe { fill: #05060c; }
.ri { stroke: #8a94a8; stroke-width: 1; } .led { fill: var(--a); animation: lamp 2s ease-in-out infinite; }
.usc { transform: translateY(-6px); } .lavora .usc { animation: esce 2s ease-in-out infinite; }
@keyframes esce { from { transform: translateY(-9px); } to { transform: translateY(3px); } }
@keyframes lamp { 50% { opacity: .3; } }
.ink { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; } .ink:empty { display: none; }
.ink div { flex: 1; min-width: 110px; font-size: 12px; color: var(--m); }
.ink i { display: block; height: 8px; border-radius: 4px; background: rgba(255,255,255,.12); margin-top: 4px; overflow: hidden; }
.ink i b { display: block; height: 100%; border-radius: 4px; }
.drop { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; min-height: 150px; border-radius: 18px;
        border: 2px dashed color-mix(in srgb, var(--b) 60%, transparent); background: color-mix(in srgb, var(--b) 7%, transparent);
        text-align: center; padding: 16px; cursor: pointer; transition: transform .15s; }
.drop:active { transform: scale(.98); }
.drop .ic { font-size: 40px; animation: su 2.2s ease-in-out infinite; } @keyframes su { 50% { transform: translateY(-5px); } }
.drop b { font-size: 18px; overflow-wrap: anywhere; } .drop span { color: var(--m); font-size: 13px; }
.drop.pieno { border-style: solid; border-color: var(--a); background: color-mix(in srgb, var(--a) 10%, transparent); }
input[type=file] { display: none; }
.riga { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 2px; border-bottom: 1px solid rgba(255,255,255,.07); }
.riga:last-child { border: none; } .riga label { font-size: 15px; font-weight: 600; } .riga small { display: block; color: var(--m); font-size: 12px; font-weight: 400; }
.step { display: flex; align-items: center; gap: 4px; }
.step button { width: 38px; height: 38px; border-radius: 12px; border: 1px solid rgba(255,255,255,.15); background: rgba(255,255,255,.06); color: #fff; font-size: 20px; font-weight: 700; }
.step output { min-width: 34px; text-align: center; font-size: 18px; font-weight: 800; }
.sw { position: relative; width: 52px; height: 30px; flex: none; }
.sw input { display: none; } .sw i { position: absolute; inset: 0; border-radius: 15px; background: rgba(255,255,255,.15); transition: .2s; }
.sw i::after { content: ''; position: absolute; left: 3px; top: 3px; width: 24px; height: 24px; border-radius: 50%; background: #fff; transition: .2s; }
.sw input:checked + i { background: var(--a); box-shadow: 0 0 10px var(--a); } .sw input:checked + i::after { left: 25px; }
.pg { width: 120px; padding: 9px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,.15); background: rgba(255,255,255,.06); color: #fff; font-size: 15px; text-align: center; }
.vai { position: relative; overflow: hidden; width: 100%; height: 64px; border: none; border-radius: 18px; font-size: 20px; font-weight: 900; letter-spacing: 1px; color: #04210f;
       background: linear-gradient(90deg, #30D158, #7CFFB0, #30D158); background-size: 200% 100%; animation: luce 3s linear infinite; box-shadow: 0 0 22px #30D15888; }
.vai:disabled { filter: grayscale(1) brightness(.6); animation: none; box-shadow: none; }
@keyframes luce { to { background-position: -200% 0; } }
.vai .pr { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: rgba(255,255,255,.35); transition: width .2s; }
.msg { min-height: 20px; text-align: center; font-size: 14px; font-weight: 700; }
.msg.ok { color: var(--a); } .msg.ko { color: #FF453A; }
.avv { display: none; padding: 10px 12px; border-radius: 14px; background: #FF9F0A22; border: 1px solid #FF9F0A; color: #FFD08A; font-size: 13px; font-weight: 700; }
h3 { margin: 4px 2px 0; font-size: 12px; letter-spacing: 1px; color: var(--m); text-transform: uppercase; }
.lv { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 14px; background: rgba(255,255,255,.04); box-shadow: inset 0 0 0 1px rgba(255,255,255,.07); }
.lv .n { flex: 1; min-width: 0; font-size: 14px; font-weight: 700; overflow-wrap: anywhere; } .lv .n small { display: block; color: var(--m); font-weight: 400; font-size: 12px; }
.lv .n em { display: block; color: #FFB340; font-style: normal; font-weight: 600; font-size: 12px; }
.pill { padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 800; white-space: nowrap; border: 1px solid; color: #FFD60A; border-color: #FFD60A; }
.p-stampa, .p-invio { color: var(--b); border-color: var(--b); animation: lamp 1s infinite; }
.p-fatto { color: var(--a); border-color: var(--a); } .p-annullato { color: var(--m); border-color: var(--m); } .p-errore { color: #FF453A; border-color: #FF453A; }
.x { border: none; background: #FF453A22; color: #FF6961; border-radius: 10px; padding: 6px 9px; font-weight: 800; font-size: 12px; }
.vuoto { color: var(--m); font-size: 13px; text-align: center; padding: 8px; }
`;

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

class StampaRemotaPanel extends HTMLElement {
  set hass(h) { this._hass = h; if (!this._built) this._build(); }
  set narrow(n) { this._narrow = n; if (this._bar) this._bar.style.display = n ? 'flex' : 'none'; }

  connectedCallback() { if (this._hass && !this._built) this._build(); this._timer = setInterval(() => this._load(), 3000); }
  disconnectedCallback() { clearInterval(this._timer); }

  _build() {
    this._built = true;
    const lang = (this._hass.language || navigator.language || 'en').slice(0, 2) === 'it' ? 'it' : 'en';
    const T = this._T = I18N[lang]; this._lang = lang;
    const r = this.attachShadow({mode: 'open'});
    r.innerHTML = `<style>${CSS}</style>
      <div class="bar" id="bar"><button id="menu" aria-label="menu"><svg viewBox="0 0 24 24"><path fill="currentColor" d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg></button><span>${T.title}</span></div>
      <div class="wrap">
        <div class="box"><div class="hd" id="hd">
          <svg viewBox="0 0 76 40"><rect class="fo" x="27" y="2" width="22" height="10" rx="1"/><rect class="co" x="19" y="10" width="38" height="17" rx="4"/>
            <rect class="fe" x="25" y="24" width="26" height="4" rx="1.5"/><g class="usc"><rect class="fo" x="27" y="25" width="22" height="9" rx="1"/>
            <path class="ri" d="M30 28 H46 M30 31 H42"/></g><circle class="led" cx="51" cy="15" r="1.6"/></svg>
          <div><b>${T.title}</b><span id="sub">${T.subtitle}</span></div></div>
          <div class="ink" id="ink"></div></div>
        <div class="avv" id="avv"></div>
        <label class="drop" id="drop" for="file"><div class="ic">📄</div><b id="dt">${T.pick}</b><span id="ds">${T.pick_s}</span></label>
        <input type="file" id="file">
        <div class="box" style="padding:6px 16px">
          <div class="riga"><label>${T.copies}</label><div class="step"><button type="button" id="meno">−</button><output id="cp">1</output><button type="button" id="piu">+</button></div></div>
          <div class="riga" id="rmono"><label><span>${T.mono}</span><small>${T.mono_s}</small></label><label class="sw"><input type="checkbox" id="bn"><i></i></label></div>
          <div class="riga"><label><span>${T.fit}</span><small>${T.fit_s}</small></label><label class="sw"><input type="checkbox" id="ad" checked><i></i></label></div>
          <div class="riga"><label><span>${T.pages}</span><small>${T.pages_s}</small></label><input class="pg" id="pg" inputmode="numeric" placeholder="${T.all}"></div>
        </div>
        <button class="vai" id="vai" disabled><span class="pr" id="pr"></span><span style="position:relative">${T.print}</span></button>
        <div class="msg" id="msg"></div>
        <h3>${T.recent}</h3>
        <div id="lista" style="display:flex;flex-direction:column;gap:8px"><div class="vuoto">…</div></div>
      </div>`;
    const $ = this._$ = id => r.getElementById(id);
    this._bar = $('bar'); this._bar.style.display = this._narrow ? 'flex' : 'none';
    $('menu').onclick = () => this.dispatchEvent(new Event('hass-toggle-menu', {bubbles: true, composed: true}));
    // Android: a filtered picker can crash the HA app when coming back, so no "accept" there (the server checks the type)
    if (!/Android/i.test(navigator.userAgent)) $('file').setAttribute('accept', '.pdf,.txt,.heic,.heif,image/*,application/pdf,text/plain');
    this._copies = 1; this._chosen = null; this._monoSet = false;
    $('meno').onclick = () => { this._copies = Math.max(1, this._copies - 1); $('cp').textContent = this._copies; };
    $('piu').onclick = () => { this._copies = Math.min(50, this._copies + 1); $('cp').textContent = this._copies; };
    const kb = n => n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
    $('file').onchange = e => {
      const f = this._chosen = (e.target.files || [])[0] || null;
      $('drop').classList.toggle('pieno', !!f);
      $('dt').textContent = f ? f.name : T.pick;
      $('ds').textContent = f ? kb(f.size) + ' · ' + T.change : T.pick_s;
      $('vai').disabled = !f; this._msg('', true);
    };
    $('vai').onclick = () => this._print();
    $('lista').onclick = e => { const b = e.target.closest('[data-cancel]'); if (b) this._cancel(b.dataset.cancel); };
    this._load();
  }

  _msg(t, ok) { const m = this._$('msg'); m.textContent = t; m.className = 'msg ' + (t ? (ok ? 'ok' : 'ko') : ''); }

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
    x.upload.onload = () => this._msg(T.converting, true);
    x.onload = () => {
      $('pr').style.width = '0'; $('vai').disabled = false;
      let r; try { r = JSON.parse(x.responseText); } catch (e) { r = {ok: false, errore: T.weird + ' (' + x.status + ')'}; }
      if (r.ok) { $('file').value = ''; $('file').onchange({target: {files: []}}); this._msg(T.sent, true); }
      else this._msg('✗ ' + (r.errore || T.error), false);
      this._load();
    };
    x.onerror = () => { $('pr').style.width = '0'; $('vai').disabled = false; this._msg(T.lost, false); };
    $('vai').disabled = true; this._msg(T.uploading, true); x.send(fd);
  }

  async _cancel(id) {
    try { await this._hass.callApi('POST', 'stampa_remota/annulla', {id}); } catch (e) {}
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
      const L = r.lavori || [];
      $('lista').innerHTML = L.length ? L.map(j => {
        const when = new Date(j.ora * 1000).toLocaleString(this._lang, {weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
        const pag = j.pagine ? ` · ${j.pagine} ${j.pagine > 1 ? T.pageN : T.page1}` : '';
        const act = ['in_coda', 'invio', 'stampa', 'conversione'].includes(j.stato);
        return `<div class="lv"><div class="n">${esc(j.nome)}<small>${when} · ${j.copie} ${j.copie > 1 ? T.copyN : T.copy1}${pag}${j.utente ? ' · ' + esc(j.utente) : ''}</small>${j.errore ? `<em>${esc(j.errore)}</em>` : ''}</div>
          <span class="pill p-${j.stato}">${T.st[j.stato] || esc(j.stato)}</span>${act ? `<button class="x" data-cancel="${esc(j.id)}">✕</button>` : ''}</div>`;
      }).join('') : `<div class="vuoto">${T.none}</div>`;
      const al = r.raggiungibile ? (r.avvisi || []).map(a => T.al[a.replace(/-(warning|error|report)$/, '')]).filter(Boolean) : [T.unreachable];
      $('avv').style.display = al.length ? 'block' : 'none'; $('avv').textContent = '⚠️ ' + [...new Set(al)].join(' · ');
      $('ink').innerHTML = (r.inchiostri || []).filter(i => i.livello !== null && i.livello >= 0).map(i =>
        `<div>${T.ink} ${esc(i.nome)} · ${i.livello}%<i><b style="width:${Math.max(2, i.livello)}%;background:${(c => /^#0{6}$/.test(c) ? '#d0d4dc' : c)(((i.colore || '').match(/#[0-9a-f]{6}/i) || ['#8a94a8'])[0])};${i.livello < 15 ? 'box-shadow:0 0 0 1px #FF453A' : ''}"></b></i></div>`).join('');
      if (r.stampante) $('sub').textContent = r.stampante + ' · ' + T.subtitle;
      $('hd').classList.toggle('lavora', L.some(j => j.stato === 'stampa' || j.stato === 'invio'));
    } catch (e) { /* HA restarting or offline: try again at the next round */ }
    this._busy = false;
  }
}
customElements.define('stampa-remota-panel', StampaRemotaPanel);
