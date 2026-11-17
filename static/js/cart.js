/* ==========================================================================
   Bag and wishlist behaviour, on every page.
   - window.Avelle.addToCart(detail, button)   used by the product page
   - window.Avelle.wishlistToggle(button)      used by every heart button
   - the bag page: quantity changes and removal without a reload
   Everything also works as plain form posts when JavaScript is unavailable.
   ========================================================================== */
(function () {
  "use strict";
  if (!window.fetch) return;
  window.Avelle = window.Avelle || {};
  if (window.Avelle.cartLoaded) return; // never bind twice
  window.Avelle.cartLoaded = true;

  function csrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function toast(opts) { if (window.Avelle.toast) window.Avelle.toast(opts); }

  function post(url, data) {
    var body = new FormData();
    Object.keys(data).forEach(function (k) { body.append(k, data[k]); });
    return fetch(url, {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest", Accept: "application/json" }
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, message: "Something went wrong. Please try again." }; })
        .then(function (json) { json.status = r.status; return json; });
    });
  }
  function networkError() { toast({ title: "Connection problem", message: "Please check your connection and try again.", type: "error" }); }

  /* ---------------- Header badge ---------------- */
  function setCount(n) {
    var badge = document.querySelector("[data-cart-count]");
    var link = document.querySelector("[data-cart-link]");
    if (badge) { badge.textContent = n; badge.hidden = !n; }
    if (link) link.setAttribute("aria-label", "Bag" + (n ? ", " + n + " item" + (n === 1 ? "" : "s") : ""));
  }

  /* ---------------- Add to bag ---------------- */
  window.Avelle.addToCart = function (detail, button) {
    if (button) { button.classList.add("is-loading"); button.setAttribute("aria-busy", "true"); }
    var result;
    return post("/cart/add/", { variant: detail.variantId, quantity: detail.quantity })
      .then(function (res) {
        result = res;
        if (typeof res.count === "number") setCount(res.count);
        if (res.ok) {
          toast({ title: res.message || "Added to your bag", message: res.note || "", action: { label: "View bag", href: "/cart/" } });
        } else {
          toast({ title: res.message || "Couldn't add that to your bag", type: "error" });
        }
        return res;
      })
      .catch(networkError)
      .then(function () {
        if (button) { button.classList.remove("is-loading"); button.removeAttribute("aria-busy"); }
        return result;
      });
  };

  /* ---------------- Wishlist ---------------- */
  var pending = {};
  window.Avelle.wishlistToggle = function (button) {
    var id = button.getAttribute("data-wishlist-toggle");
    if (pending[id]) return;
    pending[id] = true;
    return post("/wishlist/toggle/", { product: id, next: location.pathname + location.search })
      .then(function (res) {
        if (res.login_required) {
          toast({ title: "Sign in to save favourites", message: "Your wishlist is kept with your account.", action: { label: "Sign in", href: res.login_url } });
          return;
        }
        if (!res.ok) { toast({ title: "Couldn't update your wishlist", type: "error" }); return; }
        document.querySelectorAll('[data-wishlist-toggle="' + id + '"]').forEach(function (b) { b.setAttribute("aria-pressed", res.active ? "true" : "false"); });
        toast({ title: res.active ? "Saved to your wishlist" : "Removed from your wishlist" });
        var grid = document.querySelector("[data-wishlist-grid]");
        if (grid && !res.active) {
          var cell = button.closest(".product-grid__item");
          if (cell) cell.remove();
          if (!grid.children.length) location.reload(); // shows the empty state
          var label = document.querySelector("[data-wishlist-count]");
          if (label) label.textContent = res.count + " saved piece" + (res.count === 1 ? "" : "s");
        }
      })
      .catch(networkError)
      .then(function () { delete pending[id]; });
  };

  /* ---------------- Bag page ---------------- */
  var body = document.querySelector("[data-cart-body]");
  if (!body) return;
  var seq = 0, timer = null;

  function apply(res, focusLine) {
    if (res.html !== undefined) body.innerHTML = res.html;
    if (typeof res.count === "number") setCount(res.count);
    if (res.message && !res.ok) toast({ title: res.message, type: "error" });
    else if (res.note) toast({ title: res.note });
    if (focusLine) {
      var input = body.querySelector('[data-line="' + focusLine + '"] input[name="quantity"]');
      if (input) input.focus();
    }
  }
  function send(url, data, focusLine) {
    var mine = ++seq;
    body.setAttribute("aria-busy", "true");
    return post(url, data).then(function (res) { if (mine === seq) apply(res, focusLine); })
      .catch(networkError).then(function () { if (mine === seq) body.removeAttribute("aria-busy"); });
  }
  // Note: form.elements.item is the HTMLFormControlsCollection.item() method, so fields are read by selector.
  function field(form, name) { return form.querySelector('[name="' + name + '"]'); }
  function submitQty(form) {
    var item = field(form, "item").value;
    send("/cart/update/", { item: item, quantity: field(form, "quantity").value }, item);
  }

  body.addEventListener("click", function (e) {
    var step = e.target.closest("[data-qty-step]");
    if (!step) return;
    var form = step.closest("[data-cart-update]");
    var input = field(form, "quantity");
    var max = parseInt(input.max, 10) || 10;
    var next = Math.max(0, Math.min(max, (parseInt(input.value, 10) || 0) + parseInt(step.getAttribute("data-qty-step"), 10)));
    if (next === 0 && !window.confirm("Remove this item from your bag?")) return;
    input.value = next;
    clearTimeout(timer);
    timer = setTimeout(function () { submitQty(form); }, 350);
  });
  body.addEventListener("change", function (e) {
    var form = e.target.closest && e.target.closest("[data-cart-update]");
    if (form) { clearTimeout(timer); submitQty(form); }
  });
  body.addEventListener("submit", function (e) {
    var update = e.target.closest("[data-cart-update]");
    var remove = e.target.closest("[data-cart-remove]");
    if (!update && !remove) return;
    e.preventDefault();
    if (update) { clearTimeout(timer); submitQty(update); }
    else send("/cart/remove/", { item: field(remove, "item").value });
  });
})();
