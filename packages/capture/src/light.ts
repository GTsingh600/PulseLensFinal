/**
 * Light-suite pulse executor (SPEC 7.4).
 *
 * Phones: a full-screen overlay. Desktops: a border of 18% of the shorter side. Between pulses the overlay
 * shows a grey at the colours' luminance, so a colour pulse changes hue, not brightness. Split pulses paint
 * the left and right halves differently. Timing: `received` when the message arrives, colour set in the next
 * animation frame (`applied`), the following frame (`painted`), back to neutral after the duration (`ended`).
 */
import { config, type LightParams, type PulseAck, type PulseMessage } from "@pulselens/types";
import { now } from "./clock";
import { NEUTRAL_LUMINANCE, WHITE, cssColour, isoluminantColour, neutralColour, type RGB } from "./colour";
import { FlashLimiter } from "./flash";

export interface Fill {
  left: RGB;
  right: RGB;
}

export type OverlayMode = "fullscreen" | "border";

export class LightOverlay {
  readonly element: HTMLDivElement;
  readonly message: HTMLDivElement;
  private readonly halves: [HTMLDivElement, HTMLDivElement];
  current: Fill;
  /** Test hook: called with every non-neutral fill. */
  onPaint?: (fill: Fill) => void;

  constructor(private readonly opts: { mode: OverlayMode; Y?: number; borderFrac?: number }) {
    const neutral = neutralColour(opts.Y ?? NEUTRAL_LUMINANCE);
    this.current = { left: neutral, right: neutral };
    this.element = document.createElement("div");
    this.element.dataset.pulselensOverlay = opts.mode;
    Object.assign(this.element.style, {
      position: "fixed", inset: "0", zIndex: "2147483000", pointerEvents: "none", display: "flex",
    });
    this.halves = [document.createElement("div"), document.createElement("div")];
    for (const half of this.halves) {
      Object.assign(half.style, { flex: "1 1 50%", boxSizing: "border-box", borderStyle: "solid", borderWidth: "0" });
      this.element.append(half);
    }
    this.message = document.createElement("div");
    Object.assign(this.message.style, {
      position: "absolute", left: "8%", right: "8%", top: "40%", textAlign: "center", font: "600 22px system-ui, sans-serif",
      color: "#111",
    });
    if (opts.mode === "fullscreen") this.element.append(this.message);
    this.layout();
  }

  private readonly layout = () => {
    const [left, right] = this.halves;
    if (this.opts.mode === "fullscreen") {
      left.style.background = cssColour(this.current.left);
      right.style.background = cssColour(this.current.right);
      return;
    }
    const frac = this.opts.borderFrac ?? config.pulses.light.desktop_border_frac;
    const b = `${Math.round(frac * Math.min(innerWidth, innerHeight))}px`;
    left.style.borderWidth = `${b} 0 ${b} ${b}`;
    right.style.borderWidth = `${b} ${b} ${b} 0`;
    left.style.borderColor = cssColour(this.current.left);
    right.style.borderColor = cssColour(this.current.right);
  };

  mount(parent: HTMLElement = document.body): void {
    parent.append(this.element);
    addEventListener("resize", this.layout);
  }

  unmount(): void {
    removeEventListener("resize", this.layout);
    this.element.remove();
  }

  paint(fill: Fill): void {
    this.current = fill;
    this.layout();
    this.onPaint?.(fill);
  }

  get neutral(): RGB {
    return neutralColour(this.opts.Y ?? NEUTRAL_LUMINANCE);
  }

  setNeutral(): void {
    const n = this.neutral;
    this.current = { left: n, right: n };
    this.layout();
  }
}

const nextFrame = () => new Promise<void>((r) => requestAnimationFrame(() => r()));
const sleep = (ms: number) => new Promise((r) => setTimeout(r, Math.max(0, ms)));

function fillFor(p: Partial<LightParams>, Y: number): Fill | null {
  const hue = (h: unknown) => (typeof h === "number" && Number.isFinite(h) ? isoluminantColour(h, Y) : null);
  if (p.mode === "white") return { left: WHITE, right: WHITE };
  if (p.mode === "colour") {
    const c = hue(p.hue_deg);
    return c && { left: c, right: c };
  }
  if (p.mode === "split") {
    const l = hue(p.left_hue_deg);
    const r = hue(p.right_hue_deg);
    return l && r && { left: l, right: r };
  }
  return null;
}

export class LightPulseExecutor {
  private chain: Promise<unknown> = Promise.resolve();

  constructor(
    private readonly overlay: LightOverlay,
    private readonly limiter = new FlashLimiter(),
    private readonly Y = NEUTRAL_LUMINANCE,
  ) {}

  /** Runs pulses one at a time, in arrival order. */
  run(msg: PulseMessage, received: number): Promise<PulseAck> {
    const next = this.chain.then(() => this.execute(msg, received));
    this.chain = next.catch(() => undefined);
    return next;
  }

  private async execute(msg: PulseMessage, received: number): Promise<PulseAck> {
    const fail = (error: string): PulseAck => ({
      type: "ack", pulse_id: msg.pulse_id, sig: msg.sig, received, applied: null, painted: null, ended: null, ok: false,
      error, shown: null,
    });
    const params = msg.params as Partial<LightParams>;
    const fill = msg.kind === "light" ? fillFor(params, this.Y) : null;
    const duration = params.duration_ms;
    if (!fill || typeof duration !== "number" || duration <= 0 || duration > 2000) return fail("bad_params");
    if (!this.limiter.allow(now())) return fail("rate_limit");

    await nextFrame();
    this.overlay.paint(fill);
    const applied = now();
    this.limiter.record(applied);
    await nextFrame();
    const painted = now();
    await sleep(duration - (now() - painted));
    await nextFrame();
    this.overlay.setNeutral();
    const ended = now();

    const neutral = [...this.overlay.neutral];
    const shown = params.mode === "split"
      ? { neutral, left: [...fill.left], right: [...fill.right] }
      : { neutral, rgb: [...fill.left] };
    return { type: "ack", pulse_id: msg.pulse_id, sig: msg.sig, received, applied, painted, ended, ok: true, error: null, shown };
  }
}
