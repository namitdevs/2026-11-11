import { promises as fs } from "fs";
import path from "path";

import type { Snapshot } from "./types";

export async function loadSnapshot(): Promise<Snapshot | null> {
  try {
    const raw = await fs.readFile(
      path.join(process.cwd(), "public", "data", "snapshot.json"),
      "utf8",
    );
    return JSON.parse(raw) as Snapshot;
  } catch {
    return null;
  }
}
