// Stampa remota - pannello laterale di Home Assistant (web component, nessuna libreria).
// Stile sobrio: elementi e colori del tema di HA (ha-card, ha-icon, ha-switch), accento verde come le plance di casa.
// Funzioni riprese da Remote Print di Gapman1980 (MIT): anteprima con scala e posizione, più stampanti, cestino.
const I18N = {
  it: {title: 'Stampa', new: 'Nuova stampa', recent: 'Ultime stampe', none: 'Nessuna stampa ancora',
       pick: 'Scegli un file', pick_s: 'PDF, foto (JPG, PNG, HEIC) o testo · massimo 60 MB', change: 'Cambia',
       copies: 'Copie', mono: 'Bianco e nero', mono_s: 'Usa solo l\'inchiostro nero', fit: 'Adatta al foglio', fit_s: 'Rimpicciolisce la pagina se serve',
       pages: 'Pagine', pages_s: 'Vuoto = tutte, es. 1-3,5', all: 'Tutte', print: 'Stampa',
       sent: 'Inviato alla stampante', uploading: 'Caricamento…', converting: 'Preparazione delle pagine…',
       lost: 'Connessione persa durante il caricamento', weird: 'Risposta inattesa', error: 'Errore', cancel: 'Annulla',
       remove: 'Togli dall\'elenco', clear: 'Svuota', sure: 'Tocca ancora per svuotare',
       copy1: 'copia', copyN: 'copie', page1: 'pagina', pageN: 'pagine', unknown: 'Stampante', paper: 'Carta',
       ready: 'Pronta', busy: 'In stampa', stopped: 'Ferma', offline: 'Non raggiungibile',
       offline_s: 'Le stampe restano in coda e partono quando torna disponibile.',
       prev: 'Anteprima e posizione', prev_close: 'Chiudi anteprima', prep: 'Preparazione dell\'anteprima…',
       port: 'Verticale', land: 'Orizzontale', scale: 'Scala', fitb: 'Adatta', center: 'Centra',
       drag: 'Trascina la pagina per spostarla · il tratteggio è il limite di stampa', allp: 'Le regolazioni valgono per tutte le pagine',
       page: 'Pagina', laid: 'con anteprima',
       ink: {Black: 'Nero', Color: 'Colore', Cyan: 'Ciano', Magenta: 'Magenta', Yellow: 'Giallo'},
       st: {conversione: 'Preparazione', in_coda: 'In coda', invio: 'Invio', stampa: 'In stampa', fatto: 'Stampato', annullato: 'Annullato', errore: 'Errore'}},
  en: {title: 'Print', new: 'New print', recent: 'Recent prints', none: 'No prints yet',
       pick: 'Choose a file', pick_s: 'PDF, photos (JPG, PNG, HEIC) or text · up to 60 MB', change: 'Change',
       copies: 'Copies', mono: 'Black and white', mono_s: 'Uses black ink only', fit: 'Fit to page', fit_s: 'Shrinks the page if needed',
       pages: 'Pages', pages_s: 'Empty = all, e.g. 1-3,5', all: 'All', print: 'Print',
       sent: 'Sent to the printer', uploading: 'Uploading…', converting: 'Preparing the pages…',
       lost: 'Connection lost while uploading', weird: 'Unexpected answer', error: 'Error', cancel: 'Cancel',
       remove: 'Remove from the list', clear: 'Clear', sure: 'Tap again to clear',
       copy1: 'copy', copyN: 'copies', page1: 'page', pageN: 'pages', unknown: 'Printer', paper: 'Paper',
       ready: 'Ready', busy: 'Printing', stopped: 'Stopped', offline: 'Not reachable',
       offline_s: 'Prints stay queued and start when it is back.',
       prev: 'Preview and position', prev_close: 'Close preview', prep: 'Preparing the preview…',
       port: 'Portrait', land: 'Landscape', scale: 'Scale', fitb: 'Fit', center: 'Center',
       drag: 'Drag the page to move it · the dashed line is the printable limit', allp: 'Adjustments apply to all pages',
       page: 'Page', laid: 'with preview',
       ink: {Black: 'Black', Color: 'Colour', Cyan: 'Cyan', Magenta: 'Magenta', Yellow: 'Yellow'},
       st: {conversione: 'Preparing', in_coda: 'Queued', invio: 'Sending', stampa: 'Printing', fatto: 'Printed', annullato: 'Canceled', errore: 'Error'}},
};

