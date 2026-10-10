import { defineConfig } from "@playwright/test";

/** Expects the API on :8000 (`uv run poe api`) and the app on :3000 (`npm run dev` / `npm start`). */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: process.env.BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
  reporter: [["list"]],
});
