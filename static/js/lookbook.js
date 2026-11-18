/* Lookbook hero (plain JavaScript, no libraries).

   Cut-out models stand in a row. The front one is large and sharp, the others shrink, fade and blur with distance.
   It moves one look at a time and holds each at the front for 5 seconds. While it moves, the hero's background colour
   is blended between the two looks involved and the text colour flips by contrast. Only the front look's name,
   description and buy panel are shown. The models lean toward the cursor; you can also drag or throw them, use the
   arrows or keys, click a model, or pause.

   Buy panel: colours and sizes come from the product's real variants (stock included). "Add to bag" uses the site's
   cart (window.Avelle.addToCart); without JavaScript the same form posts to the cart.

   Safety: reduced motion means no autoplay, no lean and instant changes. It pauses while the buy panel is hovered or
   used, on keyboard focus, off screen and in a background tab. */
(function () {
  "use strict";
  var root = document.querySelector("[data-lookbook]");
  if (!root) return;

  var stage = root.querySelector("[data-lb-stage]");
  var cards = Array.prototype.slice.call(root.querySelectorAll("[data-lb-card]"));
  var words = Array.prototype.slice.call(root.querySelectorAll("[data-lb-word]"));
  var texts = Array.prototype.slice.call(root.querySelectorAll("[data-lb-text]"));
  var panel = root.querySelector("[data-lb-panel]");
  var currentLabel = root.querySelector("[data-lb-current]");
  var prevBtn = root.querySelector("[data-lb-prev]");
  var nextBtn = root.querySelector("[data-lb-next]");
  var toggleBtn = root.querySelector("[data-lb-toggle]");
  var toggleLabel = root.querySelector("[data-lb-toggle-label]");
  var bar = root.querySelector("[data-lb-progress]");
  var n = cards.length;
  if (!stage || n < 3 || texts.length !== n) return;

  var data = [];
  try { data = JSON.parse(document.getElementById("lb-data").textContent) || []; } catch (err) { data = []; }
  var HOLD = 5000, GLIDE = 700;                        // ms at the front, ms to move one step
  root.style.setProperty("--lb-hold", HOLD + "ms");
  root.style.setProperty("--lb-glide", GLIDE + "ms");

  var reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  var reduced = reduceQuery.matches;
  if (reduceQuery.addEventListener) reduceQuery.addEventListener("change", function (e) { reduced = e.matches; applyMotionPreference(); });

  var pos = 0;             // what is drawn, in "looks" (0 = first look at the front)
  var target = 0;          // where it is heading (a whole number unless dragging)
  var shown = 0;           // look whose panel is visible
  var yaw = 0, pitch = 0, aimX = 0, aimY = 0;
  var spacing = 200;
  var playing = !reduced;  // the visitor's choice (Pause / buy panel use)
  var hovering = false, focused = false, onScreen = true, dragging = false;
  var raf = 0, last = 0, timer = 0, tone = root.getAttribute("data-tone");

  function mod(v) { return ((v % n) + n) % n; }
  function wrapDelta(v) { v = mod(v); return v >= n / 2 ? v - n : v; }          // shortest signed distance, in looks
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* ---------- colour ---------- */
  function rgb(hex) { var h = String(hex || "#E9E1D2").replace("#", ""); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; }
  var colours = texts.map(function (el, i) { return rgb(data[i] && data[i].bg); });
  function lin(c) { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
  function lum(c) { return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]); }
  var DARK_LUM = lum([23, 23, 23]), LIGHT_LUM = lum([250, 248, 244]);   // the two inks in lookbook.css
  function wantsLightText(c) {   // same rule as the server: whichever ink contrasts more
    var l = lum(c);
    return (LIGHT_LUM + 0.05) / (l + 0.05) > (l + 0.05) / (DARK_LUM + 0.05);
  }
  function blend(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function paintBackground() {
    var base = Math.floor(pos), t = pos - base;
    var from = colours[mod(base)], to = colours[mod(base + 1)];
    var c = blend(from, to, t * t * (3 - 2 * t));
    root.style.setProperty("--lb-bg", "rgb(" + Math.round(c[0]) + "," + Math.round(c[1]) + "," + Math.round(c[2]) + ")");
    var next = wantsLightText(c) ? "light" : "dark";
    if (next !== tone) { tone = next; root.setAttribute("data-tone", tone); }
  }

  /* ---------- layout ---------- */
  function measure() { spacing = Math.max(70, (stage.clientWidth || 320) * (window.innerWidth < 600 ? 0.27 : 0.24)); draw(); }

  /* ---------- drawing ---------- */
  function draw() {
    for (var i = 0; i < n; i++) {
      var d = wrapDelta(i - pos), a = Math.abs(d), card = cards[i];
      var opacity = a <= 1 ? 1 - 0.4 * a : 0.6 - 0.35 * (a - 1);
      if (opacity <= 0.02) { card.style.visibility = "hidden"; card.style.opacity = "0"; }
      else {
        var x = spacing * Math.sign(d) * (a < 1 ? a : 1 + (a - 1) * 0.82);
        var scale = Math.max(0.45, 1 - 0.2 * Math.min(a, 2.6));
        var turn = reduced ? 0 : yaw * (1 - 0.35 * Math.min(a, 2));
        card.style.visibility = "";
        card.style.opacity = opacity.toFixed(3);
        card.style.zIndex = String(100 - Math.round(a * 10));
        card.style.filter = a < 0.35 ? "" : "blur(" + Math.min(2.6, a * 1.1).toFixed(2) + "px)";
        card.style.transform = "translate3d(calc(-50% + " + x.toFixed(1) + "px)," + (-Math.min(a, 2) * 12).toFixed(1) + "px,0) rotateY(" + turn.toFixed(2) + "deg) scale(" + scale.toFixed(3) + ")";
      }
      if (words[i]) words[i].style.opacity = (0.075 * Math.max(0, 1 - a * 1.25)).toFixed(4);
    }
    root.style.setProperty("--lb-aim-x", aimX.toFixed(3));
    root.style.setProperty("--lb-aim-y", aimY.toFixed(3));
    paintBackground();
  }

  function showPanel(i) {
    if (i === shown && texts[i].getAttribute("data-active") === "true") return;
    texts.forEach(function (el, k) {
      var on = k === i;
      if (on) el.setAttribute("data-active", "true"); else el.removeAttribute("data-active");
      el.setAttribute("aria-hidden", on ? "false" : "true");
    });
    shown = i;
    if (currentLabel) currentLabel.textContent = String(i + 1).padStart(2, "0");
  }
  function hidePanel() { texts.forEach(function (el) { el.removeAttribute("data-active"); el.setAttribute("aria-hidden", "true"); }); }

  /* ---------- animation loop (runs only while something is moving) ---------- */
  function frame(now) {
    raf = 0;
    var dt = last ? Math.min((now - last) / 1000, 0.05) : 1 / 60;
    last = now;
    var moving = false;

    if (!dragging) {
      pos += (target - pos) * (1 - Math.exp(-dt / 0.22));
      if (Math.abs(target - pos) < 0.002) pos = target; else moving = true;
    }
    var lean = 1 - Math.exp(-dt / 0.3), ty = reduced ? 0 : aimX * 8, tp = reduced ? 0 : -aimY * 3;
    yaw += (ty - yaw) * lean; pitch += (tp - pitch) * lean;
    if (Math.abs(ty - yaw) > 0.01 || Math.abs(tp - pitch) > 0.01) moving = true; else { yaw = ty; pitch = tp; }

    // The panel appears once a look is (nearly) at the front and goes as soon as it leaves.
    var nearest = mod(Math.round(pos));
    if (!dragging && Math.abs(pos - Math.round(pos)) < 0.2) showPanel(nearest); else hidePanel();

    draw();
    if (moving || dragging) raf = requestAnimationFrame(frame); else last = 0;
  }
  function wake() { if (!raf) raf = requestAnimationFrame(frame); }

  /* ---------- moving between looks ---------- */
  function goTo(i) {
    target = Math.round(target) + wrapDelta(i - Math.round(target));
    if (reduced) pos = target;
    wake(); schedule();
  }
  function by(dir) { goTo(mod(Math.round(target)) + dir); }

  /* ---------- autoplay: one look at a time, 5 seconds at the front ---------- */
  function canPlay() { return playing && !reduced && !hovering && !focused && onScreen && !dragging && !document.hidden; }
  function schedule() {
    clearTimeout(timer);
    var run = canPlay();
    if (bar) { bar.removeAttribute("data-run"); if (run) { void bar.offsetWidth; bar.setAttribute("data-run", ""); } }
    if (run) timer = setTimeout(function () { by(1); }, HOLD + GLIDE);
  }
  function setPlaying(value) {
    playing = value;
    if (toggleBtn) toggleBtn.setAttribute("aria-pressed", playing ? "false" : "true");
    if (toggleLabel) toggleLabel.textContent = playing ? "Pause" : "Play";
    schedule();
  }
  function applyMotionPreference() {
    if (reduced) { playing = false; aimX = aimY = 0; pos = target; }
    if (toggleBtn) toggleBtn.hidden = reduced;
    setPlaying(playing);
    wake();
  }

  /* ---------- pointer: drag / throw, click a look, lean toward the cursor ---------- */
  var startX = 0, startPos = 0, moved = 0, lastX = 0, lastT = 0, speed = 0, captured = false, pointerId = 0;
  stage.addEventListener("pointerdown", function (e) {
    if (e.button !== undefined && e.button !== 0) return;
    dragging = true; captured = false; pointerId = e.pointerId; moved = 0; startX = lastX = e.clientX; lastT = e.timeStamp; speed = 0; startPos = pos;
    clearTimeout(timer); wake();
  });
  stage.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    var dx = e.clientX - startX;
    moved = Math.max(moved, Math.abs(dx));
    // Capture the pointer only once it is a real drag, so a plain tap still reaches a model's button.
    if (moved > 5 && !captured) { captured = true; try { stage.setPointerCapture(pointerId); } catch (err) { /* not critical */ } }
    if (moved > 5) pos = startPos - dx / spacing;
    var dt = Math.max(e.timeStamp - lastT, 1);
    speed = -(e.clientX - lastX) / spacing / dt * 1000;      // looks per second
    lastX = e.clientX; lastT = e.timeStamp;
  });
  function release(e) {
    if (!dragging) return;
    dragging = false;
    if (captured) { try { stage.releasePointerCapture(e.pointerId); } catch (err) { /* not critical */ } }
    if (moved > 5) {
      target = Math.round(pos + clamp(speed, -6, 6) * 0.22);
      stage.setAttribute("data-dragged", "true");
      setTimeout(function () { stage.removeAttribute("data-dragged"); }, 60);
    } else target = Math.round(pos);
    wake(); schedule();
  }
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);

  cards.forEach(function (card, i) {
    card.addEventListener("click", function () {
      if (stage.hasAttribute("data-dragged")) return;       // that was a drag, not a click
      if (i !== mod(Math.round(target))) goTo(i);
    });
  });

  root.addEventListener("pointermove", function (e) {
    if (e.pointerType === "touch" || reduced) return;
    var rect = stage.getBoundingClientRect();
    aimX = clamp(((e.clientX - rect.left) / rect.width - 0.5) * 2, -1, 1);
    aimY = clamp(((e.clientY - rect.top) / rect.height - 0.5) * 2, -1, 1);
    wake();
  });
  root.addEventListener("pointerleave", function () { aimX = aimY = 0; wake(); });
  // Hovering the buy panel pauses autoplay (the visitor is reading or choosing); hovering the models does not.
  if (panel) {
    panel.addEventListener("pointerenter", function (e) { if (e.pointerType !== "touch") { hovering = true; schedule(); } });
    panel.addEventListener("pointerleave", function () { hovering = false; schedule(); });
  }

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
  // Only keyboard focus pauses; clicking with the mouse must not leave autoplay stuck.
  root.addEventListener("focusin", function (e) {
    var keyboard = false;
    try { keyboard = e.target.matches(":focus-visible"); } catch (err) { keyboard = true; }
    if (keyboard) { focused = true; clearTimeout(timer); schedule(); }
  });
  root.addEventListener("focusout", function () {
    setTimeout(function () {
      var active = document.activeElement, keyboard = false;
      try { keyboard = !!active && root.contains(active) && active.matches(":focus-visible"); } catch (err) { keyboard = root.contains(active); }
      focused = keyboard; schedule();
    }, 0);
  });
  document.addEventListener("visibilitychange", schedule);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) { onScreen = entries[0].isIntersecting; schedule(); }, { threshold: 0.25 }).observe(root);
  }
  if ("ResizeObserver" in window) new ResizeObserver(measure).observe(stage); else window.addEventListener("resize", measure);

  /* ---------- buy panels ---------- */
  function symbolOf(text) { return String(text).replace(/[\d.,\s]/g, ""); }
  texts.forEach(function (el, k) {
    var form = el.querySelector("[data-lb-form]");
    if (!form) return;
    var variants = (data[k] && data[k].variants) || [];
    var colourInputs = Array.prototype.slice.call(form.querySelectorAll('input[name="colour"]'));
    var sizeInputs = Array.prototype.slice.call(form.querySelectorAll('input[name="size"]'));
    var addBtn = form.querySelector("[data-lb-add]");
    var msg = form.querySelector("[data-lb-msg]");
    var price = form.querySelector("[data-lb-price]");
    var symbol = price ? symbolOf(price.textContent) : "";

    function chosen(inputs) { var c = inputs.filter(function (i) { return i.checked; })[0]; return c ? Number(c.value) : null; }
    function find() {
      var colour = chosen(colourInputs), size = chosen(sizeInputs);
      if ((colourInputs.length && colour === null) || (sizeInputs.length && size === null)) return null;
      return variants.filter(function (v) { return (colour === null || v.colour === colour) && (size === null || v.size === size); })[0] || null;
    }
    function say(text, state) { if (msg) { msg.textContent = text; if (state) msg.setAttribute("data-state", state); else msg.removeAttribute("data-state"); } }
    function refresh() {
      var colour = chosen(colourInputs), size = chosen(sizeInputs);
      sizeInputs.forEach(function (input) {
        var ok = variants.some(function (v) { return v.size === Number(input.value) && (colour === null || v.colour === colour) && v.qty > 0; });
        input.disabled = !ok; if (!ok && input.checked) input.checked = false;
      });
      colourInputs.forEach(function (input) {
        var ok = variants.some(function (v) { return v.colour === Number(input.value) && (size === null || v.size === size) && v.qty > 0; });
        input.disabled = !ok; if (!ok && input.checked) input.checked = false;
      });
      ["colour", "size"].forEach(function (name) {
        var label = form.querySelector('[data-lb-chosen="' + name + '"]');
        var input = (name === "colour" ? colourInputs : sizeInputs).filter(function (i) { return i.checked; })[0];
        if (label) label.textContent = input ? input.getAttribute("data-name") : "";
      });
      if (!variants.some(function (x) { return x.qty > 0; })) { say("Sold out", "error"); if (addBtn) addBtn.disabled = true; return; }
      var v = find();
      if (v && price) price.textContent = symbol + Number(v.price).toLocaleString("en-NG", { maximumFractionDigits: 0 });
      if (v && v.qty <= 0) say("Sold out", "error");
      else if (v && v.qty <= 3) say("Only " + v.qty + " left", "");
      else say("", "");
      if (addBtn) addBtn.disabled = !!(v && v.qty <= 0);
    }
    form.addEventListener("change", function () {
      refresh();
      if (playing) setPlaying(false);              // the visitor is choosing: stop the carousel moving under them
    });
    form.addEventListener("submit", function (e) {
      var v = find();
      if (!v) { e.preventDefault(); say("Please choose " + (colourInputs.length && chosen(colourInputs) === null ? "a colour" : "a size") + ".", "error"); return; }
      if (v.qty <= 0) { e.preventDefault(); return; }
      if (window.Avelle && typeof window.Avelle.addToCart === "function") {
        e.preventDefault();
        window.Avelle.addToCart({ variantId: v.id, quantity: 1 }, addBtn).then(function (res) {
          if (res && res.ok) say("Added to your bag.", "");
          else if (res && res.message) say(res.message, "error");
        });
        if (playing) setPlaying(false);
      }
    });
    refresh();
  });

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
