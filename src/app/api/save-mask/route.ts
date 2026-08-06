import { mkdir, writeFile, readdir } from "fs/promises";
import { join } from "path";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const { jobId, imageId, polygons } = await req.json();
    
    if (!jobId || !imageId || !polygons) {
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
    }

    const dir = join(process.cwd(), "temp", jobId, "masks");
    await mkdir(dir, { recursive: true });
    await writeFile(join(dir, `${imageId}.json`), JSON.stringify(polygons, null, 2));
    
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("Save mask error:", err);
    return NextResponse.json({ error: "Failed to save mask" }, { status: 500 });
  }
}

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const jobId = searchParams.get("jobId");
    
    if (!jobId) {
      return NextResponse.json({ error: "Missing jobId" }, { status: 400 });
    }

    const dir = join(process.cwd(), "temp", jobId, "masks");
    let savedCount = 0;
    let savedImages: string[] = [];
    try {
      const files = await readdir(dir);
      const jsonFiles = files.filter((f) => f.endsWith(".json"));
      savedCount = jsonFiles.length;
      savedImages = jsonFiles.map(f => f.replace(".json", ""));
    } catch {
      savedCount = 0;
      savedImages = [];
    }
    
    return NextResponse.json({ savedCount, savedImages });
  } catch (err) {
    console.error("Get mask count error:", err);
    return NextResponse.json({ error: "Failed to get count" }, { status: 500 });
  }
}