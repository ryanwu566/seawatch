// Generates a lightweight vector ship icon as an ImageData for MapLibre's
// addImage(), so vessels render in a single symbol layer (no DOM per vessel).
// The symbol is a simple ship/arrow silhouette pointing "up" (north); MapLibre
// rotates it per-feature via icon-rotate bound to the vessel orientation.

/** Draw a ship silhouette into an offscreen canvas and return its ImageData. */
export function makeShipIcon(size = 48, color = "#e2e8f0", stroke = "#04121f"): ImageData | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const c = size / 2;
  ctx.clearRect(0, 0, size, size);
  ctx.translate(c, c);

  // Ship hull: pointed bow (top), squared stern (bottom).
  const w = size * 0.26; // half-beam
  const bow = -size * 0.42;
  const mid = -size * 0.1;
  const stern = size * 0.4;

  ctx.beginPath();
  ctx.moveTo(0, bow); // bow tip
  ctx.lineTo(w, mid); // starboard shoulder
  ctx.lineTo(w * 0.8, stern); // starboard stern
  ctx.lineTo(-w * 0.8, stern); // port stern
  ctx.lineTo(-w, mid); // port shoulder
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = Math.max(1, size * 0.04);
  ctx.strokeStyle = stroke;
  ctx.stroke();

  return ctx.getImageData(0, 0, size, size);
}
