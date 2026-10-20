// Capture harness (capture-harness.html): the capture package with no UI, for e2e and device debugging.
import { CaptureSession, startTap } from "@pulselens/capture";
import { explainMaybe } from "@pulselens/explain";

const video = document.querySelector<HTMLVideoElement>("#video")!;
const out = document.querySelector<HTMLPreElement>("#state")!;
const button = document.querySelector<HTMLButtonElement>("#start")!;

button.addEventListener("click", () => {
  button.disabled = true;
  const start = startTap(); // first, inside the click: fullscreen and motion permission need the gesture
  const session = new CaptureSession({
    video,
    product: "lab",
    mode: "superset",
    role: "lab",
    promptText: (key) => explainMaybe(key)?.text ?? "",
    onChange: (state) => {
      document.body.dataset.phase = state.phase;
      out.textContent = JSON.stringify(state, null, 1);
    },
  });
  void start.then((s) => session.start(s));
});
