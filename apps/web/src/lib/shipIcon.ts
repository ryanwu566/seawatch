// Generates a lightweight vector ship icon as an ImageData for MapLibre's
// addImage(), so vessels render in a single symbol layer (no DOM per vessel).
// The symbol is a simple ship/arrow silhouette pointing "up" (north); MapLibre
// rotates it per-feature via icon-rotate bound to the vessel orientation.

/** Draw a ship silhouette into an offscreen canvas and return its ImageData. */
export function makeShipIcon(size = 64, color = "#ffffff", stroke = "#04121f"): ImageData | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const c = size / 2;
  ctx.clearRect(0, 0, size, size);
  ctx.translate(c, c);

  // Directional vessel silhouette: sharp bow (top/north), tapered hull, flat
  // stern. Reads as a ship/arrow and rotates cleanly to heading/COG.
  const w = size * 0.22; // half-beam
  const bow = -size * 0.44;
  const shoulder = -size * 0.14;
  const stern = size * 0.38;

  ctx.beginPath();
  ctx.moveTo(0, bow); // bow tip
  ctx.lineTo(w, shoulder); // starboard shoulder
  ctx.lineTo(w * 0.72, stern); // starboard quarter
  ctx.lineTo(-w * 0.72, stern); // port quarter
  ctx.lineTo(-w, shoulder); // port shoulder
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = Math.max(1.5, size * 0.045);
  ctx.strokeStyle = stroke;
  ctx.lineJoin = "round";
  ctx.stroke();

  return ctx.getImageData(0, 0, size, size);
}
