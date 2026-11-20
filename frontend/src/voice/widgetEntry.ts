/**
 * Standalone bundle for the website widget (public/widget.js loads it on demand as /sarvam-voice.js).
 * Built by vite.voice.config.ts; exposes window.KuralSarvamVoice.start(options).
 */
import { startSarvamCall } from './sarvamCall'

declare global {
  interface Window { KuralSarvamVoice?: { start: typeof startSarvamCall } }
}

window.KuralSarvamVoice = { start: startSarvamCall }
