/**
 * Photosensitivity guard (SPEC 7.4, 17): never more than 3 flash onsets in any 1 s window.
 * The orchestrator's spacing already respects this; the client enforces it as a second line of defence.
 */
export class FlashLimiter {
  private onsets: number[] = [];

  constructor(
    private readonly max = 3,
    private readonly windowMs = 1000,
  ) {}

  /** Whether a flash starting at time t (ms) keeps every window within the limit. */
  allow(t: number): boolean {
    return this.onsets.filter((s) => t - s < this.windowMs).length < this.max;
  }

  record(t: number): void {
    this.onsets = [...this.onsets.filter((s) => t - s < this.windowMs), t];
  }
}
