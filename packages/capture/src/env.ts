// Browser, OS, channel and profile detection (SPEC 7.1, 8). Pure functions of the UA so they are unit-tested.
import { config, type Channel } from "@pulselens/types";

export interface UserAgentInfo {
  browser: string;
  os: string;
  mobile: boolean;
}

const BROWSERS: [RegExp, string][] = [
  [/Edg(?:A|iOS)?\/(\d+)/, "Edge"],
  [/SamsungBrowser\/([\d.]+)/, "Samsung Internet"],
  [/OPR\/(\d+)/, "Opera"],
  [/CriOS\/(\d+)/, "Chrome iOS"],
  [/FxiOS\/(\d+)/, "Firefox iOS"],
  [/Firefox\/(\d+)/, "Firefox"],
  [/Chrome\/(\d+)/, "Chrome"],
  [/Version\/([\d.]+).*Safari/, "Safari"],
];

function parseOs(ua: string): string {
  let m: RegExpExecArray | null;
  if ((m = /Android (\d+(?:\.\d+)?)/.exec(ua))) return `Android ${m[1]}`;
  if ((m = /(?:iPhone|iPad|iPod).*? OS (\d+)_(\d+)/.exec(ua))) return `iOS ${m[1]}.${m[2]}`;
  if (/Windows NT/.test(ua)) return "Windows";
  if (/CrOS/.test(ua)) return "ChromeOS";
  if ((m = /Mac OS X (\d+)[._](\d+)/.exec(ua))) return `macOS ${m[1]}.${m[2]}`;
  if (/Linux/.test(ua)) return "Linux";
  return "unknown";
}

export function parseUserAgent(ua: string): UserAgentInfo {
  let browser = "unknown";
  for (const [re, name] of BROWSERS) {
    const m = re.exec(ua);
    if (m) {
      browser = `${name} ${m[1]}`;
      break;
    }
  }
  return { browser, os: parseOs(ua), mobile: /Android|iPhone|iPad|iPod|Mobile/.test(ua) };
}

/**
 * mobile_browser or desktop_browser. UA-CH `mobile` wins when the browser provides it; an iPad reports a
 * Mac UA, so a "Macintosh" UA with a touch screen counts as mobile.
 */
export function detectChannel(input: { ua: string; uaMobile: boolean | null; maxTouchPoints: number }): Channel {
  if (input.uaMobile !== null) return input.uaMobile ? "mobile_browser" : "desktop_browser";
  if (parseUserAgent(input.ua).mobile) return "mobile_browser";
  if (/Macintosh/.test(input.ua) && input.maxTouchPoints > 1) return "mobile_browser";
  return "desktop_browser";
}

export type FpsBand = "lt20" | "20to27" | "ge27";

export function fpsBand(fps: number): FpsBand {
  const [low, high] = config.profiles.fps_bands;
  return fps < low ? "lt20" : fps < high ? "20to27" : "ge27";
}

/** SPEC 8 profile key, or null until fps is known. */
export function profileKey(channel: Channel, fps: number | null | undefined): string | null {
  return fps ? `${channel}|${fpsBand(fps)}` : null;
}

/** CLAUDE.md: phones need HTTPS for the camera and motion sensors. */
export function secureContextError(): string | null {
  if (!globalThis.isSecureContext) return "This page must be opened over HTTPS (use the tunnel URL) to use the camera.";
  if (!navigator.mediaDevices?.getUserMedia) return "This browser does not give web pages access to the camera.";
  return null;
}
