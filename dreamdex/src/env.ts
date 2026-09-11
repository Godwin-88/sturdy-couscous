/**
 * env.ts — dotenv that resolves the REPO-ROOT `.env` (config lives at the repo
 * root, but every npm script runs from `dreamdex/`). Works from `src/` (tsx)
 * and `dist/` (built) because both sit two levels under the repo root.
 */
import dotenv from "dotenv";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDir = dirname(fileURLToPath(import.meta.url)); // <repo>/dreamdex/src (or /dist)
const rootEnv = join(moduleDir, "../../.env");

dotenv.config({ path: [rootEnv, "./.env"] });