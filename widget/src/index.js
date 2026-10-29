// cpbot-widget: framework-agnostic floating chat launcher.
// Renders a chat icon in a shadow root and, on click, opens an iframe onto
// cpbot's chat-only route, handing it the host site's signed JWT.

const DEFAULTS = {
  apiUrl: 'https://cpbot-staging.onrender.com',
  chatUrl: 'https://cpbot-frontend.onrender.com/widget-chat',
  position: 'bottom-right',
  color: null,
  offset: 20,
  zIndex: 2147483000,
  lang: null,
  title: null,
  open: false,
};

let instance = null;

function normalize(options) {
  if (!options || !options.tenant) {
    throw new Error('CpBotWidget.init: "tenant" is required');
  }
  if (!options.token && !options.tokenProvider && !options.tokenUrl) {
    throw new Error('CpBotWidget.init: provide "token", "tokenProvider" or "tokenUrl"');
  }
  const theme = options.theme || {};
  return {
    ...DEFAULTS,
    tenant: String(options.tenant).toLowerCase(),
    token: options.token || null,
    tokenProvider: options.tokenProvider || null,
    tokenUrl: options.tokenUrl || null,
    apiUrl: (options.apiUrl || DEFAULTS.apiUrl).replace(/\/+$/, ''),
    chatUrl: (options.chatUrl || DEFAULTS.chatUrl).replace(/\/+$/, ''),
    lang: options.lang || DEFAULTS.lang,
    title: options.title || theme.title || null,
    color: theme.color || null,
    position: theme.position === 'bottom-left' ? 'bottom-left' : DEFAULTS.position,
    offset: Number.isFinite(theme.offset) ? theme.offset : DEFAULTS.offset,
    zIndex: Number.isFinite(theme.zIndex) ? theme.zIndex : DEFAULTS.zIndex,
    open: !!options.open,
  };
}

const CSS = `
:host { all: initial; }
* { box-sizing: border-box; }
.launcher {
  position: fixed; width: 56px; height: 56px; border-radius: 50%; border: 0; cursor: pointer;
  background: var(--cpbot-color); color: #fff; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 14px rgba(0,0,0,.25); transition: transform .15s ease;
}
.launcher:hover { transform: scale(1.06); }
.launcher:focus-visible { outline: 3px solid #fff; outline-offset: -6px; }
.launcher svg { width: 26px; height: 26px; fill: currentColor; }
.panel {
  position: fixed; width: 380px; height: min(600px, calc(100vh - 110px)); background: #fff;
  border-radius: 14px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,.28);
  display: none;
}
.panel.open { display: block; }
.panel iframe { width: 100%; height: 100%; border: 0; display: block; }
.right { right: var(--cpbot-offset); }
.left { left: var(--cpbot-offset); }
.launcher { bottom: var(--cpbot-offset); }
.panel { bottom: calc(var(--cpbot-offset) + 68px); }
@media (max-width: 480px) {
  .panel { inset: 0; width: 100%; height: 100%; border-radius: 0; }
}
`;

const ICON =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7l-4 4V4a2 2 0 0 1 1-1.7z"/></svg>';

class Widget {
  constructor(options) {
    this.o = options;
    this.isOpen = false;
    this.loadedOnce = false;
    this.chatOrigin = new URL(options.chatUrl, location.href).origin;
    this.onMessage = this.onMessage.bind(this);
    this.onKeydown = this.onKeydown.bind(this);
    this.build();
    window.addEventListener('message', this.onMessage);
    document.addEventListener('keydown', this.onKeydown);
    this.loadConfig();
    if (options.open) this.open();
  }

  build() {
    const o = this.o;
    this.host = document.createElement('div');
    this.host.setAttribute('data-cpbot-widget', '');
    this.host.style.cssText = `position:fixed;z-index:${o.zIndex};`;
    const root = this.host.attachShadow({ mode: 'open' });
    const side = o.position === 'bottom-left' ? 'left' : 'right';

    const style = document.createElement('style');
    style.textContent = CSS;

    this.panel = document.createElement('div');
    this.panel.className = `panel ${side}`;
    this.panel.setAttribute('role', 'dialog');

    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = `launcher ${side}`;
    this.button.innerHTML = ICON;
    this.button.setAttribute('aria-expanded', 'false');
    this.button.addEventListener('click', () => this.toggle());

    root.append(style, this.panel, this.button);
    this.setTitle(o.title || 'Chat');
    this.setColor(o.color || '#2563EB');
    this.host.style.setProperty('--cpbot-offset', `${o.offset}px`);
    document.body.appendChild(this.host);
  }