const CSS = `
:host { --sr-prim: #0c8a6c; --sr-ok: #0d9e80; --sr-warn: #c27a00; --sr-err: var(--error-color, #d23c3c);
  display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color);
  -webkit-font-smoothing: antialiased; }
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
h2 { margin: 0; font-size: 18px; font-weight: 600; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; min-height: 34px; }
.sec { font-size: 14px; color: var(--secondary-text-color); }

.seg { display: inline-flex; flex-wrap: wrap; border: 1px solid var(--divider-color); border-radius: 10px; padding: 3px; gap: 2px; }
.seg button { border: 0; background: transparent; color: var(--secondary-text-color); font-size: 14px; font-weight: 500;
  padding: 7px 12px; border-radius: 8px; cursor: pointer; min-height: 34px; }
.seg button[aria-pressed=true] { background: var(--sr-prim); color: #fff; }
.psel { margin-bottom: 14px; } .psel:empty { display: none; }

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
.txt:hover { background: rgba(12, 138, 108, .08); }
.txt.sure { color: var(--sr-err); }
.chosen .drop { display: none; } .chosen .file { display: flex; }
input[type=file] { display: none; }
.prevbtn { display: none; width: 100%; margin-top: 8px; height: 40px; border: 1px solid var(--divider-color); border-radius: 10px; background: none;
  color: var(--primary-text-color); font-size: 14px; font-weight: 500; cursor: pointer; align-items: center; justify-content: center; gap: 8px; }
.prevbtn ha-icon { --mdc-icon-size: 20px; color: var(--sr-prim); }
.chosen .prevbtn { display: flex; }

.ed { display: none; margin-top: 12px; padding: 12px; border: 1px solid var(--divider-color); border-radius: 12px; }
.edit .ed { display: block; }
.edit .rfit { display: none; }
.ed .tools { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.stage { display: flex; justify-content: center; margin: 14px 0; }
.sheet { position: relative; overflow: hidden; background: #fff; touch-action: none; cursor: grab; border-radius: 2px;
  box-shadow: 0 0 0 1px var(--divider-color), 0 1px 4px rgba(0, 0, 0, .12); }
.sheet.drag { cursor: grabbing; }
.sheet img { position: absolute; max-width: none; pointer-events: none; user-select: none; -webkit-user-drag: none; }
.sheet .mg { position: absolute; border: 1px dashed rgba(210, 60, 60, .7); pointer-events: none; z-index: 1; }
.sheet .wait { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 12px; text-align: center;
  color: #8a8f98; font-size: 13px; pointer-events: none; }
.sheet .wait:empty { display: none; }
.sl { display: flex; align-items: center; gap: 10px; }
.sl span { font-size: 14px; } .sl output { min-width: 48px; text-align: right; font-size: 14px; font-weight: 600; }
.sl input { flex: 1; accent-color: var(--sr-prim); }
.btns { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.btns button, .nav button { height: 34px; padding: 0 12px; border: 1px solid var(--divider-color); border-radius: 10px; background: none;
  color: var(--primary-text-color); font-size: 14px; cursor: pointer; }
.nav { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--secondary-text-color); }
.nav button { width: 34px; padding: 0; } .nav button:disabled { opacity: .35; cursor: default; }
.hint { font-size: 12px; color: var(--secondary-text-color); margin: 8px 0 0; }

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
.job .n em.grave { color: var(--sr-err); font-weight: 600; }
.x { flex: none; width: 32px; height: 32px; border: 0; background: none; color: var(--secondary-text-color); border-radius: 50%; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; }
.x:hover { background: rgba(127, 127, 127, .12); } .x ha-icon { --mdc-icon-size: 18px; }
.empty { font-size: 14px; color: var(--secondary-text-color); }
`;

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const iconFor = name => /\.pdf$/i.test(name) ? 'mdi:file-pdf-box' : /\.(jpe?g|png|gif|heic|heif|webp|tiff?|bmp)$/i.test(name) ? 'mdi:file-image-outline'
  : /\.(txt|md|csv|log)$/i.test(name) ? 'mdi:file-document-outline' : 'mdi:file-outline';
