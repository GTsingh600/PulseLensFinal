// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { browserAndOs, detectGyro, fpsFields, webglRenderer } from "./details";

const WIN_CHROME_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36";

type Brand = { brand: string; version: string };

function stubUaData(opts: { platform?: string; platformVersion?: string; brands?: Brand[]; mobile?: boolean; throws?: boolean }) {
  const data = {
    mobile: opts.mobile ?? false,
    platform: opts.platform ?? "Windows",
    getHighEntropyValues: vi.fn(async () => {
      if (opts.throws) throw new Error("blocked");
      return { platformVersion: opts.platformVersion, fullVersionList: opts.brands };
    }),
  };
  Object.defineProperty(navigator, "userAgentData", { value: data, configurable: true });
  Object.defineProperty(navigator, "userAgent", { value: WIN_CHROME_UA, configurable: true });
}

const BRAVE: Brand[] = [
  { brand: "Not)A;Brand", version: "8.0.0.0" },
  { brand: "Chromium", version: "155.0.7000.1" },
  { brand: "Brave", version: "155.1.80.1" },
];

afterEach(() => {
  Reflect.deleteProperty(navigator, "userAgentData");
  vi.unstubAllGlobals();
});

describe("browserAndOs", () => {
  it("names the real brand from UA client hints, not Chromium or the GREASE brand", async () => {
    stubUaData({ brands: BRAVE, platformVersion: "15.0.0" });
    expect((await browserAndOs()).browser).toBe("Brave 155");
  });

  it("falls back to Chromium when it is the only real brand", async () => {
    stubUaData({ brands: [{ brand: "Chromium", version: "155.0" }, { brand: "Not_A Brand", version: "24" }] });
    expect((await browserAndOs()).browser).toBe("Chromium 155");
  });

  it("uses the UA string when the browser has no client hints", async () => {
    Object.defineProperty(navigator, "userAgent", { value: WIN_CHROME_UA, configurable: true });
    expect(await browserAndOs()).toEqual({ browser: "Chrome 155", os: "Windows", uaMobile: null });
  });

  it("keeps UA-CH mobile when the high-entropy hints are refused", async () => {
    stubUaData({ throws: true, mobile: true });
    expect(await browserAndOs()).toEqual({ browser: "Chrome 155", os: "Windows", uaMobile: true });
  });

  it("reports macOS and Android versions as the platform gives them", async () => {
    stubUaData({ platform: "Android", platformVersion: "14.0.0", brands: BRAVE, mobile: true });
    expect((await browserAndOs()).os).toBe("Android 14.0.0");
  });

  // UA-CH platformVersion on Windows is not the marketing version: 13.0.0 and up is Windows 11, 1 to 10 is
  // Windows 10. The Brave session recorded at G1 showed "Windows 19.0.0" on the Camera card.
  it("maps a Windows platformVersion of 13 or more to Windows 11", async () => {
    stubUaData({ platformVersion: "19.0.0", brands: BRAVE });
    expect((await browserAndOs()).os).toBe("Windows 11");
  });

  it("maps a Windows platformVersion below 13 to Windows 10", async () => {
    stubUaData({ platformVersion: "10.0.0", brands: BRAVE });
    expect((await browserAndOs()).os).toBe("Windows 10");
  });
});

describe("detectGyro", () => {
  it("is absent without DeviceMotionEvent (laptops)", async () => {
    vi.stubGlobal("DeviceMotionEvent", undefined);
    expect(await detectGyro("not-needed")).toBe("absent");
  });

  it("is denied when iOS motion permission was refused", async () => {
    vi.stubGlobal("DeviceMotionEvent", class {});
    expect(await detectGyro("denied")).toBe("denied");
  });

  it("is available after a rotation event and granted when permission was asked", async () => {
    vi.stubGlobal("DeviceMotionEvent", class {});
    for (const [permission, state] of [["not-needed", "available"], ["granted", "granted"]] as const) {
      const p = detectGyro(permission, 500);
      const e = Object.assign(new Event("devicemotion"), { rotationRate: { alpha: 0.1, beta: null, gamma: null } });
      dispatchEvent(e);
      expect(await p).toBe(state);
    }
  });

  it("is absent when no rotation arrives before the timeout, or the event carries no rotation", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("DeviceMotionEvent", class {});
    const p = detectGyro("not-needed", 1000);
    dispatchEvent(Object.assign(new Event("devicemotion"), { rotationRate: { alpha: null, beta: null, gamma: null } }));
    vi.advanceTimersByTime(1000);
    expect(await p).toBe("absent");
    vi.useRealTimers();
  });
});

describe("fpsFields and webglRenderer", () => {
  it("puts a measured 15.6 fps desktop in the lt20 profile even when it claims 30", () => {
    expect(fpsFields("desktop_browser", { fpsMedian: 15.6, jitterMs: 7 } as never)).toEqual({
      fps_median: 15.6,
      fps_jitter_ms: 7,
      profile_measured: "desktop_browser|lt20",
    });
    expect(fpsFields("desktop_browser", { fpsMedian: null, jitterMs: null } as never).profile_measured).toBeNull();
  });

  it("returns null instead of throwing where WebGL is unavailable", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    expect(webglRenderer()).toBeNull();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => {
      throw new Error("blocked by the browser");
    });
    expect(webglRenderer()).toBeNull();
  });
});
