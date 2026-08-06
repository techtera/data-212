import type { CocoEntry } from "@/store/jobStore";

interface Region {
  points: number[][];
  className: string;
}

interface AnnotatorState {
  images: Array<{
    src: string;
    id: string;
    regions?: Region[];
  }>;
}

function pointsToCocoSegmentation(points: number[][]): number[][] {
  const flat: number[] = [];
  for (const [x, y] of points) {
    flat.push(Math.round(x), Math.round(y));
  }
  return [flat];
}

function computeBbox(points: number[][]): [number, number, number, number] {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  const w = maxX - minX;
  const h = maxY - minY;
  return [minX, minY, w, h];
}

function computeArea(points: number[][]): number {
  let area = 0;
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    area += points[i][0] * points[j][1];
    area -= points[j][0] * points[i][1];
  }
  return Math.abs(area) / 2;
}

export function annotatorStateToCoco(
  state: AnnotatorState,
  imageIndex: number
): CocoEntry | null {
  const img = state.images[imageIndex];
  if (!img || !img.regions || img.regions.length === 0) return null;

  const firstRegion = img.regions[0];
  // Close the polygon if not already closed
  const points = firstRegion.points;
  const closedPoints = points.length > 0 && 
    (points[0][0] !== points[points.length - 1][0] || points[0][1] !== points[points.length - 1][1])
    ? [...points, points[0]]
    : points;
    
  const segmentation = pointsToCocoSegmentation(closedPoints);
  const bbox = computeBbox(closedPoints);
  const area = computeArea(closedPoints);

  return {
    image_id: img.id, // Use actual image ID from flagged images (e.g., "9", "10", "11", "12")
    segmentation,
    saved_at: new Date().toISOString(),
    category_id: 1,
    bbox,
    area,
    is_crowd: 0,
  };
}

export function buildCocoFile(entries: CocoEntry[]) {
  return {
    info: {
      year: new Date().getFullYear(),
      version: "1.0",
      description: "TERAFAC re-annotations",
      contributor: "frontend",
      date_created: new Date().toISOString(),
    },
    licenses: [],
    images: entries.map((e) => ({
      id: Number(e.image_id),
      file_name: `image_${e.image_id}.png`,
      width: 512,
      height: 512,
    })),
    annotations: entries.map((e, i) => ({
      id: i + 1,
      image_id: Number(e.image_id),
      category_id: e.category_id,
      segmentation: e.segmentation,
      area: e.area,
      bbox: e.bbox,
      iscrowd: e.is_crowd,
    })),
    categories: [{ id: 1, name: "object", supercategory: "none" }],
  };
}