const PILL = {fatto: 'up', errore: 'down', annullato: '', in_coda: 'warn', conversione: 'warn', invio: 'warn', stampa: 'warn'};
const ACTIVE = ['in_coda', 'invio', 'stampa', 'conversione'];
const OLD_ALERTS = {'media-empty': 'Carta finita', 'media-needed': 'Carta finita', 'media-jam': 'Foglio inceppato', 'door-open': 'Sportello aperto',
  'cover-open': 'Coperchio aperto', 'marker-supply-low': 'Inchiostro in esaurimento', 'marker-supply-empty': 'Inchiostro finito',
  'toner-low': 'Toner in esaurimento', 'toner-empty': 'Toner finito'};
const store = {get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
               set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }};

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
          <div class="psel seg" id="psel" role="group"></div>
          <div class="pr-head"><div class="ico"><ha-icon icon="mdi:printer-outline"></ha-icon></div>
            <div class="n"><b id="pname">${T.unknown}</b><span class="sec" id="pstate">…</span></div><span class="pill" id="ppill"></span></div>
          <div class="inks" id="inks"></div>
          <div class="alerts" id="alerts"></div>
          <p class="note" id="pnote"></p>
        </ha-card>
        <ha-card id="form">
          <div class="head"><h2>${T.new}</h2></div>
          <label class="drop" for="file"><ha-icon icon="mdi:tray-arrow-up"></ha-icon><b>${T.pick}</b><span>${T.pick_s}</span></label>
          <div class="file"><ha-icon id="ficon" icon="mdi:file-outline"></ha-icon><div class="n"><b id="fname"></b><span id="fsize"></span></div>
            <label class="txt" for="file">${T.change}</label></div>
          <input type="file" id="file">
          <button type="button" class="prevbtn" id="prevbtn"><ha-icon icon="mdi:file-eye-outline"></ha-icon><span id="prevlbl">${T.prev}</span></button>
          <div class="ed" id="ed">
            <div class="tools">
              <div class="seg" role="group"><button type="button" data-o="p">${T.port}</button><button type="button" data-o="l">${T.land}</button></div>
              <div class="nav" id="pnav"><button type="button" id="pp" aria-label="‹">‹</button><span id="pn"></span><button type="button" id="pnx" aria-label="›">›</button></div>
            </div>
            <div class="stage" id="stage"><div class="sheet" id="sheet"><img id="pimg" alt=""><div class="mg" id="mg"></div><div class="wait" id="wait"></div></div></div>
            <div class="sl"><span>${T.scale}</span><input type="range" id="sc" min="5" max="300" step="1"><output id="sco"></output></div>
            <div class="btns"><button type="button" id="bfit">${T.fitb}</button><button type="button" id="bcen">${T.center}</button><button type="button" id="b100">100%</button></div>
            <p class="hint" id="hint"></p>
          </div>
          <div class="opts">
            <div class="row"><div class="l">${T.copies}</div><div class="step"><button type="button" id="meno" aria-label="-">−</button><output id="cp">1</output><button type="button" id="piu" aria-label="+">+</button></div></div>
            <div class="row" id="rmono"><div class="l">${T.mono}<small>${T.mono_s}</small></div><ha-switch id="bn"></ha-switch></div>
            <div class="row rfit"><div class="l">${T.fit}<small>${T.fit_s}</small></div><ha-switch id="ad" checked></ha-switch></div>
            <div class="row"><div class="l">${T.pages}<small>${T.pages_s}</small></div><input class="pg" id="pg" inputmode="numeric" placeholder="${T.all}"></div>
          </div>
          <button class="go" id="vai" disabled><span class="p" id="pr"></span><ha-icon icon="mdi:printer"></ha-icon><span>${T.print}</span></button>
          <p class="msg" id="msg"></p>
        </ha-card>
        <ha-card><div class="head"><h2>${T.recent}</h2><button type="button" class="txt" id="clear">${T.clear}</button></div><div id="lista"><div class="empty">…</div></div></ha-card>
      </div>`;
    const $ = this._$ = id => r.getElementById(id);
    $('menu').onclick = () => this.dispatchEvent(new Event('hass-toggle-menu', {bubbles: true, composed: true}));
    // Android: a filtered picker can crash the HA app when coming back, so no "accept" there (the server checks the type)
    if (!/Android/i.test(navigator.userAgent)) $('file').setAttribute('accept', '.pdf,.txt,.heic,.heif,image/*,application/pdf,text/plain');
    this._copies = 1; this._chosen = null; this._monoFor = null; this._sel = store.get('stampa_remota_stampante');
    $('meno').onclick = () => { this._copies = Math.max(1, this._copies - 1); $('cp').textContent = this._copies; };
    $('piu').onclick = () => { this._copies = Math.min(50, this._copies + 1); $('cp').textContent = this._copies; };
    const kb = n => n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
    $('file').onchange = e => {
      const f = this._chosen = (e.target.files || [])[0] || null;
      $('form').classList.toggle('chosen', !!f);
      if (f) { $('fname').textContent = f.name; $('fsize').textContent = kb(f.size); $('ficon').setAttribute('icon', iconFor(f.name)); }
      this._closeEd(); this._P = null;
      $('vai').disabled = !f; this._msg('');
    };
    $('vai').onclick = () => this._print();
    $('prevbtn').onclick = () => (this._edOpen ? this._closeEd() : this._openEd());
    $('lista').onclick = e => {
      const c = e.target.closest('[data-cancel]'); if (c) return this._post('annulla', {id: c.dataset.cancel});
      const t = e.target.closest('[data-forget]'); if (t) return this._post('togli', {id: t.dataset.forget});
      return null;
    };
    $('clear').onclick = () => {   // two taps: the first one asks
      const b = $('clear');
      if (!b.classList.contains('sure')) {
        b.classList.add('sure'); b.textContent = T.sure; clearTimeout(this._sureT);
        this._sureT = setTimeout(() => { b.classList.remove('sure'); b.textContent = T.clear; }, 3000);
        return;
      }
      b.classList.remove('sure'); b.textContent = T.clear; this._post('svuota', {});
    };
    this._initEditor();
    this._load();
  }

  _msg(t, ok) { const m = this._$('msg'); m.textContent = t; m.className = 'msg' + (ok === true ? ' ok' : ok === false ? ' ko' : ''); }

  async _token() {
    const a = this._hass.auth;
    if (a.expired) await a.refreshAccessToken();
    return a.data.access_token;
  }

  _printer() { const L = this._printers || []; return L.find(p => p.id === this._sel) || L[0] || null; }

  // ---------------------------------------------------------------- preview and position
  _initEditor() {
    const $ = this._$;
    this.shadowRoot.querySelectorAll('[data-o]').forEach(b => b.onclick = () => { this._L.o = b.dataset.o; this._fitLayout(); });
    $('sc').oninput = e => { this._L.s = e.target.value / 100; this._draw(); };
    $('bfit').onclick = () => this._fitLayout();
    $('bcen').onclick = () => { this._L.dx = 0; this._L.dy = 0; this._draw(); };
    $('b100').onclick = () => { this._L.s = 1; this._draw(); };
    $('pp').onclick = () => { this._pg = Math.max(0, this._pg - 1); this._draw(true); };
    $('pnx').onclick = () => { this._pg = Math.min(this._P.pagine - 1, this._pg + 1); this._draw(true); };
    const sh = $('sheet');
    let st = null;
    sh.addEventListener('pointerdown', e => {
      if (!this._P) return;
      st = {x: e.clientX, y: e.clientY, dx: this._L.dx, dy: this._L.dy};
      sh.setPointerCapture(e.pointerId); sh.classList.add('drag');
    });
    sh.addEventListener('pointermove', e => {
      if (!st) return;
      this._L.dx = st.dx + (e.clientX - st.x) / this._K; this._L.dy = st.dy - (e.clientY - st.y) / this._K; this._draw();
    });
    const end = () => { st = null; sh.classList.remove('drag'); };
    sh.addEventListener('pointerup', end); sh.addEventListener('pointercancel', end);
    this._thumbs = {};
  }

  _sheetPt() { const p = this._printer(); const [w, h] = p ? p.foglio_pt : [595.28, 841.89]; return this._L.o === 'l' ? [h, w] : [w, h]; }
  _margin() { return (this._printer() || {}).margine_pt || 12; }

  _fitLayout() {   // page fitted inside the printable area, centred
    const [W, H] = this._sheetPt(), [w, h] = this._P.misure[this._pg], m = this._margin();
    Object.assign(this._L, {s: Math.min((W - 2 * m) / w, (H - 2 * m) / h), dx: 0, dy: 0});
    this._draw();
  }

  async _openEd() {
    const $ = this._$, T = this._T;
    if (!this._chosen) return;
    this._edOpen = true; $('form').classList.add('edit'); $('prevlbl').textContent = T.prev_close;
    if (this._P) { this._draw(true); return; }
    $('wait').textContent = T.prep; $('pimg').removeAttribute('src');
    const p = this._printer(), [W, H] = p ? p.foglio_pt : [595.28, 841.89];
    $('sheet').style.width = '240px'; $('sheet').style.height = 240 * H / W + 'px';
    const fd = new FormData(); fd.append('file', this._chosen, this._chosen.name);
    if (p) fd.append('stampante', p.id);
    try {
      const res = await fetch('/api/stampa_remota/prepara', {method: 'POST', body: fd, headers: {Authorization: 'Bearer ' + await this._token()}});
      const r = await res.json();
      if (!r.ok) { this._closeEd(); this._msg(r.errore || T.error, false); return; }
      this._P = r; this._pg = 0; this._thumbs = {}; this._have = 0;
      const [w, h] = r.misure[0], m = this._margin();
      const o = w > h ? 'l' : 'p', SW = o === 'l' ? H : W, SH = o === 'l' ? W : H;
      this._L = {o, s: $('ad').checked ? Math.min((SW - 2 * m) / w, (SH - 2 * m) / h) : Math.min(1, SW / w, SH / h), dx: 0, dy: 0};
      $('wait').textContent = '';
      this._draw(true);
    } catch (e) { this._closeEd(); this._msg(T.lost, false); }
  }

  _closeEd() { const $ = this._$; this._edOpen = false; $('form').classList.remove('edit'); $('prevlbl').textContent = this._T.prev; }

  _thumb(page, width) {
    const key = page + ':' + width;
    if (!this._thumbs[key]) {
      this._thumbs[key] = (async () => {
        const res = await fetch(`/api/stampa_remota/anteprima?token=${encodeURIComponent(this._P.token)}&pagina=${page + 1}&w=${width}`,
                                {headers: {Authorization: 'Bearer ' + await this._token()}});
        if (!res.ok) throw new Error(String(res.status));
        return URL.createObjectURL(await res.blob());
      })();
    }
    return this._thumbs[key];
  }

  _draw(newPage) {
    const $ = this._$, T = this._T, L = this._L, P = this._P;
    if (!P || !L) return;
    const [W, H] = this._sheetPt(), [w, h] = P.misure[this._pg], m = this._margin();
    const maxW = W > H ? 420 : 300;
    const boxW = Math.min($('stage').clientWidth || maxW, maxW);
    const K = this._K = boxW / W, sh = $('sheet');
    sh.style.width = W * K + 'px'; sh.style.height = H * K + 'px';
    Object.assign($('mg').style, {left: m * K + 'px', top: m * K + 'px', right: m * K + 'px', bottom: m * K + 'px'});
    const img = $('pimg'), pw = L.s * w * K, ph = L.s * h * K;
    Object.assign(img.style, {width: pw + 'px', height: ph + 'px',
      left: (W / 2 + L.dx - L.s * w / 2) * K + 'px', top: (H / 2 - L.dy - L.s * h / 2) * K + 'px'});
    // picture resolution in steps, so zooming does not ask for a new one at every pixel
    const want = Math.min(1600, Math.max(200, Math.ceil(pw * (window.devicePixelRatio || 1) / 200) * 200));
    if (newPage || want > (this._have || 0) * 1.4 || this._havePg !== this._pg) {
      this._have = want; this._havePg = this._pg;
      const pg = this._pg;
      this._thumb(pg, want).then(u => { if (this._pg === pg) img.src = u; }).catch(() => { /* expired: next print re-uploads */ });
    }
    this.shadowRoot.querySelectorAll('[data-o]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.o === L.o)));
    $('sc').value = Math.round(L.s * 100); $('sco').textContent = Math.round(L.s * 100) + '%';
    $('pnav').style.display = P.pagine > 1 ? '' : 'none';
    $('pn').textContent = `${T.page} ${this._pg + 1}/${P.pagine}`;
    $('pp').disabled = this._pg === 0; $('pnx').disabled = this._pg >= P.pagine - 1;
    $('hint').textContent = T.drag + (P.pagine > 1 ? ' · ' + T.allp : '');
  }

  // ---------------------------------------------------------------- print and list
  async _print() {
    const $ = this._$, T = this._T;
    if (!this._chosen) return;
    const fd = new FormData();
    fd.append('copie', this._copies); fd.append('bianco_nero', $('bn').checked ? '1' : '0');
    fd.append('adatta', $('ad').checked ? '1' : '0'); fd.append('pagine', $('pg').value.trim());
    if (this._printer()) fd.append('stampante', this._printer().id);
    const withLayout = this._edOpen && this._P;
    if (withLayout) { fd.append('token', this._P.token); fd.append('layout', JSON.stringify(this._L)); }   // already uploaded
    else fd.append('file', this._chosen, this._chosen.name);
    const x = new XMLHttpRequest();
    x.open('POST', '/api/stampa_remota/stampa');
    x.setRequestHeader('Authorization', 'Bearer ' + await this._token());
    x.upload.onprogress = ev => { if (ev.lengthComputable && !withLayout) $('pr').style.width = (ev.loaded / ev.total * 100) + '%'; };
    x.upload.onload = () => this._msg(T.converting);
    x.onload = () => {
      $('pr').style.width = '0';
      let r; try { r = JSON.parse(x.responseText); } catch (e) { r = {ok: false, errore: T.weird + ' (' + x.status + ')'}; }
      if (r.ok) { $('file').value = ''; $('file').onchange({target: {files: []}}); $('pg').value = ''; this._msg(T.sent, true); }
      else { $('vai').disabled = false; this._msg(r.errore || T.error, false); }
      this._load();
    };
    x.onerror = () => { $('pr').style.width = '0'; $('vai').disabled = false; this._msg(T.lost, false); };
    $('vai').disabled = true; this._msg(withLayout ? T.converting : T.uploading); x.send(fd);
  }

  async _post(path, body) {
    try { await this._hass.callApi('POST', 'stampa_remota/' + path, body); } catch (e) { /* refreshed below */ }
    this._load();
  }

  _renderPrinter() {
    const $ = this._$, T = this._T, p = this._printer(), L = this._jobs || [];
    const many = (this._printers || []).length > 1;
    $('psel').innerHTML = many ? this._printers.map(x =>
      `<button type="button" data-p="${esc(x.id)}" aria-pressed="${x.id === (p && p.id)}">${esc(x.nome)}</button>`).join('') : '';
    $('psel').querySelectorAll('[data-p]').forEach(b => b.onclick = () => {
      this._sel = b.dataset.p; store.set('stampa_remota_stampante', this._sel);
      this._P = null; this._closeEd(); this._renderPrinter();
    });
    if (!p) return;
    if (this._monoFor !== p.id) { $('bn').checked = !!p.bianco_nero_predefinito; this._monoFor = p.id; }
    $('rmono').style.display = p.colore === false ? 'none' : '';
    $('pname').textContent = p.nome || p.modello || T.unknown;
    const printing = L.some(j => (j.stato === 'stampa' || j.stato === 'invio') && j.stampante === p.nome);
    const grave = (p.avvisi || []).some(a => a.grave);
    const [st, cls] = !p.raggiungibile ? [T.offline, 'down'] : (p.stato === 'stopped' || grave) ? [T.stopped, 'down']
      : (printing || p.stato === 'processing') ? [T.busy, 'warn'] : [T.ready, 'up'];
    $('pstate').textContent = [p.nome && p.modello && p.nome !== p.modello ? p.modello : '', p.carta ? `${T.paper} ${p.carta}` : '']
      .filter(Boolean).join(' · ');
    $('ppill').textContent = st; $('ppill').className = 'pill ' + cls;
    $('pnote').textContent = p.raggiungibile ? '' : (p.errore ? p.errore.charAt(0).toUpperCase() + p.errore.slice(1) + '. ' : '') + T.offline_s;
    $('inks').innerHTML = p.raggiungibile ? (p.inchiostri || []).filter(i => i.livello !== null && i.livello >= 0).map(i => {
      const low = i.livello < 15;
      const fill = low ? 'var(--sr-err)' : (/black/i.test(i.nome) ? 'var(--primary-text-color)' : 'var(--sr-prim)');
      return `<div class="ink"><div class="r"><span>${esc(T.ink[i.nome] || i.nome)}</span><b>${i.livello}%</b></div>
        <div class="bar2"><i style="width:${Math.max(2, Math.min(100, i.livello))}%;background:${fill}"></i></div></div>`;
    }).join('') : '';
    $('alerts').innerHTML = (p.avvisi || []).map(a => `<span class="pill ${a.grave ? 'down' : 'warn'}">${esc(a.testo)}</span>`).join('');
  }

  async _load() {
    if (!this._built || this._busy) return;
    this._busy = true;
    const $ = this._$, T = this._T;
    try {
      const r = await this._hass.callApi('GET', 'stampa_remota/stato');
      // answer of a version < 1.2.0 still running until Home Assistant restarts: one printer, alerts as codes
      this._printers = r.stampanti || [{id: '', nome: r.stampante, modello: r.stampante, raggiungibile: r.raggiungibile,
        errore: r.errore, stato: r.stato, inchiostri: r.inchiostri, colore: r.colore, carta: r.carta,
        foglio_pt: [595.28, 841.89], margine_pt: 12, bianco_nero_predefinito: r.bianco_nero_predefinito, vecchia: true,
        avvisi: (r.avvisi || []).map(a => ({testo: OLD_ALERTS[a.replace(/-(warning|error|report)$/, '')], grave: /-error$/.test(a)}))
          .filter(a => a.testo)}];
      $('prevbtn').style.visibility = this._printers[0] && this._printers[0].vecchia ? 'hidden' : '';
      const L = this._jobs = (r.lavori || []).slice(0, 10);
      this._renderPrinter();
      const many = this._printers.length > 1;
      $('clear').style.display = L.some(j => !ACTIVE.includes(j.stato)) ? '' : 'none';
      $('lista').innerHTML = L.length ? L.map(j => {
        const when = new Date(j.ora * 1000).toLocaleString(this._lang, {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
        const pag = j.pagine ? ` · ${j.pagine} ${j.pagine > 1 ? T.pageN : T.page1}` : '';
        const act = ACTIVE.includes(j.stato);
        const meta = [when, `${j.copie} ${j.copie > 1 ? T.copyN : T.copy1}${pag}`, many ? j.stampante : '', j.utente, j.anteprima ? T.laid : '']
          .filter(Boolean).map(esc).join(' · ');
        const note = j.avviso ? `<em class="grave">${esc(j.avviso)}</em>` : j.errore ? `<em>${esc(j.errore)}</em>` : '';
        const btn = act
          ? `<button class="x" data-cancel="${esc(j.id)}" aria-label="${T.cancel}" title="${T.cancel}"><ha-icon icon="mdi:close"></ha-icon></button>`
          : `<button class="x" data-forget="${esc(j.id)}" aria-label="${T.remove}" title="${T.remove}"><ha-icon icon="mdi:delete-outline"></ha-icon></button>`;
        return `<div class="job"><ha-icon icon="${iconFor(j.nome)}"></ha-icon>
          <div class="n"><b>${esc(j.nome)}</b><span>${meta}</span>${note}</div>
          <span class="pill ${PILL[j.stato] ?? ''}">${T.st[j.stato] || esc(j.stato)}</span>${btn}</div>`;
      }).join('') : `<div class="empty">${T.none}</div>`;
    } catch (e) { /* HA restarting or offline: try again at the next round */ }
    this._busy = false;
  }
}
customElements.define('stampa-remota-panel', StampaRemotaPanel);
