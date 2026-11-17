/* Lookbook carousel hero (plain JavaScript, no libraries).

   A ring of pictures in CSS 3D. It moves one picture at a time and holds each at the front for 5 seconds;
   only the front picture's headline, subheadline and button are shown. You can drag or throw the ring,
   use the arrow buttons or keys, pause it, and the ring leans gently toward the mouse pointer.

   Safety: with reduced motion the ring never moves by itself, never leans and changes picture without
   animation. It also pauses while hovered, focused, off screen or in a background tab. Without this script
   the pictures stay a scrollable row and the first slide's words show. */
(function () {
  "use strict";
  var root = document.querySelector("[data-lookbook]");
  if (!root) return;

  var stage = root.querySelector("[data-lb-stage]");
  var camera = root.querySelector("[data-lb-camera]");
  var ring = root.querySelector("[data-lb-ring]");
  var cards = Array.prototype.slice.call(root.querySelectorAll("[data-lb-card]"));
  var texts = Array.prototype.slice.call(root.querySelectorAll("[data-lb-text]"));
  var currentLabel = root.querySelector("[data-lb-current]");
  var prevBtn = root.querySelector("[data-lb-prev]");
  var nextBtn = root.querySelector("[data-lb-next]");
  var toggleBtn = root.querySelector("[data-lb-toggle]");
  var toggleLabel = root.querySelector("[data-lb-toggle-label]");
  var n = cards.length;
  if (!stage || !camera || !ring || n < 3 || texts.length !== n) return;

  var HOLD = 5000;                       // how long a picture stays at the front, in ms
  var STEP = 360 / n;
  var reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  var reduced = reduceQuery.matches;
  reduceQuery.addEventListener && reduceQuery.addEventListener("change", function (e) { reduced = e.matches; applyMotionPreference(); });

  var radius = 300;
  var angle = 0;          // what is drawn
  var target = 0;         // where it is heading (always a multiple of STEP unless dragging)
  var shown = 0;          // index whose words are visible
  var yaw = 0, pitch = 0, aimYaw = 0, aimPitch = 0;
  var playing = !reduced; // the visitor's choice (Pause button)
  var hovering = false, focused = false, onScreen = true, dragging = false;
  var raf = 0, last = 0, timer = 0;

  function wrap(deg) { return ((((deg + 180) % 360) + 360) % 360) - 180; }
  function indexOf(deg) { return ((Math.round(-deg / STEP) % n) + n) % n; }

  /* ---------- layout ---------- */
  function measure() {
    var width = stage.clientWidth || 320;
    var w = Math.max(150, Math.min(300, width * 0.4));
    root.style.setProperty("--lb-w", w + "px");
    var gap = w * 0.12;
    radius = Math.max((w + gap) / (2 * Math.sin(Math.PI / n)), w * 0.9);
    stage.style.perspective = Math.round(w * 5.5) + "px";
    cards.forEach(function (card, i) {
      card.style.transform = "rotateY(" + (i * STEP) + "deg) translateZ(" + radius + "px)";
    });
    draw();
  }

  /* ---------- drawing ---------- */
  function draw() {
    ring.style.transform = "translateZ(" + (-radius) + "px) rotateY(" + angle + "deg)";
    camera.style.transform = "rotateX(" + pitch + "deg) rotateY(" + yaw + "deg)";
    for (var i = 0; i < n; i++) {
      var facing = Math.cos(wrap(i * STEP + angle) * Math.PI / 180);
      var card = cards[i];
      card.style.opacity = facing <= 0.02 ? "0" : String(0.3 + 0.7 * facing);
      card.style.visibility = facing <= 0.02 ? "hidden" : "";
    }
    root.style.setProperty("--lb-px", (yaw * 3).toFixed(2));
    root.style.setProperty("--lb-py", (pitch * 3).toFixed(2));
  }

  function showWords(i) {
    if (i === shown && texts[i].getAttribute("data-active") === "true") return;
    texts.forEach(function (el, k) {
      var on = k === i;
      if (on) el.setAttribute("data-active", "true"); else el.removeAttribute("data-active");
      el.setAttribute("aria-hidden", on ? "false" : "true");
    });
    shown = i;
    if (currentLabel) currentLabel.textContent = String(i + 1).padStart(2, "0");
  }
  function hideWords() {
    texts.forEach(function (el) { el.removeAttribute("data-active"); el.setAttribute("aria-hidden", "true"); });
  }

  /* ---------- animation loop (runs only while something is moving) ---------- */
  function frame(now) {
    raf = 0;
    var dt = last ? Math.min((now - last) / 1000, 0.05) : 1 / 60;
    last = now;
    var moving = false;

    if (!dragging) {
      var ease = 1 - Math.exp(-dt / 0.2);
      angle += (target - angle) * ease;
      if (Math.abs(target - angle) < 0.03) angle = target; else moving = true;
    }
    var lean = 1 - Math.exp(-dt / 0.3);
    yaw += (aimYaw - yaw) * lean;
    pitch += (aimPitch - pitch) * lean;
    if (Math.abs(aimYaw - yaw) > 0.01 || Math.abs(aimPitch - pitch) > 0.01) moving = true; else { yaw = aimYaw; pitch = aimPitch; }

    // The words appear once the picture is (nearly) at the front, and go as soon as it leaves.
    var nearest = indexOf(angle);
    var close = Math.abs(wrap(angle + nearest * STEP)) < STEP * 0.22;
    if (close && !dragging) { if (nearest !== shown || texts[nearest].getAttribute("data-active") !== "true") showWords(nearest); }
    else hideWords();

    draw();
    if (moving || dragging) raf = requestAnimationFrame(frame); else last = 0;
  }
  function wake() { if (!raf) raf = requestAnimationFrame(frame); }

  /* ---------- moving between pictures ---------- */
  function goTo(i) {
    var desired = -i * STEP;
    target = target + wrap(desired - target);
    if (reduced) { angle = target; }
    wake();
    schedule();
  }
  function by(dir) { goTo(indexOf(target) + dir); }

  /* ---------- autoplay: one picture at a time, 5 seconds at the front ---------- */
  function canPlay() { return playing && !reduced && !hovering && !focused && onScreen && !dragging && !document.hidden; }
  function schedule() {
    clearTimeout(timer);
    if (!canPlay()) return;
    timer = setTimeout(function () { by(1); }, HOLD + 700);   // 700ms is the glide itself
  }

  function setPlaying(value) {
    playing = value;
    if (toggleBtn) toggleBtn.setAttribute("aria-pressed", playing ? "false" : "true");
    if (toggleLabel) toggleLabel.textContent = playing ? "Pause" : "Play";
    schedule();
  }
  function applyMotionPreference() {
    if (reduced) { playing = false; aimYaw = aimPitch = 0; angle = target; }
    if (toggleBtn) toggleBtn.hidden = reduced;
    setPlaying(playing);
    wake();
  }

  /* ---------- pointer: drag / throw, click a picture, lean toward the cursor ---------- */
  var startX = 0, startAngle = 0, moved = 0, lastX = 0, lastT = 0, speed = 0, captured = false, pointerId = 0;
  var DEG_PER_PX = 0.28;

  stage.addEventListener("pointerdown", function (e) {
    if (e.button !== undefined && e.button !== 0) return;
    dragging = true; captured = false; pointerId = e.pointerId; moved = 0; startX = lastX = e.clientX; lastT = e.timeStamp; speed = 0; startAngle = angle;
    clearTimeout(timer);
    wake();
  });
  stage.addEventListener("pointermove", function (e) {
    if (dragging) {
      var dx = e.clientX - startX;
      moved = Math.max(moved, Math.abs(dx));
      // Only capture the pointer once it is really a drag, so a plain tap still reaches the picture's button.
      if (moved > 5 && !captured) { captured = true; try { stage.setPointerCapture(pointerId); } catch (err) { /* not critical */ } }
      if (moved > 5) angle = startAngle + dx * DEG_PER_PX;
      var dt = Math.max(e.timeStamp - lastT, 1);
      speed = (e.clientX - lastX) * DEG_PER_PX / dt * 1000;   // degrees per second
      lastX = e.clientX; lastT = e.timeStamp;
    }
  });
  function release(e) {
    if (!dragging) return;
    dragging = false;
    if (captured) { try { stage.releasePointerCapture(e.pointerId); } catch (err) { /* not critical */ } }
    if (moved > 5) {
      var throwTo = angle + Math.max(-260, Math.min(260, speed)) * 0.25;
      target = Math.round(throwTo / STEP) * STEP;
      stage.setAttribute("data-dragged", "true");
      setTimeout(function () { stage.removeAttribute("data-dragged"); }, 60);
    } else {
      target = Math.round(angle / STEP) * STEP;
    }
    wake(); schedule();
  }
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);

  cards.forEach(function (card, i) {
    card.addEventListener("click", function () {
      if (stage.hasAttribute("data-dragged")) return;     // that was a drag, not a click
      if (i !== indexOf(target)) goTo(i);
    });
  });

  root.addEventListener("pointermove", function (e) {
    if (e.pointerType === "touch" || reduced) return;
    var rect = root.getBoundingClientRect();
    var nx = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
    var ny = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
    aimYaw = Math.max(-1, Math.min(1, nx)) * 7;
    aimPitch = -Math.max(-1, Math.min(1, ny)) * 4;
    wake();
  });
  root.addEventListener("pointerenter", function (e) { if (e.pointerType !== "touch") { hovering = true; clearTimeout(timer); } });
  root.addEventListener("pointerleave", function () { hovering = false; aimYaw = aimPitch = 0; wake(); schedule(); });

  /* ---------- keyboard, buttons, focus ---------- */
  stage.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") { by(-1); e.preventDefault(); }
    else if (e.key === "ArrowRight") { by(1); e.preventDefault(); }
    else if (e.key === "Home") { goTo(0); e.preventDefault(); }
    else if (e.key === "End") { goTo(n - 1); e.preventDefault(); }
  });
  if (prevBtn) prevBtn.addEventListener("click", function () { by(-1); });
  if (nextBtn) nextBtn.addEventListener("click", function () { by(1); });
  if (toggleBtn) toggleBtn.addEventListener("click", function () { setPlaying(!playing); });
  // Only keyboard focus pauses the carousel; clicking a button with the mouse must not leave it stuck.
  root.addEventListener("focusin", function (e) {
    var keyboard = false;
    try { keyboard = e.target.matches(":focus-visible"); } catch (err) { keyboard = true; }
    if (keyboard) { focused = true; clearTimeout(timer); }
  });
  root.addEventListener("focusout", function () {
    setTimeout(function () {
      var active = document.activeElement, keyboard = false;
      try { keyboard = !!active && root.contains(active) && active.matches(":focus-visible"); } catch (err) { keyboard = root.contains(active); }
      focused = keyboard;
      schedule();
    }, 0);
  });

  document.addEventListener("visibilitychange", function () { if (document.hidden) clearTimeout(timer); else schedule(); });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) { onScreen = entries[0].isIntersecting; if (onScreen) schedule(); else clearTimeout(timer); }, { threshold: 0.25 }).observe(root);
  }
  if ("ResizeObserver" in window) new ResizeObserver(measure).observe(stage); else window.addEventListener("resize", measure);

  /* ---------- start ---------- */
  texts.forEach(function (el, k) { el.setAttribute("aria-hidden", k === 0 ? "false" : "true"); });
  root.classList.add("lb--3d");
  measure();
  applyMotionPreference();
  var firstImage = cards[0].querySelector("img");
  function ready() { root.classList.add("is-ready"); schedule(); }
  if (firstImage && !firstImage.complete) { firstImage.addEventListener("load", ready, { once: true }); firstImage.addEventListener("error", ready, { once: true }); setTimeout(ready, 2500); } else ready();
  wake();
})();