  setColor(color) {
    this.host.style.setProperty('--cpbot-color', color);
  }

  setTitle(title) {
    this.button.setAttribute('aria-label', title);
    this.panel.setAttribute('aria-label', title);
  }

  // Tenant customization from the backend; explicit init options win.
  async loadConfig() {
    try {
      const res = await fetch(`${this.o.apiUrl}/widget/config?tenant=${encodeURIComponent(this.o.tenant)}`);
      if (!res.ok) return;
      const cfg = await res.json();
      if (!this.o.color && cfg.icon_color) this.setColor(cfg.icon_color);
      if (!this.o.title && cfg.bot_name) this.setTitle(cfg.bot_name);
    } catch (_) {
      // Non-fatal: the launcher keeps its defaults.
    }
  }

  async resolveToken() {
    const o = this.o;
    if (o.tokenProvider) return await o.tokenProvider();
    if (o.tokenUrl) {
      const res = await fetch(o.tokenUrl, { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`token endpoint returned ${res.status}`);
      const text = await res.text();
      try {
        const json = JSON.parse(text);
        return typeof json === 'string' ? json : json.token;
      } catch (_) {
        return text.trim();
      }
    }
    return o.token;
  }

  async loadIframe() {
    let token;
    try {
      token = await this.resolveToken();
    } catch (err) {
      console.error('[cpbot-widget] could not get an SSO token', err);
      return;
    }
    if (!token) return;
    const hash = new URLSearchParams({ tenant: this.o.tenant, token });
    if (this.o.lang) hash.set('lang', this.o.lang);
    // Token goes in the fragment so it is never sent to a server or leaked via Referer.
    const src = `${this.o.chatUrl}#${hash.toString()}`;

    if (!this.iframe) {
      this.iframe = document.createElement('iframe');
      this.iframe.title = this.button.getAttribute('aria-label') || 'Chat';
      this.iframe.setAttribute('allow', 'clipboard-write');
      this.panel.appendChild(this.iframe);
      this.iframe.src = src;
    } else {
      // Changing only the fragment would not reload the document, so
      // navigate the iframe's own location afresh.
      this.iframe.contentWindow.location.replace(src);
    }
    this.loadedOnce = true;
  }

  open() {
    if (this.isOpen) return;
    this.isOpen = true;
    this.panel.classList.add('open');
    this.button.setAttribute('aria-expanded', 'true');
    if (!this.loadedOnce) this.loadIframe();
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.panel.classList.remove('open');
    this.button.setAttribute('aria-expanded', 'false');
  }

  toggle() {
    this.isOpen ? this.close() : this.open();
  }

  onMessage(event) {
    if (event.origin !== this.chatOrigin) return;
    if (this.iframe && event.source !== this.iframe.contentWindow) return;
    const type = event.data && event.data.type;
    if (type === 'cpbot:close') this.close();
    // The 30-min chat session ended: reload with a fresh partner token when
    // one can be minted (tokenProvider/tokenUrl); a static token is
    // typically already expired, so retrying it would just fail again.
    if (type === 'cpbot:session-expired' && (this.o.tokenProvider || this.o.tokenUrl)) {
      this.loadIframe();
    }
  }

  onKeydown(event) {
    if (event.key === 'Escape' && this.isOpen) this.close();
  }

  destroy() {
    window.removeEventListener('message', this.onMessage);
    document.removeEventListener('keydown', this.onKeydown);
    this.host.remove();
  }
}

function start(options) {
  if (instance) return instance;
  const create = () => {
    instance = new Widget(normalize(options));
  };
  if (document.body) create();
  else document.addEventListener('DOMContentLoaded', create, { once: true });
  return null;
}

export function init(options) {
  start(options);
}
export function open() {
  if (instance) instance.open();
}
export function close() {
  if (instance) instance.close();
}
export function toggle() {
  if (instance) instance.toggle();
}
export function destroy() {
  if (instance) {
    instance.destroy();
    instance = null;
  }
}

// <script src="cpbot-widget.js" data-tenant="..." data-token="..."></script>
function autoInit() {
  const script = document.currentScript;
  if (!script || !script.dataset || !script.dataset.tenant) return;
  const d = script.dataset;
  init({
    tenant: d.tenant,
    token: d.token,
    tokenUrl: d.tokenUrl,
    apiUrl: d.apiUrl,
    chatUrl: d.chatUrl,
    lang: d.lang,
    title: d.title,
    open: d.open === 'true',
    theme: {
      color: d.color,
      position: d.position,
      offset: d.offset ? Number(d.offset) : undefined,
    },
  });
}

if (typeof document !== 'undefined') autoInit();
