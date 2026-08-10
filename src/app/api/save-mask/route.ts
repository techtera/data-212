import { mkdir, writeFile, readdir, unlink } from "fs/promises";
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

export async function DELETE(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const jobId = searchParams.get("jobId");
    const imageId = searchParams.get("imageId");

    if (!jobId) {
      return NextResponse.json({ error: "Missing jobId" }, { status: 400 });
    }

    const dir = join(process.cwd(), "temp", jobId, "masks");

    // Delete a single image's mask if imageId is provided
    if (imageId) {
      const filePath = join(dir, `${imageId}.json`);
      try {
        await unlink(filePath);
        return NextResponse.json({ ok: true });
      } catch (err: any) {
        if (err.code === "ENOENT") {
          return NextResponse.json({ ok: true, alreadyDeleted: true });
        }
        throw err;
      }
    }

    // Otherwise delete ALL mask files for this job
    let deleted = 0;
    try {
      const files = await readdir(dir);
      const jsonFiles = files.filter((f) => f.endsWith(".json"));
      for (const f of jsonFiles) {
        try {
          await unlink(join(dir, f));
          deleted += 1;
        } catch {
          // ignore individual failures
        }
      }
    } catch {
      // dir doesn't exist -> nothing to delete
    }

    return NextResponse.json({ ok: true, deleted });
  } catch (err) {
    console.error("Delete mask error:", err);
    return NextResponse.json({ error: "Failed to delete mask" }, { status: 500 });
  }
}