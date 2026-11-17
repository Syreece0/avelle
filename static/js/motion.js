/* ==========================================================================
   AVELLE motion system (GSAP + ScrollTrigger, enhancement only)

   Layers on a product card (each element owns exactly one kind of motion):
     .pc               ENTRANCE  GSAP x / y / scale / opacity, once, from the grid's direction
     .pc__float        FLOAT     GSAP y yoyo, slow, per-card timing, started after the entrance
     .pc__tilt         TILT      CSS variables only (--tilt-x, --tilt-y); hover lift is CSS
   The grid cell <li> is never animated, so nothing can shift the layout.

   Directions, set with data-enter on a .product-grid:
     up | left | right | mixed   (mixed: left column from the left, right column from the right,
                                  the middle from below)

   Also here: scroll reveals ([data-reveal]), parallax ([data-parallax*]),
   the shop's exit/enter hooks, and fade page transitions.

   Safety: with GSAP missing, or prefers-reduced-motion, none of this runs and every
   element stays visible and static. Phones get entrances only (no float, tilt or parallax).
   Public:  window.Avelle.motion = { active(), enter(grid, items, mode) }
   ========================================================================== */
(function () {
  "use strict";

  var root = document.documentElement;
  window.Avelle = window.Avelle || {};

  // Reduced motion: show the first frame of a hero video instead of playing it.
  (function () {
    var v = document.querySelector("[data-hero-video]");
    if (v && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { v.removeAttribute("autoplay"); v.pause(); }
  })();

  function reducedNow() { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
  function release() { root.classList.remove("motion-pending"); }

  window.Avelle.motion = { active: function () { return false; }, enter: function () {} };

  if (!window.gsap || !window.ScrollTrigger || reducedNow()) { release(); root.classList.remove("page-entering"); return; }
  gsap.registerPlugin(ScrollTrigger);

  var DESKTOP = { name: "desktop", dist: 72, rise: 60, dur: 0.95, stagger: 0.08, float: true, tilt: true, parallax: true };
  var MOBILE = { name: "mobile", dist: 36, rise: 40, dur: 0.7, stagger: 0.06, float: false, tilt: false, parallax: false };
  var cfg = null;                       // current profile while motion is active
  var live = { triggers: [], tweens: [] };
  var io = null;                        // pauses floating cards that are off screen
  var tiltAbort = null;
  var lowPower = (navigator.connection && navigator.connection.saveData) || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2);

  function track(list, item) { if (item) (Array.isArray(item) ? item : [item]).forEach(function (i) { list.push(i); }); return item; }
  function toArray(x) { return Array.prototype.slice.call(x); }
  function inView(el, pad) {
    var r = el.getBoundingClientRect(), h = window.innerHeight * (pad || 1);
    return r.bottom > 0 && r.top < h;
  }

  /* ---------------- Product card entrance + float ---------------- */
  function cellsOf(grid) { return toArray(grid.children).filter(function (li) { return li.classList.contains("product-grid__item"); }); }
  function pcsOf(items) {
    var out = [];
    items.forEach(function (li) { var pc = li.matches && li.matches(".pc") ? li : li.querySelector && li.querySelector("[data-pc]"); if (pc) out.push(pc); });
    return out;
  }
  function columnsOf(grid) {
    var lefts = [];
    cellsOf(grid).forEach(function (li) { if (lefts.indexOf(li.offsetLeft) === -1) lefts.push(li.offsetLeft); });
    return lefts.sort(function (a, b) { return a - b; });
  }
  function directionFor(pc, mode, lefts) {
    if (mode !== "mixed") return mode;
    if (lefts.length < 2 || lefts.length > 5) return "up"; // rails and single columns just rise
    var col = lefts.indexOf(pc.parentNode.offsetLeft);
    if (col === 0) return "left";
    if (col === lefts.length - 1) return "right";
    return "up";
  }
  function offsets(dir) {
    if (dir === "left") return { x: -cfg.dist, y: 0 };
    if (dir === "right") return { x: cfg.dist, y: 0 };
    return { x: 0, y: cfg.rise };
  }

  function prepare(pcs, mode, grid) {
    var lefts = mode === "mixed" ? columnsOf(grid) : [];
    pcs.forEach(function (pc) {
      var o = offsets(directionFor(pc, mode, lefts));
      pc._played = false;
      gsap.set(pc, { autoAlpha: 0, x: o.x, y: o.y, scale: 0.96 });
    });
  }

  function play(batch) {
    batch = batch.filter(function (pc) { return !pc._played; });
    if (!batch.length) return;
    batch.forEach(function (pc) { pc._played = true; });
    var tween = gsap.to(batch, {
      autoAlpha: 1, x: 0, y: 0, scale: 1, duration: cfg.dur, ease: "power3.out", stagger: cfg.stagger, overwrite: "auto",
      clearProps: "transform,opacity,visibility", // hand the element back to CSS once settled
      onComplete: function () { batch.forEach(startFloat); }
    });
    track(live.tweens, tween);
  }

  function startFloat(pc) {
    var layer = pc.querySelector("[data-pc-float]");
    if (!cfg || !cfg.float || lowPower || !layer || layer._float || !document.body.contains(layer)) return;
    var amplitude = 5 + Math.random() * 6;
    var tween = gsap.to(layer, {
      y: (Math.random() < 0.5 ? -1 : 1) * amplitude, duration: 2.8 + Math.random() * 2.4, ease: "sine.inOut",
      yoyo: true, repeat: -1, delay: Math.random() * 1.6
    });
    layer._float = tween;
    pc._floatTween = tween;
    track(live.tweens, tween);
    if (io) io.observe(pc.parentNode);
  }
  function stopFloats(root_) {
    toArray(root_.querySelectorAll("[data-pc-float]")).forEach(function (layer) {
      if (layer._float) { layer._float.kill(); layer._float = null; gsap.set(layer, { clearProps: "transform" }); }
      if (io && layer.closest(".product-grid__item")) io.unobserve(layer.closest(".product-grid__item"));
    });
  }

  function enter(grid, items, mode) {
    if (!cfg) return;
    var pcs = pcsOf(items);
    if (!pcs.length) return;
    var dir = mode === "append" ? "up" : (grid.getAttribute("data-enter") || "up");
    prepare(pcs, dir, grid);
    var batches = ScrollTrigger.batch(pcs, { start: "top 92%", once: true, interval: 0.08, batchMax: 8, onEnter: play });
    track(live.triggers, batches);
    grid._batches = (grid._batches || []).concat(batches);
    release();
    // Failsafe: anything near the viewport that never got its trigger still appears
    setTimeout(function () { play(pcs.filter(function (pc) { return !pc._played && document.body.contains(pc) && inView(pc, 1.2); })); }, 2500);
  }

  function leave(grid) {
    (grid._batches || []).forEach(function (t) { t.kill(); });
    grid._batches = [];
    stopFloats(grid);
    var pcs = toArray(grid.querySelectorAll("[data-pc]"));
    gsap.killTweensOf(pcs);
    var visible = pcs.filter(function (pc) { return inView(pc, 1); });
    if (!visible.length) return Promise.resolve();
    return new Promise(function (resolve) {
      gsap.to(visible, { autoAlpha: 0, scale: 0.97, duration: 0.24, ease: "power2.in", stagger: 0.015, overwrite: true, onComplete: resolve, onInterrupt: resolve });
    });
  }

  /* ---------------- 3D tilt (pointer devices only; CSS does the lifting) ---------------- */
  function initTilt() {
    tiltAbort = new AbortController();
    var sig = { signal: tiltAbort.signal };
    var current = null, frame = 0, last = null;

    function setFloatSpeed(el, speed) {
      var layer = el.closest("[data-pc-float]");
      if (layer && layer._float) gsap.to(layer._float, { timeScale: speed, duration: 0.5, overwrite: true });
    }
    function reset(el) {
      if (!el) return;
      el.classList.remove("is-tracking");
      el.style.setProperty("--tilt-x", "0deg");
      el.style.setProperty("--tilt-y", "0deg");
      setFloatSpeed(el, 1);
    }
    function apply() {
      frame = 0;
      if (!current || !last) return;
      var r = current.getBoundingClientRect();
      var px = Math.max(-0.5, Math.min(0.5, (last.x - r.left) / r.width - 0.5));
      var py = Math.max(-0.5, Math.min(0.5, (last.y - r.top) / r.height - 0.5));
      current.style.setProperty("--tilt-y", (px * 9).toFixed(2) + "deg");
      current.style.setProperty("--tilt-x", (-py * 7).toFixed(2) + "deg");
    }
    document.addEventListener("pointermove", function (e) {
      if (e.pointerType === "touch") return;
      var el = e.target.closest && e.target.closest("[data-pc-tilt]");
      if (el !== current) {
        reset(current);
        current = el;
        if (el) { el.classList.add("is-tracking"); setFloatSpeed(el, 0); }
      }
      if (!el) return;
      last = { x: e.clientX, y: e.clientY };
      if (!frame) frame = requestAnimationFrame(apply);
    }, sig);
    document.addEventListener("pointerleave", function () { reset(current); current = null; }, sig);
    window.addEventListener("blur", function () { reset(current); current = null; }, sig);
    window.addEventListener("scroll", function () { if (current) { reset(current); current = null; } }, { passive: true, signal: tiltAbort.signal });
    tiltAbort.reset = function () { reset(current); current = null; if (frame) cancelAnimationFrame(frame); };
  }

  /* ---------------- Scroll reveals and parallax ---------------- */
  function initReveals() {
    var targets = gsap.utils.toArray("[data-reveal]");
    targets.forEach(function (el) {
      var kind = el.getAttribute("data-reveal");
      gsap.set(el, { autoAlpha: 0, y: kind === "up" || !kind ? cfg.rise * 0.6 : 0, x: kind === "left" ? -cfg.dist * 0.7 : kind === "right" ? cfg.dist * 0.7 : 0 });
    });
    track(live.triggers, ScrollTrigger.batch(targets, {
      start: "top 90%", once: true,
      onEnter: function (batch) { gsap.to(batch, { autoAlpha: 1, x: 0, y: 0, duration: 0.95, stagger: 0.12, ease: "power3.out", overwrite: true }); }
    }));
    return targets;
  }
  function initParallax() {
    gsap.utils.toArray("[data-parallax]").forEach(function (el) {
      var speed = parseFloat(el.getAttribute("data-parallax")) || 0.1;
      var hero = el.getAttribute("data-parallax-trigger") === "hero";
      track(live.triggers, gsap.to(el, {
        yPercent: speed * 100, ease: "none",
        scrollTrigger: { trigger: hero ? el.closest(".hero") : el.closest("section") || el, start: hero ? "top top" : "top bottom", end: "bottom top", scrub: true }
      }).scrollTrigger);
    });
    gsap.utils.toArray("[data-parallax-inner]").forEach(function (el) {
      track(live.triggers, gsap.fromTo(el, { yPercent: -5 }, {
        yPercent: 5, ease: "none",
        scrollTrigger: { trigger: el.parentElement, start: "top bottom", end: "bottom top", scrub: true }
      }).scrollTrigger);
    });
  }

  /* ---------------- Product page entrance: gallery from the left, details from the right ---------------- */
  function initProductPage() {
    var stage = document.querySelector(".pdp__stage");
    var info = toArray(document.querySelectorAll(".pdp__info > *"));
    var thumbs = toArray(document.querySelectorAll(".pdp__thumbs li"));
    if (!stage) return;
    gsap.set(stage, { autoAlpha: 0, x: -cfg.dist * 0.6 });
    gsap.set(info, { autoAlpha: 0, x: cfg.dist * 0.5 });
    gsap.set(thumbs, { autoAlpha: 0, y: 16 });
    release();
    var tl = gsap.timeline({ defaults: { ease: "power3.out" } });
    tl.to(stage, { autoAlpha: 1, x: 0, duration: 1, clearProps: "transform,opacity,visibility" }, 0.05)
      .to(info, { autoAlpha: 1, x: 0, duration: 0.85, stagger: 0.07, clearProps: "transform,opacity,visibility" }, 0.2)
      .to(thumbs, { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.06, clearProps: "transform,opacity,visibility" }, 0.5);
    track(live.tweens, tl);
  }

  /* ---------------- Activate / deactivate with the media query ---------------- */
  function activate(profile) {
    cfg = profile;
    window.Avelle.motion.active = function () { return !!cfg; };
    if (profile.float && "IntersectionObserver" in window) {
      io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          var pc = en.target.querySelector("[data-pc]");
          var tw = pc && pc._floatTween;
          if (tw) { if (en.isIntersecting) tw.resume(); else tw.pause(); }
        });
      }, { rootMargin: "80px" });
    }
    if (profile.tilt) initTilt();
    initReveals();
    if (profile.parallax) initParallax();
    toArray(document.querySelectorAll(".product-grid[data-enter]")).forEach(function (grid) { enter(grid, cellsOf(grid), "init"); });
    initProductPage();
    release();
  }

  function deactivate() {
    var was = cfg;
    cfg = null;
    window.Avelle.motion.active = function () { return false; };
    live.triggers.forEach(function (t) { if (t && t.kill) t.kill(); });
    live.tweens.forEach(function (t) { if (t && t.kill) t.kill(); });
    live.triggers = []; live.tweens = [];
    if (io) { io.disconnect(); io = null; }
    if (tiltAbort) { tiltAbort.reset(); tiltAbort.abort(); tiltAbort = null; }
    if (was) {
      toArray(document.querySelectorAll("[data-pc-float]")).forEach(function (l) { l._float = null; });
      gsap.set(toArray(document.querySelectorAll("[data-pc], [data-pc-float], [data-reveal], .pdp__stage, .pdp__info > *, .pdp__thumbs li")), { clearProps: "all" });
      toArray(document.querySelectorAll("[data-pc-tilt]")).forEach(function (el) { el.style.removeProperty("--tilt-x"); el.style.removeProperty("--tilt-y"); el.classList.remove("is-tracking"); });
    }
    release();
  }

  var mm = gsap.matchMedia();
  mm.add({
    desktop: "(min-width: 900px) and (prefers-reduced-motion: no-preference)",
    mobile: "(max-width: 899px) and (prefers-reduced-motion: no-preference)"
  }, function (context) {
    activate(context.conditions.desktop ? DESKTOP : MOBILE);
    return deactivate;
  });
  mm.add("(prefers-reduced-motion: reduce)", function () { release(); root.classList.remove("page-entering"); });

  window.Avelle.motion.enter = enter;

  /* ---------------- Shop hooks (see static/js/shop.js) ---------------- */
  document.addEventListener("avelle:results-leaving", function (e) {
    if (!cfg) return;
    var grid = document.querySelector("[data-product-grid]");
    if (grid) e.detail.wait.push(leave(grid));
  });
  document.addEventListener("avelle:results-rendered", function (e) {
    if (!cfg) return; // not ours to handle: shop.js plays its CSS fade
    e.preventDefault();
    enter(e.detail.grid, e.detail.items, e.detail.mode);
    if (e.detail.mode === "replace") requestAnimationFrame(function () { ScrollTrigger.refresh(); });
  });

  /* ---------------- Page transitions: a quick fade between pages ---------------- */
  function enterPage() {
    if (!root.classList.contains("page-entering")) return;
    var main = document.getElementById("main");
    if (!main) { root.classList.remove("page-entering"); return; }
    gsap.fromTo(main, { opacity: 0 }, { opacity: 1, duration: 0.45, ease: "power1.out", clearProps: "opacity", onStart: function () { root.classList.remove("page-entering"); } });
  }
  enterPage();
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) { var main = document.getElementById("main"); if (main) gsap.set(main, { clearProps: "opacity" }); root.classList.remove("page-entering"); }
  });

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || reducedNow()) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.target || a.hasAttribute("download") || a.hasAttribute("data-no-transition") || a.getAttribute("rel") === "external") return;
    var url;
    try { url = new URL(a.href, location.href); } catch (err) { return; }
    if (url.origin !== location.origin || !/^https?:$/.test(url.protocol)) return;
    if (/^\/(django-admin|dashboard|static|media)\b/.test(url.pathname)) return;
    if (url.pathname === location.pathname && url.search === location.search) return; // hash jumps and same-page links
    var main = document.getElementById("main");
    if (!main) return;
    e.preventDefault();
    var go = function () { try { sessionStorage.setItem("avelle-nav", "1"); } catch (err) {} location.href = url.href; };
    var fired = false, once = function () { if (!fired) { fired = true; go(); } };
    gsap.to(main, { opacity: 0, duration: 0.28, ease: "power1.in", onComplete: once });
    setTimeout(once, 600); // never leave the visitor waiting on an animation
  });
})();
