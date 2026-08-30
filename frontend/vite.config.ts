import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Портът е 3000, защото README-то обещава фронтенда там.
export default defineConfig({
  plugins: [react()],
  // strictPort: при зает порт Vite по подразбиране мълчаливо мине на 3001, а
  // той не е в cors_origins на бекенда — изгледът тръгва и всяка заявка се
  // проваля. По-добре да откаже да стартира и да го каже.
  server: { port: 3000, host: true, strictPort: true },
  preview: { port: 3000, host: true, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
