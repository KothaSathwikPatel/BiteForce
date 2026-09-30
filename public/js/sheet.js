// Draggable bottom sheet with three detents (peek / half / full) on phones.
// On wide screens CSS turns it into a fixed side panel and this class does nothing.
const DESKTOP = window.matchMedia('(min-width: 900px)');
const ORDER = ['peek', 'half', 'full'];
const PEEK_PX = 112;

export class Sheet {
  constructor(sheetEl, grabberEl) {
    this.el = sheetEl;
    this.grabber = grabberEl;
    this.detent = 'peek';
    this.drag = null;
    document.documentElement.style.setProperty('--peek', `${PEEK_PX}px`);

    sheetEl.addEventListener('pointerdown', (e) => this.onDown(e));
    sheetEl.addEventListener('pointermove', (e) => this.onMove(e));
    sheetEl.addEventListener('pointerup', (e) => this.onUp(e));
    sheetEl.addEventListener('pointercancel', (e) => this.onUp(e));
    grabberEl.addEventListener('keydown', (e) => this.onKey(e));
    window.addEventListener('resize', () => this.apply());
    DESKTOP.addEventListener('change', () => this.apply());
    this.apply();
  }

  get isDesktop() {
    return DESKTOP.matches;
  }

  visibleFor(detent) {
    const height = this.el.offsetHeight;
    if (detent === 'peek') return PEEK_PX;
    if (detent === 'half') return Math.min(Math.round(window.innerHeight * 0.5), height);
    return height;
  }

  setDetent(detent) {
    this.detent = detent;
    this.apply();
  }

  apply() {
    if (this.isDesktop) {
      this.el.style.transform = '';
      this.el.style.removeProperty('--sheet-visible');
      return;
    }
    const visible = this.visibleFor(this.detent);
    this.el.style.setProperty('--sheet-visible', `${visible}px`);
    document.documentElement.style.setProperty('--sheet-visible', `${visible}px`);
    this.el.style.transform = `translateY(${this.el.offsetHeight - visible}px)`;
  }

  /** Space taken up by the sheet, used to centre map pins in the visible area. */
  insets() {
    if (this.isDesktop) return { bottom: 0, left: 396 };
    return { bottom: this.visibleFor(this.detent), left: 0 };
  }

  onDown(e) {
    if (this.isDesktop || !e.target.closest('[data-drag]')) return;
    this.el.setPointerCapture(e.pointerId);
    this.el.classList.add('is-dragging');
    this.drag = {
      startY: e.clientY,
      startVisible: this.visibleFor(this.detent),
      startDetent: this.detent,
      lastY: e.clientY,
      lastT: performance.now(),
      velocity: 0,
    };
  }

  onMove(e) {
    if (!this.drag) return;
    const { startY, startVisible } = this.drag;
    const max = this.visibleFor('full');
    const visible = Math.min(max, Math.max(PEEK_PX - 20, startVisible - (e.clientY - startY)));
    this.el.style.transform = `translateY(${this.el.offsetHeight - visible}px)`;
    this.el.style.setProperty('--sheet-visible', `${visible}px`);
    const now = performance.now();
    const dt = Math.max(1, now - this.drag.lastT);
    this.drag.velocity = (e.clientY - this.drag.lastY) / dt; // px/ms, positive = moving down
    this.drag.lastY = e.clientY;
    this.drag.lastT = now;
  }

  onUp(e) {
    if (!this.drag) return;
    const { startDetent, velocity } = this.drag;
    const current = this.el.offsetHeight - new DOMMatrixReadOnly(getComputedStyle(this.el).transform).m42;
    this.drag = null;
    this.el.classList.remove('is-dragging');
    if (this.el.hasPointerCapture?.(e.pointerId)) this.el.releasePointerCapture(e.pointerId);

    let target;
    if (Math.abs(velocity) > 0.5) {
      const index = ORDER.indexOf(startDetent);
      target = ORDER[Math.max(0, Math.min(ORDER.length - 1, index + (velocity < 0 ? 1 : -1)))];
    } else {
      target = ORDER.reduce((best, d) =>
        Math.abs(this.visibleFor(d) - current) < Math.abs(this.visibleFor(best) - current) ? d : best);
    }
    this.setDetent(target);
  }

  onKey(e) {
    const index = ORDER.indexOf(this.detent);
    if (e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      this.setDetent(ORDER[Math.min(ORDER.length - 1, index + 1)]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.setDetent(ORDER[Math.max(0, index - 1)]);
    }
  }
}
