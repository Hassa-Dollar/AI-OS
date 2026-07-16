export const config = {
  apiUrl: import.meta.env.VITE_API_URL,
} as const;

if (!config.apiUrl) {
  throw new Error(
    "VITE_API_URL is not set. Copy .env.example from the repo root to components/web/.env and fill it.",
  );
}
