/**
 * Cropping the saved photos, the way the scanning apps do it.
 *
 * Heystack shoots the whole frame and crops afterwards in software, and
 * that is the better order: the camera keeps every pixel, and the crop
 * can be redone or undone without reshooting. The phone's own crop is
 * still there for people who want it tight straight away.
 *
 * Runs in the browser because the canvas is already here and a Worker
 * would need an image library to do the same thing.
 */

/** Finds the card in an image. Same rules as the scanner, same guards. */
export function findCardBox(img: HTMLImageElement): { x: number; y: number; w: number; h: number } | null {
  const W = 220, H = Math.max(1, Math.round((img.naturalHeight / img.naturalWidth) * W));
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const x = c.getContext('2d', { willReadFrequently: true })!;
  x.drawImage(img, 0, 0, W, H);
  const d = x.getImageData(0, 0, W, H).data;
  const lum = new Float32Array(W * H);
  for (let i = 0, p = 0; i < d.length; i += 4, p++)
    lum[p] = d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114;

  let edge = 0, edgeN = 0, mid = 0, midN = 0;
  for (let y = 0; y < H; y++) for (let xx = 0; xx < W; xx++) {
    const v = lum[y * W + xx];
    if (xx < W * 0.06 || xx > W * 0.94 || y < H * 0.06 || y > H * 0.94) { edge += v; edgeN++; }
    else if (xx > W * 0.35 && xx < W * 0.65 && y > H * 0.35 && y < H * 0.65) { mid += v; midN++; }
  }
  const lighter = mid / Math.max(1, midN) > edge / Math.max(1, edgeN);
  const cut = (mid / Math.max(1, midN) + edge / Math.max(1, edgeN)) / 2;

  const col = new Uint16Array(W), row = new Uint16Array(H);
  for (let y = 0; y < H; y++) for (let xx = 0; xx < W; xx++) {
    const on = lighter ? lum[y * W + xx] > cut : lum[y * W + xx] < cut;
    if (on) { col[xx]++; row[y]++; }
  }
  const span = (hits: Uint16Array, n: number, other: number) => {
    const need = other * 0.30;
    let best: [number, number] | null = null, run: number | null = null;
    for (let i = 0; i < n; i++) {
      if (hits[i] >= need) { if (run === null) run = i; }
      else if (run !== null) {
        if (!best || i - run > best[1] - best[0]) best = [run, i];
        run = null;
      }
    }
    if (run !== null && (!best || n - run > best[1] - best[0])) best = [run, n];
    return best;
  };
  const cs = span(col, W, H), rs = span(row, H, W);
  if (!cs || !rs) return null;

  let sx = cs[0] / W, ex = cs[1] / W, sy = rs[0] / H, ey = rs[1] / H;
  const fw = ex - sx, fh = ey - sy;
  // The same three guards. A first version wanted to crop a photo where
  // the card already filled the frame, and would have sliced it in half.
  if (fw * fh > 0.78) return null;                       // already fills it
  const ratio = (fw * img.naturalWidth) / Math.max(1, fh * img.naturalHeight);
  if (!((ratio > 0.45 && ratio < 0.95) || (ratio > 1.05 && ratio < 2.2))) return null;
  if (fw < 0.15 || fh < 0.15) return null;

  const pad = 0.035;
  sx = Math.max(0, sx - pad); sy = Math.max(0, sy - pad);
  ex = Math.min(1, ex + pad); ey = Math.min(1, ey + pad);
  return {
    x: Math.round(sx * img.naturalWidth), y: Math.round(sy * img.naturalHeight),
    w: Math.round((ex - sx) * img.naturalWidth), h: Math.round((ey - sy) * img.naturalHeight),
  };
}

const load = (url: string) => new Promise<HTMLImageElement>((res, rej) => {
  const i = new Image();
  i.crossOrigin = 'anonymous';
  i.onload = () => res(i);
  i.onerror = () => rej(new Error('could not load that photo'));
  i.src = url;
});

/**
 * Crops one photo to its card and stands it up.
 *
 * Returns null when nothing should change, so a photo that is already
 * right is left exactly as it is rather than re-encoded for nothing.
 */
export async function cropToCard(url: string): Promise<Blob | null> {
  const img = await load(url);
  const box = findCardBox(img);
  const landscape = (box ? box.w > box.h : img.naturalWidth > img.naturalHeight);
  if (!box && !landscape) return null;

  const sx = box?.x ?? 0, sy = box?.y ?? 0;
  const sw = box?.w ?? img.naturalWidth, sh = box?.h ?? img.naturalHeight;

  const c = document.createElement('canvas');
  // A card stands up. Anything landscape is lying down and gets turned.
  c.width = landscape ? sh : sw;
  c.height = landscape ? sw : sh;
  const x = c.getContext('2d')!;
  if (landscape) {
    x.translate(c.width / 2, c.height / 2);
    x.rotate(-Math.PI / 2);
    x.drawImage(img, sx, sy, sw, sh, -sw / 2, -sh / 2, sw, sh);
  } else {
    x.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
  }
  return new Promise((res) => c.toBlob((b) => res(b), 'image/jpeg', 0.92));
}
