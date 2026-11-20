import { defineConfig } from 'vite'

// Second build: the website widget's voice-call bundle (dist/sarvam-voice.js), loaded on demand by public/widget.js.
// Runs after the dashboard build, so it must not empty dist/.
export default defineConfig({
  build: {
    emptyOutDir: false,
    copyPublicDir: false,
    lib: {
      entry: 'src/voice/widgetEntry.ts',
      name: 'KuralSarvamVoiceBundle',
      formats: ['iife'],
      fileName: () => 'sarvam-voice.js',
    },
  },
})
