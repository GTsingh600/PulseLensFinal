// CameraDetails collection (SPEC 7.1 step 3, SPEC 4.2).
import type { CameraDetails, Channel, ClockSource, GyroState } from "@pulselens/types";
import { now } from "./clock";
import { parseUserAgent, profileKey } from "./env";
import type { GrabberStats } from "./grabber";

type Json = Record<string, unknown>;

interface UADataLike {
  mobile: boolean;
  platform: string;
  getHighEntropyValues(hints: string[]): Promise<{
    platformVersion?: string;
    fullVersionList?: { brand: string; version: string }[];
  }>;
}

const uaData = () => (navigator as Navigator & { userAgentData?: UADataLike }).userAgentData;

/**
 * UA-CH platformVersion is not the marketing version on Windows: 13 and up is Windows 11, 1 to 12 is Windows 10,
 * 0 is older. Elsewhere it is the OS version (Android 14.0.0, macOS 14.5.0).
 */
export function osName(platform: string, version: string | undefined): string {
  if (!version) return platform;
  if (platform === "Windows") {
    const major = Number.parseInt(version, 10);
    return major >= 13 ? "Windows 11" : major >= 1 ? "Windows 10" : "Windows";
  }
  return `${platform} ${version}`;
}

/** Browser and OS from UA client hints where available, else from the UA string. */
export async function browserAndOs(): Promise<{ browser: string; os: string; uaMobile: boolean | null }> {
  const parsed = parseUserAgent(navigator.userAgent);
  const data = uaData();
  if (!data) return { browser: parsed.browser, os: parsed.os, uaMobile: null };
  try {
    const hi = await data.getHighEntropyValues(["platformVersion", "fullVersionList"]);
    const brand = hi.fullVersionList?.find((b) => !/Not.?A.?Brand|Chromium/i.test(b.brand))
      ?? hi.fullVersionList?.find((b) => /Chromium/i.test(b.brand));
    return {
      browser: brand ? `${brand.brand} ${brand.version.split(".")[0]}` : parsed.browser,
      os: data.platform ? osName(data.platform, hi.platformVersion) : parsed.os,
      uaMobile: data.mobile,
    };
  } catch {
    return { browser: parsed.browser, os: parsed.os, uaMobile: data.mobile };
  }
}

/** Screen refresh estimate: median requestAnimationFrame interval over `ms`. */
export function measureRefreshHz(ms = 1000): Promise<number | null> {
  return new Promise((resolve) => {
    const times: number[] = [];
    const start = now();
    const tick = (t: number) => {
      times.push(t);
      if (now() - start < ms) requestAnimationFrame(tick);
      else {
        const d = times.slice(1).map((x, k) => x - times[k]!).sort((a, b) => a - b);
        resolve(d.length ? Math.round(1000 / d[Math.floor(d.length / 2)]!) : null);
      }
    };
    requestAnimationFrame(tick);
  });
}

export function webglRenderer(): string | null {
  try {
    const gl = document.createElement("canvas").getContext("webgl");
    if (!gl) return null;
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    return String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
  } catch {
    return null;
  }
}

/** Gyro: absent without DeviceMotionEvent or without a rotation event within `timeoutMs`. */
export function detectGyro(permission: "granted" | "denied" | "not-needed", timeoutMs = 1000): Promise<GyroState> {
  if (typeof DeviceMotionEvent === "undefined") return Promise.resolve("absent");
  if (permission === "denied") return Promise.resolve("denied");
  return new Promise((resolve) => {
    const done = (state: GyroState) => {
      removeEventListener("devicemotion", onMotion);
      clearTimeout(timer);
      resolve(state);
    };
    const onMotion = (e: DeviceMotionEvent) => {
      const r = e.rotationRate;
      if (r && (r.alpha !== null || r.beta !== null || r.gamma !== null)) done(permission === "granted" ? "granted" : "available");
    };
    const timer = setTimeout(() => done("absent"), timeoutMs);
    addEventListener("devicemotion", onMotion);
  });
}

async function sha256Hex(text: string): Promise<string> {
  if (!crypto.subtle) return "";
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Drops ids from settings/capabilities (the hash goes in device_id_hash) and makes the object JSON-safe. */
function plain(obj: object | undefined): Json {
  const out: Json = {};
  for (const [k, v] of Object.entries(obj ?? {})) if (k !== "deviceId" && k !== "groupId") out[k] = JSON.parse(JSON.stringify(v));
  return out;
}

export interface DetailsInput {
  track: MediaStreamTrack;
  channel: Channel;
  clockSource: ClockSource;
  gyro: GyroState;
  stats: GrabberStats;
}

export async function collectCameraDetails(input: DetailsInput): Promise<CameraDetails> {
  const settings = input.track.getSettings();
  let capabilities: Json = {};
  try {
    capabilities = plain(input.track.getCapabilities?.());
  } catch {
    // getCapabilities is missing or throws on some browsers (Firefox); empty is fine
  }
  const [{ browser, os, uaMobile }, refresh, idHash] = await Promise.all([
    browserAndOs(),
    measureRefreshHz(),
    sha256Hex(`${settings.deviceId ?? ""}|${settings.groupId ?? ""}`),
  ]);
  return {
    channel: input.channel,
    browser,
    os,
    ua_mobile: uaMobile,
    camera_label: input.track.label,
    device_id_hash: idHash.slice(0, 16),
    settings: plain(settings),
    capabilities,
    native_modes: [],
    ...fpsFields(input.channel, input.stats),
    clock_source: input.clockSource,
    rvfc: "requestVideoFrameCallback" in HTMLVideoElement.prototype,
    resize_mode_supported: "resizeMode" in navigator.mediaDevices.getSupportedConstraints(),
    gyro: input.gyro,
    screen: { w: screen.width, h: screen.height, dpr: devicePixelRatio, refresh_hz_estimate: refresh },
    webgl_renderer: webglRenderer(),
    webdriver: !!navigator.webdriver,
    profile_claimed: profileKey(input.channel, settings.frameRate),
    noise_curve: null,
    fingerprint_pce: null,
  };
}

/** The fields that change as frames arrive; sent again as a partial update (SPEC 7.1 step 4). */
export function fpsFields(channel: Channel, stats: GrabberStats) {
  return {
    fps_median: stats.fpsMedian,
    fps_jitter_ms: stats.jitterMs,
    profile_measured: profileKey(channel, stats.fpsMedian),
  };
}
