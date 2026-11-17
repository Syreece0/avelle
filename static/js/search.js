/* ==========================================================================
   Header search suggestions (progressive enhancement over a normal GET form).
   - Debounced fetch to /shop/suggest/, stale responses ignored
   - ARIA combobox: ArrowUp/Down move through options, Enter opens the active one,
     Escape clears the list. Without JS the form submits to /shop/?q=
   ========================================================================== */
(function () {
  "use strict";

  var form = document.querySelector("[data-search-form]");
  var input = form && form.querySelector("input[name='q']");
  var box = document.getElementById("search-suggest");
  if (!form || !input || !box || !window.fetch) return;

  var timer = null, controller = null, token = 0, active = -1;

  function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;"); } // safe inside attribute values too
  function options() { return Array.prototype.slice.call(box.querySelectorAll("[role='option']")); }

  function close() {
    box.hidden = true; box.innerHTML = ""; active = -1;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function setActive(i) {
    var list = options();
    if (!list.length) return;
    active = (i + list.length) % list.length;
    list.forEach(function (el, n) { el.setAttribute("aria-selected", n === active ? "true" : "false"); });
    input.setAttribute("aria-activedescendant", list[active].id);
    list[active].scrollIntoView({ block: "nearest" });
  }

  function render(data, q) {
    var html = "", n = 0;
    if (data.categories.length) {
      html += '<div class="search-suggest__label">Categories</div>';
      data.categories.forEach(function (c) {
        html += '<a role="option" id="sg-' + (n++) + '" aria-selected="false" href="' + esc(c.url) + '"><span class="search-suggest__name">' + esc(c.name) + "</span></a>";
      });
    }
    if (data.products.length) {
      html += '<div class="search-suggest__label">Products</div>';
      data.products.forEach(function (p) {
        html += '<a role="option" id="sg-' + (n++) + '" aria-selected="false" href="' + esc(p.url) + '">' +
          (p.image ? '<img src="' + esc(p.image) + '" alt="" width="44" height="55" loading="lazy">' : "") +
          '<span class="search-suggest__name">' + esc(p.name) + '</span><span class="search-suggest__price">' + esc(p.price) + "</span></a>";
      });
      html += '<a role="option" id="sg-' + (n++) + '" aria-selected="false" class="search-suggest__all" href="/shop/?q=' + encodeURIComponent(q) + '">See all results for “' + esc(q) + "”</a>";
    }
    if (!n) html = '<p class="search-suggest__empty" role="status">No matches for “' + esc(q) + "”. Try a different word.</p>";
    box.innerHTML = html;
    box.hidden = false;
    active = -1;
    input.setAttribute("aria-expanded", n ? "true" : "false");
  }

  function lookup() {
    var q = input.value.replace(/\s+/g, " ").trim();
    if (q.length < 2) { close(); return; }
    var mine = ++token;
    if (controller) controller.abort();
    controller = new AbortController();
    fetch("/shop/suggest/?q=" + encodeURIComponent(q), { headers: { Accept: "application/json" }, credentials: "same-origin", signal: controller.signal })
      .then(function (r) { if (!r.ok) throw new Error("status " + r.status); return r.json(); })
      .then(function (data) { if (mine === token && input.value.trim().length >= 2) render(data, q); })
      .catch(function () { /* suggestions are optional; the form still works */ });
  }

  input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(lookup, 200); });
  input.addEventListener("keydown", function (e) {
    var list = options();
    if (e.key === "ArrowDown" && list.length) { e.preventDefault(); setActive(active + 1); }
    else if (e.key === "ArrowUp" && list.length) { e.preventDefault(); setActive(active - 1); }
    else if (e.key === "Enter" && active > -1 && list[active]) { e.preventDefault(); window.location.href = list[active].getAttribute("href"); }
    else if (e.key === "Escape" && !box.hidden) { e.stopPropagation(); close(); }
  });
  document.addEventListener("click", function (e) { if (!form.contains(e.target) && !box.contains(e.target)) close(); });
  form.addEventListener("submit", function () { token++; close(); });
})();
