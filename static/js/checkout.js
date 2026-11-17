/* ==========================================================================
   Checkout: live totals and saved-address prefill (progressive enhancement).
   The server recomputes every figure when the order is placed; this only previews them.
   ========================================================================== */
(function () {
  "use strict";
  var form = document.querySelector("[data-checkout]");
  if (!form || !window.fetch) return;

  var url = form.getAttribute("data-quote-url");
  var stateSel = form.elements.state;
  var codeInput = form.elements.discount_code;
  var emailInput = form.elements.email;
  var seq = 0, timer = null, controller = null;

  function $(sel) { return document.querySelector(sel); }
  function setAll(key, text) { document.querySelectorAll('[data-q="' + key + '"]').forEach(function (el) { el.textContent = text; }); }

  function render(q) {
    setAll("subtotal", q.subtotal);
    var row = $('[data-row="discount"]');
    if (row) { row.hidden = !q.discount; if (q.discount) setAll("discount", q.discount); }
    setAll("delivery", q.state_ok ? q.delivery : "Choose your state");
    document.querySelectorAll('.cart-summary [data-q="total"]').forEach(function (el) { el.textContent = q.total || "-"; });
    var pay = $("[data-pay] [data-q='total']");
    if (pay) pay.textContent = q.total || "now";
    var eta = $("[data-eta]");
    if (eta) eta.textContent = q.state_ok && q.eta ? "Delivery in " + q.eta + "." : (stateSel.value ? "We don't deliver to that state yet." : "");
    var msg = $("[data-code-message]");
    if (msg) { msg.textContent = q.code_message || ""; msg.classList.toggle("is-error", !!codeInput.value.trim() && !q.code_ok); }
  }

  function refresh() {
    var mine = ++seq;
    if (controller) controller.abort();
    controller = new AbortController();
    var params = new URLSearchParams({ state: stateSel.value, code: codeInput.value.trim(), email: emailInput ? emailInput.value.trim() : "" });
    fetch(url + "?" + params.toString(), { headers: { Accept: "application/json" }, credentials: "same-origin", signal: controller.signal })
      .then(function (r) { if (!r.ok) throw new Error("status " + r.status); return r.json(); })
      .then(function (q) { if (mine === seq) render(q); })
      .catch(function (err) { if (err && err.name === "AbortError") return; /* the server still recomputes on submit */ });
  }

  stateSel.addEventListener("change", refresh);
  form.querySelector("[data-apply-code]").addEventListener("click", refresh);
  codeInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); refresh(); } });
  codeInput.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(refresh, 700); });

  /* Saved addresses fill the fields; the customer can still edit them */
  var saved = $("[data-saved-address]");
  if (saved) saved.addEventListener("change", function () {
    var o = saved.options[saved.selectedIndex];
    if (!o.value) return;
    var map = { customer_name: "name", phone: "phone", address_line1: "line1", address_line2: "line2", city: "city", state: "state", landmark: "landmark" };
    Object.keys(map).forEach(function (field) { if (form.elements[field]) form.elements[field].value = o.getAttribute("data-" + map[field]) || ""; });
    refresh();
  });

  /* Stop double submits: a second click would create a second order */
  form.addEventListener("submit", function (e) {
    var pay = $("[data-pay]");
    if (pay.getAttribute("aria-busy") === "true") { e.preventDefault(); return; }
    pay.setAttribute("aria-busy", "true");
    pay.classList.add("is-loading");
  });
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) { var pay = $("[data-pay]"); pay.removeAttribute("aria-busy"); pay.classList.remove("is-loading"); } // back from Paystack
  });
})();
