// Start tap and camera start (SPEC 7.1).

export interface StartResult {
  fullscreen: boolean;
  wakeLock: boolean;
  orientationLocked: boolean;
  motionPermission: "granted" | "denied" | "not-needed";
}

type PermissionRequester = { requestPermission?: () => Promise<"granted" | "denied"> };

/**
 * Call synchronously from the Start tap: fullscreen, motion permission (iOS) and wake lock all need a user
 * gesture, so both requests are made before the first await.
 */
export async function startTap(): Promise<StartResult> {
  const ua = navigator.userAgent;
  const android = /Android/.test(ua);
  // Only iOS needs (and only iOS should get) the motion prompt; desktop Chrome also exposes requestPermission
  // and answers "denied" on laptops without sensors, which would read as a refusal instead of "absent".
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  const fullscreenRequest = android ? document.documentElement.requestFullscreen?.() : undefined;
  const motion = (globalThis as unknown as { DeviceMotionEvent?: PermissionRequester }).DeviceMotionEvent;
  const motionRequest = ios && typeof motion?.requestPermission === "function" ? motion.requestPermission() : undefined;

  const result: StartResult = { fullscreen: false, wakeLock: false, orientationLocked: false, motionPermission: "not-needed" };
  if (fullscreenRequest) {
    result.fullscreen = await fullscreenRequest.then(() => true, () => false);
    if (result.fullscreen) {
      const orientation = screen.orientation as ScreenOrientation & { lock?: (o: string) => Promise<void> };
      result.orientationLocked = await (orientation.lock?.("portrait") ?? Promise.reject()).then(() => true, () => false);
    }
  }
  if (android && "wakeLock" in navigator) {
    result.wakeLock = await navigator.wakeLock.request("screen").then(() => true, () => false);
  }
  if (motionRequest) result.motionPermission = await motionRequest.catch(() => "denied" as const);
  return result;
}

export interface OpenCamera {
  stream: MediaStream;
  track: MediaStreamTrack;
}

/** getUserMedia with the SPEC 7.1 constraints, attached to `video` and playing. */
export async function openCamera(video: HTMLVideoElement): Promise<OpenCamera> {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } },
    audio: false,
  });
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream;
  await video.play();
  if (!video.videoWidth) await new Promise((r) => video.addEventListener("loadedmetadata", r, { once: true }));
  return { stream, track: stream.getVideoTracks()[0]! };
}

export function stopCamera(cam: OpenCamera | null, video?: HTMLVideoElement): void {
  for (const t of cam?.stream.getTracks() ?? []) t.stop();
  if (video) video.srcObject = null;
}
