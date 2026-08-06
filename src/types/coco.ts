export interface CocoPoint {
  x: number;
  y: number;
}

export interface CocoPolygonRow {
  image_id: string;
  category_id: number;
  segmentation: number[][];
  bbox: [number, number, number, number];
  area: number;
  is_crowd: 0 | 1;
}

export interface CocoFile {
  images: {
    id: string;
    file_name: string;
    width: number;
    height: number;
  }[];
  annotations: CocoPolygonRow[];
  categories: {
    id: number;
    name: string;
  }[];
}
