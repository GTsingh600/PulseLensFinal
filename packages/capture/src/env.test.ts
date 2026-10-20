import { describe, expect, it } from "vitest";
import { detectChannel, fpsBand, parseUserAgent, profileKey } from "./env";

const UA = {
  androidChrome:
    "Mozilla/5.0 (Linux; Android 14; SM-A145F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
  samsung:
    "Mozilla/5.0 (Linux; Android 13; SM-M135F) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
  iphoneSafari:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
  iphoneChrome:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/129.0.6668.69 Mobile/15E148 Safari/604.1",
  ipadOS:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
  winChrome:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
  winEdge:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.2792.65",
  macFirefox: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:131.0) Gecko/20100101 Firefox/131.0",
  linuxChrome: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
};

describe("detectChannel (M1.4 acceptance: channel detection works)", () => {
  it("classifies phones as mobile_browser", () => {
    for (const ua of [UA.androidChrome, UA.samsung, UA.iphoneSafari, UA.iphoneChrome]) {
      expect(detectChannel({ ua, uaMobile: null, maxTouchPoints: 5 })).toBe("mobile_browser");
    }
  });

  it("classifies laptops as desktop_browser", () => {
    for (const ua of [UA.winChrome, UA.winEdge, UA.macFirefox, UA.linuxChrome, UA.ipadOS]) {
      expect(detectChannel({ ua, uaMobile: null, maxTouchPoints: 0 })).toBe("desktop_browser");
    }
  });

  it("treats an iPad (desktop UA with touch) as mobile", () => {
    expect(detectChannel({ ua: UA.ipadOS, uaMobile: null, maxTouchPoints: 5 })).toBe("mobile_browser");
  });

  it("trusts UA-CH mobile when the browser provides it", () => {
    expect(detectChannel({ ua: UA.winChrome, uaMobile: true, maxTouchPoints: 0 })).toBe("mobile_browser");
    expect(detectChannel({ ua: UA.androidChrome, uaMobile: false, maxTouchPoints: 5 })).toBe("desktop_browser");
  });
});

describe("parseUserAgent", () => {
  it.each([
    [UA.androidChrome, "Chrome 129", "Android 14"],
    [UA.samsung, "Samsung Internet 25.0", "Android 13"],
    [UA.iphoneSafari, "Safari 17.5", "iOS 17.5"],
    [UA.iphoneChrome, "Chrome iOS 129", "iOS 17.5"],
    [UA.winEdge, "Edge 129", "Windows"],
    [UA.winChrome, "Chrome 129", "Windows"],
    [UA.macFirefox, "Firefox 131", "macOS 14.5"],
    [UA.linuxChrome, "Chrome 129", "Linux"],
  ])("%s", (ua, browser, os) => {
    expect(parseUserAgent(ua)).toMatchObject({ browser, os });
  });
});

describe("device profile (SPEC 8)", () => {
  it("bands fps at 20 and 27", () => {
    expect([12, 19.9, 20, 26.9, 27, 30].map(fpsBand)).toEqual(["lt20", "lt20", "20to27", "20to27", "ge27", "ge27"]);
    expect(profileKey("mobile_browser", 29.7)).toBe("mobile_browser|ge27");
    expect(profileKey("desktop_browser", null)).toBeNull();
  });
});
