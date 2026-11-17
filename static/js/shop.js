/* ==========================================================================
   Shop listing behaviour (progressive enhancement over a normal GET form)

   Without JS everything works as plain links and a submit button. With JS:
     - filters, tabs, sort and pagination fetch JSON and swap the results
     - the URL is updated with pushState; back/forward restore the state
     - "Load more" appends the next page
     - below 900px the filter form is moved into a drawer <dialog>

   Contract for the Phase 6 animation layer (all events bubble from [data-shop-results]):
     avelle:results-leaving   detail.wait is an array; push a Promise to delay the swap
                              (use it to play an exit animation). Capped at 1200ms.
     avelle:results-rendered  cancelable. detail = { grid, items, mode: "replace"|"append" }.
                              If nobody calls preventDefault(), a CSS fade-in plays instead.
   ========================================================================== */
(function () {
  "use strict";

  var root = document.querySelector("[data-shop]");
  if (!root || !window.fetch || !window.URLSearchParams) return;

  var endpoint = root.getAttribute("data-endpoint");
  var results = root.querySelector("[data-shop-results]");
  var grid = root.querySelector("[data-product-grid]");
  var pager = root.querySelector("[data-shop-pager]");
  var chipsBox = root.querySelector("[data-shop-chips]");
  var typesBox = root.querySelector("[data-shop-types]");
  var tabsBox = root.querySelector("[data-shop-tabs]");
  var sortSelect = root.querySelector("[data-sort-select]");
  var form = document.querySelector("[data-shop-form]");
  var drawer = document.getElementById("filters-drawer");
  var drawerBody = drawer && drawer.querySelector("[data-filters-drawer-body]");
  var home = document.querySelector("[data-filters-home]");
  var scope = null; // "category/type" the current filter options were built for
  var seq = 0;      // identifies the latest request so stale responses are ignored
  var controller = null;
  var loadingTimer = null;
  var typingTimer = null;

  function reduced() { return window.Avelle && window.Avelle.prefersReducedMotion && window.Avelle.prefersReducedMotion(); }
  function notify(title, message) { if (window.Avelle && window.Avelle.toast) window.Avelle.toast({ title: title, message: message, type: "error" }); }
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }

  /* ---------- Reading state ---------- */
  function paramsFromForm() {
    var params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      value = String(value).trim();
      if (value !== "") params.append(key, value);
    });
    params.delete("page");
    return params;
  }
  function queryOf(href) { var i = href.indexOf("?"); return i === -1 ? "" : href.slice(i + 1); }
  function urlFor(params) { var q = params.toString(); return endpoint + (q ? "?" + q : ""); }

  /* ---------- Fetch + render ---------- */
  function request(query, opts) {
    opts = opts || {};
    var mode = opts.append ? "append" : "replace";
    var id = ++seq;
    if (controller) controller.abort();
    controller = new AbortController();

    clearTimeout(loadingTimer);
    loadingTimer = setTimeout(function () { results.classList.add("is-loading"); }, 150);
    results.setAttribute("aria-busy", "true");

    var url = endpoint + (query ? "?" + query : "");
    return fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" }, credentials: "same-origin", signal: controller.signal })
      .then(function (r) { if (!r.ok) throw new Error("bad status " + r.status); return r.json(); })
      .then(function (data) {
        if (id !== seq) return;
        return render(data, mode, opts, id).then(function () {
          if (id !== seq) return;
          if (opts.history === "push") history.pushState({ shop: true }, "", url);
          else if (opts.history === "replace") history.replaceState({ shop: true }, "", url);
        });
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") return; // superseded by a newer request
        if (id === seq) {
          notify("Couldn't update the results", "Please check your connection and try again.");
          var stuck = root.querySelector("[data-load-more]");
          if (stuck) stuck.classList.remove("is-loading");
        }
      })
      .then(function () {
        if (id !== seq) return;
        clearTimeout(loadingTimer);
        results.classList.remove("is-loading");
        results.setAttribute("aria-busy", "false");
      });
  }

  function waitForExit() {
    var detail = { wait: [] };
    results.dispatchEvent(new CustomEvent("avelle:results-leaving", { bubbles: true, detail: detail }));
    if (!detail.wait.length) return Promise.resolve();
    return Promise.race([Promise.all(detail.wait), new Promise(function (r) { setTimeout(r, 1200); })]).catch(function () {});
  }

  function toNodes(html) {
    var tpl = document.createElement("template");
    tpl.innerHTML = html.trim();
    return Array.prototype.slice.call(tpl.content.children);
  }

  function render(data, mode, opts, id) {
    var before = mode === "replace" ? waitForExit() : Promise.resolve();
    return before.then(function () {
      if (id !== seq) return; // a newer request took over while the exit animation played
      var items = toNodes(data.results_html);
      if (mode === "replace") grid.replaceChildren.apply(grid, items);
      else items.forEach(function (n) { grid.appendChild(n); });

      pager.innerHTML = data.pagination_html;
      if (mode === "replace") {
        root.querySelector("[data-shop-heading]").textContent = data.heading;
        document.title = data.heading + " · AVELLE";
        chipsBox.innerHTML = data.chips_html;
        typesBox.innerHTML = data.types_html;
        renderTabs(data);
        renderSorts(data.sorts);
        syncFilters(data, opts);
      }
      updateTotals(data);

      var detail = { grid: grid, items: items, mode: mode };
      var ok = results.dispatchEvent(new CustomEvent("avelle:results-rendered", { bubbles: true, cancelable: true, detail: detail }));
      if (ok && !reduced()) fadeIn(items);

      if (mode === "replace" && opts && opts.scroll) {
        var top = results.getBoundingClientRect().top;
        if (top < 0 || top > window.innerHeight * 0.6) {
          var y = window.scrollY + root.querySelector("[data-shop-tabs]").getBoundingClientRect().top - 90;
          window.scrollTo({ top: Math.max(0, y), behavior: reduced() ? "auto" : "smooth" });
        }
      }
    });
  }

  /* CSS fallback entrance, used until the GSAP system (Phase 6) cancels it */
  function fadeIn(items) {
    items.forEach(function (n, i) { n.style.setProperty("--i", Math.min(i, 12)); });
    grid.classList.add("is-entering");
    setTimeout(function () {
      grid.classList.remove("is-entering");
      items.forEach(function (n) { n.style.removeProperty("--i"); });
    }, 1100);
  }

  function updateTotals(data) {
    root.querySelectorAll("[data-shop-total]").forEach(function (el) {
      el.textContent = data.total;
      var label = el.nextSibling;
      if (label && label.nodeType === 3) label.nodeValue = " " + (data.total === 1 ? "piece" : "pieces");
    });
    document.querySelectorAll("[data-shop-total-copy]").forEach(function (el) { el.textContent = data.total; });
    var badge = root.querySelector("[data-filter-badge]");
    var btn = root.querySelector(".shop-toolbar__filters");
    if (btn) {
      if (data.active_count) {
        if (!badge) { badge = document.createElement("span"); badge.className = "dropdown__count"; badge.setAttribute("data-filter-badge", ""); btn.appendChild(document.createTextNode(" ")); btn.appendChild(badge); }
        badge.textContent = data.active_count;
      } else if (badge) { badge.remove(); }
    }
  }

  function renderTabs(data) {
    var anyActive = data.tabs.some(function (t) { return t.selected; });
    var html = tab("All", data.all_count, allHrefFor(data), !anyActive);
    data.tabs.forEach(function (t) { html += tab(t.name, t.count, t.href, t.selected); });
    tabsBox.innerHTML = html;
  }
  function allHrefFor(data) { return data.all_href || "/shop/"; }
  function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;"); } // safe inside attribute values too
  function tab(name, count, href, active) {
    return '<a class="shop-tab' + (active ? " is-active" : "") + '" href="' + esc(href) + '" data-shop-link' + (active ? ' aria-current="true"' : "") + ">" +
      esc(name) + ' <span class="shop-tab__n">' + count + "</span></a>";
  }

  function renderSorts(sorts) {
    if (!sortSelect || !sorts) return;
    sortSelect.innerHTML = sorts.map(function (s) {
      return '<option value="' + esc(String(s.value)) + '"' + (s.selected ? " selected" : "") + ">" + esc(s.label) + "</option>";
    }).join("");
  }

  /* Filter panel: swap whole panel when the options themselves change; otherwise just update counts */
  function syncFilters(data, opts) {
    var rebuild = scope !== data.scope || !(opts && opts.fromForm);
    if (rebuild) {
      var open = {};
      form.querySelectorAll("details.filter").forEach(function (d) { open[d.querySelector("summary").textContent.trim()] = d.open; });
      form.innerHTML = data.filters_html;
      form.querySelectorAll("details.filter").forEach(function (d) {
        var key = d.querySelector("summary").textContent.trim();
        if (key in open) d.open = open[key];
      });
    } else {
      ["size", "colour", "brand"].forEach(function (kind) {
        var counts = data.facets[kind] || {};
        form.querySelectorAll('[data-count-for^="' + kind + ':"]').forEach(function (el) {
          var key = el.getAttribute("data-count-for").split(":")[1];
          var n = counts[key] || 0;
          el.textContent = n;
          var label = el.closest("label");
          var input = label && label.querySelector("input");
          if (label && label.classList.contains("option")) label.classList.toggle("is-zero", !n && !(input && input.checked));
        });
      });
    }
    scope = data.scope;
  }

  /* ---------- Triggers ---------- */
  function go(query, opts) { return request(query, opts); }

  // Filters (checkboxes) apply as you choose; typing a price waits for a pause.
  document.addEventListener("change", function (e) {
    if (!form || !form.contains(e.target)) return;
    clearTimeout(typingTimer);
    go(paramsFromForm().toString(), { history: "push", fromForm: true });
  });
  document.addEventListener("input", function (e) {
    if (!form || !form.contains(e.target) || e.target.type !== "number") return;
    clearTimeout(typingTimer);
    typingTimer = setTimeout(function () { go(paramsFromForm().toString(), { history: "replace", fromForm: true }); }, 600);
  });
  document.addEventListener("submit", function (e) {
    if (e.target === form) { e.preventDefault(); clearTimeout(typingTimer); go(paramsFromForm().toString(), { history: "push", fromForm: true }); }
    else if (e.target.matches && e.target.matches("[data-sort-form]")) e.preventDefault();
  });

  if (sortSelect) sortSelect.addEventListener("change", function () {
    var params = paramsFromForm();
    params.set("sort", sortSelect.value);
    go(params.toString(), { history: "push", scroll: false });
  });

  // Links that change the listing: tabs, type pills, chips, pagination numbers
  root.addEventListener("click", function (e) {
    var more = e.target.closest("[data-load-more]");
    if (more) {
      if (e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      more.classList.add("is-loading");
      go(queryOf(more.getAttribute("href")), { append: true, history: false });
      return;
    }
    var link = e.target.closest("[data-shop-link], .chip__remove, .chip--clear, .shop-pagination a");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    e.preventDefault();
    go(queryOf(link.getAttribute("href")), { history: "push", scroll: true });
  });

  window.addEventListener("popstate", function () {
    go(location.search.replace(/^\?/, ""), { history: false });
  });

  /* ---------- Filter drawer on small screens ---------- */
  var mq = window.matchMedia("(max-width: 899px)");
  function placeForm() {
    if (!drawerBody || !home) return;
    var target = mq.matches ? drawerBody : home;
    if (form.parentNode !== target) target.appendChild(form);
    home.hidden = mq.matches; // an empty sidebar column would still reserve space
  }
  if (mq.addEventListener) mq.addEventListener("change", placeForm); else if (mq.addListener) mq.addListener(placeForm);
  placeForm();
  scope = (form.querySelector('input[name="category"]') ? form.querySelector('input[name="category"]').value : "") + "/" +
          (form.querySelector('input[name="type"]') ? form.querySelector('input[name="type"]').value : "");

  // Re-establish the history entry so Back works from the first interaction
  history.replaceState({ shop: true }, "", location.href);
})();
