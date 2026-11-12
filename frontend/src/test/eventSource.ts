/** A fake EventSource: tests drive it with `open()`, `durable()`, `ephemeral()` and `fail()`. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static reset() { FakeEventSource.instances = []; }
  static get last() { return FakeEventSource.instances[FakeEventSource.instances.length - 1]; }

  url: string;
  closed = false;
  onopen: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  private listeners: Record<string, ((ev: MessageEvent) => void)[]> = {};

  constructor(url: string | URL) {
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (ev: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  removeEventListener(type: string, fn: (ev: MessageEvent) => void) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((f) => f !== fn);
  }
  close() { this.closed = true; }

  open() { this.onopen?.(new Event("open")); }
  fail() { this.onerror?.(new Event("error")); }
  emit(type: string, data: unknown, lastEventId = "") {
    const ev = new MessageEvent(type, { data: JSON.stringify(data), lastEventId });
    for (const fn of this.listeners[type] ?? []) fn(ev);
  }
  durable(ev: { seq: number }) { this.emit("durable", ev, String(ev.seq)); }
  ephemeral(data: unknown) { this.emit("ephemeral", data); }
}
