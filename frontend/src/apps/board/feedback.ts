// Communication board — selection feedback and conventional text-to-speech (browser APIs).
//
// Speech here is ordinary computer speech (the Web Speech API reads the composed text aloud).
// It is NOT neural speech decoding: nothing about it comes from brain signals.

export const SPEECH_LABEL = "computer speech (not neural speech decoding)";

export function speechAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
}

export function speak(text: string, rate: number): boolean {
  if (!speechAvailable() || !text.trim()) return false;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = rate;
  window.speechSynthesis.speak(u);
  return true;
}

let audio: AudioContext | null = null;

/** A short, quiet tick (Web Audio). Returns false where audio is unavailable. */
export function tick(): boolean {
  const Ctx = typeof window !== "undefined" ? (window.AudioContext ?? null) : null;
  if (!Ctx) return false;
  try {
    audio ??= new Ctx();
    const t = audio.currentTime;
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.08, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
    osc.connect(gain).connect(audio.destination);
    osc.start(t);
    osc.stop(t + 0.07);
    return true;
  } catch {
    return false;
  }
}
