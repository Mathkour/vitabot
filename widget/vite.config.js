import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    lib: {
      entry: 'src/index.js',
      name: 'CpBotWidget',
      formats: ['es', 'umd'],
      fileName: (format) => (format === 'es' ? 'cpbot-widget.esm.mjs' : 'cpbot-widget.js'),
    },
    minify: 'esbuild',
    sourcemap: false,
    emptyOutDir: true,
  },
});
