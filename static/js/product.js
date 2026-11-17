/* ==========================================================================
   Product detail page: gallery, lightbox, variant selection, quantity.
   Works from two JSON blocks written by the page: #pdp-variants and #pdp-images.
   Adding to the bag is handled by window.Avelle.addToCart (cart.js).
   ========================================================================== */
(function () {
  "use strict";

  var page = document.querySelector("[data-pdp]");
  if (!page) return;

  function read(id) { try { return JSON.parse(document.getElementById(id).textContent); } catch (e) { return []; } }
  var variants = read("pdp-variants");
  var imageMeta = read("pdp-images");
  var currency = page.getAttribute("data-currency") || "₦";
  function reduced() { return window.Avelle && window.Avelle.prefersReducedMotion && window.Avelle.prefersReducedMotion(); }

  /* ---------------- Gallery ---------------- */
  var main = page.querySelector("[data-gallery-main]");
  var thumbs = Array.prototype.slice.call(page.querySelectorAll("[data-gallery-thumb]"));
  var zoomBox = page.querySelector(".pdp__zoom");
  var current = 0;

  function showImage(index, opts) {
    if (!thumbs.length || !main) return;
    index = (index + thumbs.length) % thumbs.length;
    var thumb = thumbs[index];
    current = index;
    thumbs.forEach(function (t, i) {
      t.classList.toggle("is-active", i === index);
      if (i === index) t.setAttribute("aria-current", "true"); else t.removeAttribute("aria-current");
    });
    if (main.getAttribute("src") === thumb.getAttribute("data-src")) return;
    var swap = function () {
      main.src = thumb.getAttribute("data-src");
      main.alt = thumb.getAttribute("data-alt") || "";
      main.classList.remove("is-swapping");
    };
    if (reduced() || (opts && opts.instant)) return swap();
    main.classList.add("is-swapping");
    var pre = new Image();
    pre.onload = pre.onerror = function () { setTimeout(swap, 120); };
    pre.src = thumb.getAttribute("data-src");
  }

  thumbs.forEach(function (t, i) { t.addEventListener("click", function () { showImage(i); }); });
  page.querySelectorAll("[data-gallery-step]").forEach(function (b) {
    b.addEventListener("click", function () { showImage(current + parseInt(b.getAttribute("data-gallery-step"), 10)); });
  });

  // Hover zoom: the inner <img> scales; the wrapper never moves.
  if (zoomBox && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    zoomBox.addEventListener("pointerenter", function () { if (!reduced()) zoomBox.classList.add("is-zooming"); });
    zoomBox.addEventListener("pointermove", function (e) {
      var r = zoomBox.getBoundingClientRect();
      main.style.setProperty("--zx", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
      main.style.setProperty("--zy", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
    });
    zoomBox.addEventListener("pointerleave", function () { zoomBox.classList.remove("is-zooming"); });
  }

  /* ---------------- Lightbox ---------------- */
  var box = document.getElementById("lightbox");
  var boxImg = box && box.querySelector("[data-lightbox-img]");
  function lightboxShow(index) {
    if (!thumbs.length) return;
    index = (index + thumbs.length) % thumbs.length;
    showImage(index, { instant: true });
    boxImg.src = thumbs[index].getAttribute("data-src");
    boxImg.alt = thumbs[index].getAttribute("data-alt") || "";
  }
  var openBtn = page.querySelector("[data-gallery-open]");
  if (box && openBtn) {
    box.classList.toggle("lightbox--single", thumbs.length < 2);
    openBtn.addEventListener("click", function () {
      if (typeof box.showModal !== "function") return;
      if (thumbs.length) lightboxShow(current); else { boxImg.src = main.src; boxImg.alt = main.alt; }
      box.showModal();
    });
    box.querySelectorAll("[data-lightbox-step]").forEach(function (b) {
      b.addEventListener("click", function () { lightboxShow(current + parseInt(b.getAttribute("data-lightbox-step"), 10)); });
    });
    box.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") lightboxShow(current - 1);
      if (e.key === "ArrowRight") lightboxShow(current + 1);
    });
    box.addEventListener("click", function (e) { if (e.target === box || e.target === boxImg) box.close(); });
  }

  /* ---------------- Variant selection ---------------- */
  var form = page.querySelector("[data-pdp-form]");
  var message = page.querySelector("[data-message]");
  var addBtn = page.querySelector("[data-add]");
  var qtyInput = page.querySelector("[data-qty-input]");
  var priceNow = page.querySelector("[data-price-now]");
  var priceWas = page.querySelector("[data-price-was]");
  var basePriceText = priceNow ? priceNow.textContent : "";
  var MAX_QTY = 10;

  function money(value) {
    var n = parseFloat(value);
    return currency + n.toLocaleString("en-NG", { maximumFractionDigits: n % 1 ? 2 : 0 });
  }
  function selected(name) {
    var el = form.querySelector('input[name="' + name + '"]:checked');
    return el ? parseInt(el.value, 10) : null;
  }
  function find(size, colour) {
    return variants.filter(function (v) { return v.size === size && v.colour === colour; })[0] || null;
  }
  function inStock(v) { return v && v.qty > 0; }

  // An option is "out" when no in-stock variant has it (given the other choice, if made).
  function markOptions() {
    var size = selected("size"), colour = selected("colour");
    form.querySelectorAll('[data-option="size"]').forEach(function (el) {
      var id = parseInt(el.getAttribute("data-value"), 10);
      var ok = variants.some(function (v) { return v.size === id && (colour === null || v.colour === colour) && inStock(v); });
      el.classList.toggle("is-out", !ok);
    });
    form.querySelectorAll('[data-option="colour"]').forEach(function (el) {
      var id = parseInt(el.getAttribute("data-value"), 10);
      var ok = variants.some(function (v) { return v.colour === id && (size === null || v.size === size) && inStock(v); });
      el.classList.toggle("is-out", !ok);
    });
  }

  function setMessage(text, kind) {
    message.textContent = text;
    message.classList.toggle("is-error", kind === "error");
    message.classList.toggle("is-low", kind === "low");
  }

  function chosenLabels() {
    ["size", "colour"].forEach(function (name) {
      var out = form.querySelector('[data-chosen="' + name + '"]');
      var el = form.querySelector('input[name="' + name + '"]:checked');
      if (out) out.textContent = el ? el.getAttribute("data-name") : "";
    });
  }

  // Returns the chosen variant or null; `state` explains why it's null.
  function evaluate() {
    var needSize = !!form.querySelector('input[name="size"]');
    var needColour = !!form.querySelector('input[name="colour"]');
    var size = selected("size"), colour = selected("colour");
    if ((needSize && size === null) || (needColour && colour === null)) return { state: "incomplete", variant: null };
    var v = find(size, colour);
    if (!v) return { state: "missing", variant: null };
    if (!inStock(v)) return { state: "soldout", variant: v };
    return { state: "ok", variant: v };
  }

  function updateQty(v) {
    var max = v ? Math.min(v.qty, MAX_QTY) : MAX_QTY;
    qtyInput.max = max;
    var n = parseInt(qtyInput.value, 10) || 1;
    qtyInput.value = Math.max(1, Math.min(n, max));
  }

  function refresh(userChange) {
    chosenLabels();
    markOptions();
    var r = evaluate();
    var v = r.variant;

    // Price (a variant can carry its own price)
    if (priceNow) {
      if (v && v.price && money(v.price) !== basePriceText) {
        priceNow.textContent = money(v.price);
        if (priceWas) priceWas.hidden = true;
      } else {
        priceNow.textContent = basePriceText;
        if (priceWas) priceWas.hidden = false;
      }
    }

    form.querySelectorAll(".pdp__field").forEach(function (f) { f.classList.remove("has-error"); });

    if (r.state === "ok") {
      if (v.low) setMessage("Only " + v.qty + " left in this size and colour", "low");
      else setMessage("In stock", "");
      addBtn.removeAttribute("aria-disabled");
    } else if (r.state === "soldout") {
      setMessage("Sold out in this size and colour. Try another combination.", "error");
      addBtn.setAttribute("aria-disabled", "true");
    } else if (r.state === "missing") {
      setMessage("This size and colour combination isn't offered.", "error");
      addBtn.setAttribute("aria-disabled", "true");
    } else {
      if (userChange) setMessage("", "");
      addBtn.removeAttribute("aria-disabled");
    }
    updateQty(v);
  }

  // Selecting a colour shows that colour's photo if one is tagged
  form.addEventListener("change", function (e) {
    if (e.target.name === "colour" && thumbs.length) {
      var id = parseInt(e.target.value, 10);
      for (var i = 0; i < imageMeta.length; i++) {
        if (imageMeta[i].colour === id) { showImage(i); break; }
      }
    }
    if (e.target === qtyInput) { updateQty(evaluate().variant); return; }
    refresh(true);
  });

  page.querySelectorAll("[data-qty-step]").forEach(function (b) {
    b.addEventListener("click", function () {
      var step = parseInt(b.getAttribute("data-qty-step"), 10);
      var max = parseInt(qtyInput.max, 10) || MAX_QTY;
      qtyInput.value = Math.max(1, Math.min(max, (parseInt(qtyInput.value, 10) || 1) + step));
    });
  });

  /* ---------------- Add to bag ---------------- */
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (addBtn.disabled) return;
    var r = evaluate();

    if (r.state === "incomplete") {
      var missing = ["size", "colour"].filter(function (n) { return form.querySelector('input[name="' + n + '"]') && selected(n) === null; });
      var first = null;
      missing.forEach(function (n) {
        var group = form.querySelector('[data-group="' + n + '"]');
        group.classList.add("has-error");
        if (!first) first = group;
      });
      setMessage("Please choose your " + missing.join(" and ") + ".", "error");
      if (first) { var input = first.querySelector("input"); if (input) input.focus(); }
      return;
    }
    if (r.state !== "ok") { refresh(false); return; }

    var detail = { variantId: r.variant.id, productId: parseInt(page.getAttribute("data-product-id"), 10), quantity: parseInt(qtyInput.value, 10) || 1 };
    if (window.Avelle && typeof window.Avelle.addToCart === "function") {
      window.Avelle.addToCart(detail, addBtn);
    } else {
      form.submit(); // no cart script: fall back to the plain form post
    }
  });

  refresh(false);
})();
