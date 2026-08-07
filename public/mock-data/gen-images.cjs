const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

function makePng(width, height, rgb) {
  const [r, g, b] = rgb;
  const bp = Buffer.alloc(width * height * 3);
  for (let i = 0; i < width * height; i++) {
    bp[i * 3] = r;
    bp[i * 3 + 1] = g;
    bp[i * 3 + 2] = b;
  }
  const raw = Buffer.alloc(height * (1 + width * 3));
  for (let y = 0; y < height; y++) {
    raw[y * (1 + width * 3)] = 0;
    bp.copy(raw, y * (1 + width * 3) + 1, y * width * 3, (y + 1) * width * 3);
  }
  const crc32 = (() => {
    const tbl = [];
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      tbl[n] = c >>> 0;
    }
    return (buf) => {
      let c = 0xffffffff;
      for (const byte of buf) c = tbl[(c ^ byte) & 0xff] ^ (c >>> 8);
      return (c ^ 0xffffffff) >>> 0;
    };
  })();
  const u32 = (n) => {
    const b = Buffer.alloc(4);
    b.writeUInt32BE(n >>> 0, 0);
    return b;
  };
  const chunk = (type, data) => {
    const t = Buffer.from(type, "ascii");
    const len = u32(data.length);
    const crc = u32(crc32(Buffer.concat([t, data])));
    return Buffer.concat([len, t, data, crc]);
  };
  const ihdr = Buffer.concat([
    u32(width),
    u32(height),
    Buffer.from([8, 2, 0, 0, 0]),
  ]);
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const idat = zlib.deflateSync(raw);
  const iend = Buffer.alloc(0);
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", idat),
    chunk("IEND", iend),
  ]);
}

const dirs = {
  images: path.join(__dirname, "images"),
  flagged: path.join(__dirname, "flagged"),
};
for (const d of Object.values(dirs)) fs.mkdirSync(d, { recursive: true });

const colors = [
  [200, 60, 60],
  [60, 200, 80],
  [60, 100, 220],
  [220, 180, 60],
  [180, 60, 200],
  [60, 200, 200],
  [200, 120, 60],
  [120, 200, 120],
  [220, 100, 100],
  [100, 220, 140],
  [100, 140, 240],
  [240, 200, 100],
  [200, 100, 220],
  [100, 220, 220],
  [220, 140, 100],
  [140, 220, 140],
  [200, 50, 150],
  [50, 200, 150],
  [150, 50, 200],
  [200, 150, 50],
  [50, 150, 200],
  [150, 200, 50],
  [180, 80, 180],
  [80, 180, 80],
  [80, 80, 180],
  [180, 180, 80],
  [120, 60, 180],
  [60, 180, 60],
  [180, 120, 60],
  [100, 100, 100],
  [160, 60, 160],
  [60, 160, 160],
];
for (let i = 0; i < 32; i++) {
  fs.writeFileSync(
    path.join(dirs.images, `${i + 1}.png`),
    makePng(64, 64, colors[i])
  );
}
for (let i = 0; i < 4; i++) {
  const c = [220, 80, 80];
  fs.writeFileSync(
    path.join(dirs.flagged, `${9 + i}.png`),
    makePng(64, 64, c)
  );
}

console.log(
  "generated:",
  fs.readdirSync(dirs.images).length,
  "images +",
  fs.readdirSync(dirs.flagged).length,
  "flagged"
);
