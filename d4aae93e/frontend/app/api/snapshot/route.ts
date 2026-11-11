import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const api = process.env.CAMPUS_PULSE_API;
  if (api) {
    try {
      const response = await fetch(`${api.replace(/\/$/, "")}/api/v1/snapshot`, {
        cache: "no-store",
      });
      if (response.ok) {
        return NextResponse.json(await response.json());
      }
    } catch {
      // fall through to the bundled replay snapshot
    }
  }
  try {
    const raw = await fs.readFile(
      path.join(process.cwd(), "public", "data", "snapshot.json"),
      "utf8",
    );
    return new NextResponse(raw, {
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json({ error: "snapshot unavailable" }, { status: 503 });
  }
}
