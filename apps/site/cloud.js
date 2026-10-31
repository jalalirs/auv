/**
 * The drifting cloud of renders on the front page.
 *
 * Cards sit on a cylinder, each turned by its share of a circle and pushed out
 * to a radius, with height, radius, scale and tilt scattered so nothing lines
 * up. The far ones are blurred and faded by depth. The scatter comes from a
 * fixed seed, so the arrangement is the same on every load.
 *
 * Every picture is a render of ours: corals from the colony library, and frames
 * from dives over places we built.
 */

const COUNT = 20;

const CARDS = Array.from({ length: COUNT }, (_, index) =>
  new URL(`./assets/cloud/reef-${String(index + 1).padStart(2, "0")}.webp`, import.meta.url).href
);

const DRIFT = 3.5;        // degrees per second while nothing touches it
const FRICTION = 0.94;    // spin kept per frame after a drag
const SENSITIVITY = 0.2;  // degrees per pixel dragged
const RADIUS = 660;
const CARD_WIDTH = 190;

function seeded(seed) {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

export function mountCloud(root) {
  if (!root) return;

  const random = seeded(20261031);
  const ring = document.createElement("div");
  ring.className = "cloud-ring";

  const step = 360 / COUNT;
  const placed = CARDS.map((src, index) => {
    const card = document.createElement("div");
    card.className = "cloud-card";

    const angle = index * step + (random() - 0.5) * step * 0.55;
    const radius = RADIUS * (0.78 + random() * 0.34);
    const lift = (random() - 0.5) * 190;
    const scale = 0.58 + random() * 0.42;
    const tilt = (random() - 0.5) * 7;

    card.style.width = `${CARD_WIDTH}px`;
    card.style.transform =
      `rotateY(${angle}deg) translateZ(${radius}px) ` +
      `translateY(${lift}px) rotateZ(${tilt}deg) scale(${scale})`;

    const image = document.createElement("img");
    image.src = src;
    image.alt = "";
    image.loading = index < 6 ? "eager" : "lazy";
    image.decoding = "async";
    image.draggable = false;
    card.append(image);
    ring.append(card);
    return { card, angle, radius };
  });

  root.append(ring);

  let rotation = 0;
  let velocity = DRIFT;
  let dragging = false;
  let lastX = 0;
  let lastTime = performance.now();
  const stillness = window.matchMedia("(prefers-reduced-motion: reduce)");

  // Blur, fade and stacking depend on where each card has turned to.
  const depth = () => {
    for (const { card, angle, radius } of placed) {
      const z = Math.cos(((angle + rotation) * Math.PI) / 180) * radius;
      const nearness = (z / radius + 1) / 2;
      card.style.opacity = String(0.18 + nearness * 0.82);
      card.style.filter = `blur(${((1 - nearness) * 7).toFixed(2)}px)`;
      card.style.zIndex = String(Math.round(nearness * 100));
    }
  };

  const frame = (now) => {
    const elapsed = Math.min((now - lastTime) / 1000, 0.05);
    lastTime = now;
    if (!dragging && !stillness.matches) {
      velocity += (DRIFT - velocity) * (1 - FRICTION);
      rotation += velocity * elapsed;
    }
    // Pushed back by the radius so the near face sits at the screen plane.
    ring.style.transform = `translateZ(${-RADIUS}px) rotateY(${rotation}deg)`;
    depth();
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  root.addEventListener("pointerdown", (event) => {
    dragging = true;
    lastX = event.clientX;
    root.dataset.dragging = "true";
    root.setPointerCapture(event.pointerId);
  });

  root.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const moved = event.clientX - lastX;
    lastX = event.clientX;
    rotation += moved * SENSITIVITY;
    velocity = moved * SENSITIVITY * 8;
  });

  const release = () => {
    dragging = false;
    root.dataset.dragging = "false";
  };
  root.addEventListener("pointerup", release);
  root.addEventListener("pointercancel", release);
}
