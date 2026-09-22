import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // En desarrollo, Vite reenvia estas rutas a FastAPI: para el navegador
    // todo viene de localhost:5173 y no hace falta configurar CORS.
    proxy: {
      '/chat': 'http://127.0.0.1:8000',
      '/historial': 'http://127.0.0.1:8000',
    },
  },
})