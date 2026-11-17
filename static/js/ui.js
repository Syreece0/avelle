/* ==========================================================================
   AVELLE UI behaviours (no dependencies)
   Everything is wired through data attributes so templates stay declarative:

     [data-dropdown]            wrapper; contains .dropdown__trigger and .dropdown__panel
     [data-dialog-open="id"]    opens <dialog id="id"> as a modal
     [data-dialog-close]        closes the nearest <dialog>
     [data-toggle="id"]         shows/hides the element with that id (search panel)
     [data-qty]                 quantity stepper wrapper (buttons with data-qty-step="1|-1")
     [data-pc-more]             touch devices: reveals a product card's quick controls
     [data-sidebar-toggle]      dashboard sidebar (small screens)
     form[data-loading-form]    submit buttons get .is-loading on submit

   Public API:  window.Avelle.toast({title, message, type})
                window.Avelle.prefersReducedMotion()
   ========================================================================== */
(function () {
  "use strict";

  var reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  function prefersReducedMotion() { return reduceQuery.matches; }

  // <body data-icons="..."> carries the (possibly hashed) sprite URL from Django's static().
  var ICON_HREF = document.body.getAttribute("data-icons") || "/static/img/icons.svg";

  function icon(name) {
    return '<svg class="icon" aria-hidden="true" focusable="false"><use href="' + ICON_HREF + "#i-" + name + '"></use></svg>';
  }

  /* ---------------- Toasts ---------------- */
  function toastRegion() {
    var region = document.getElementById("toast-region");
    if (!region) {
      region = document.createElement("div");
      region.id = "toast-region";
      region.className = "toast-region";
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    return region;
  }

  function toast(opts) {
    opts = opts || {};
    var type = opts.type === "error" ? "error" : "success";
    var el = document.createElement("div");
    el.className = "toast toast--" + type;
    el.setAttribute("role", type === "error" ? "alert" : "status");

    var iconWrap = document.createElement("span");
    iconWrap.className = "toast__icon";
    iconWrap.innerHTML = icon(type === "error" ? "alert" : "check");

    var text = document.createElement("div");
    var title = document.createElement("div");
    title.className = "toast__title";
    title.textContent = opts.title || (type === "error" ? "Something went wrong" : "Done");
    text.appendChild(title);
    if (opts.message) {
      var msg = document.createElement("p");
      msg.className = "toast__msg";
      msg.textContent = opts.message; // textContent: never inject HTML from messages
      text.appendChild(msg);
    }
    if (opts.action && opts.action.href) {
      var link = document.createElement("a");
      link.className = "toast__action";
      link.href = opts.action.href;
      link.textContent = opts.action.label || "View";
      text.appendChild(link);
    }

    var close = document.createElement("button");
    close.type = "button";
    close.className = "toast__close";
    close.setAttribute("aria-label", "Dismiss notification");
    close.innerHTML = icon("close");

    el.appendChild(iconWrap);
    el.appendChild(text);
    el.appendChild(close);
    toastRegion().appendChild(el);

    function dismiss() {
      if (!el.parentNode) return;
      el.classList.add("is-leaving");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, prefersReducedMotion() ? 0 : 300);
    }
    close.addEventListener("click", dismiss);
    setTimeout(dismiss, opts.duration || (type === "error" ? 7000 : 4500));
    return el;
  }

  // Django messages are rendered as hidden <li data-toast-type> items and shown as toasts.
  function seedToasts() {
    document.querySelectorAll(".toast-seed li").forEach(function (li) {
      var level = (li.getAttribute("data-toast-type") || "").indexOf("error") > -1 ? "error" : "success";
      toast({ title: li.textContent.trim(), type: level });
    });
  }

  /* ---------------- Dropdowns ---------------- */
  function closeDropdown(dd) {
    var trigger = dd.querySelector(".dropdown__trigger");
    var panel = dd.querySelector(".dropdown__panel");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    if (panel) panel.hidden = true;
  }
  function closeAllDropdowns(except) {
    document.querySelectorAll("[data-dropdown]").forEach(function (dd) {
      if (dd !== except) closeDropdown(dd);
    });
  }
  document.addEventListener("click", function (e) {
    var trigger = e.target.closest(".dropdown__trigger");
    if (trigger) {
      var dd = trigger.closest("[data-dropdown]");
      var panel = dd.querySelector(".dropdown__panel");
      var open = trigger.getAttribute("aria-expanded") === "true";
      closeAllDropdowns(dd);
      trigger.setAttribute("aria-expanded", String(!open));
      panel.hidden = open;
      if (!open) {
        var first = panel.querySelector("input, button, a");
        if (first && e.detail === 0) first.focus(); // keyboard activation only
      }
      return;
    }
    if (!e.target.closest("[data-dropdown]")) closeAllDropdowns();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var openTrigger = document.querySelector(".dropdown__trigger[aria-expanded='true']");
    if (openTrigger) {
      closeAllDropdowns();
      openTrigger.focus();
    }
  });

  /* ---------------- Dialogs (modal + drawers) ---------------- */
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-dialog-open]");
    if (opener) {
      var dlg = document.getElementById(opener.getAttribute("data-dialog-open"));
      if (dlg && typeof dlg.showModal === "function") {
        dlg.showModal();
        document.body.classList.add("is-locked");
      }
      return;
    }
    var closer = e.target.closest("[data-dialog-close]");
    if (closer) {
      var parent = closer.closest("dialog");
      if (parent) parent.close();
      return;
    }
    // Clicking the backdrop (the <dialog> element itself) closes it
    if (e.target.tagName === "DIALOG" && e.target.open) e.target.close();
  });
  document.addEventListener("close", function (e) {
    if (e.target.tagName === "DIALOG" && !document.querySelector("dialog[open]")) {
      document.body.classList.remove("is-locked");
    }
  }, true);

  /* ---------------- Simple show/hide toggles (search panel) ---------------- */
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-toggle]");
    if (!t) return;
    var target = document.getElementById(t.getAttribute("data-toggle"));
    if (!target) return;
    var willShow = target.hidden;
    target.hidden = !willShow;
    t.setAttribute("aria-expanded", String(willShow));
    if (willShow) {
      var field = target.querySelector("input");
      if (field) field.focus();
    }
  });

  /* ---------------- Quantity stepper ---------------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-qty-step]");
    if (!btn) return;
    var wrap = btn.closest("[data-qty]");
    var input = wrap && wrap.querySelector("input");
    if (!input) return;
    var min = parseInt(input.min || "1", 10);
    var max = parseInt(input.max || "99", 10);
    var next = (parseInt(input.value, 10) || min) + parseInt(btn.getAttribute("data-qty-step"), 10);
    input.value = Math.min(max, Math.max(min, next));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  /* ---------------- Product card: touch reveal ---------------- */
  document.addEventListener("click", function (e) {
    var more = e.target.closest("[data-pc-more]");
    if (!more) return;
    var tilt = more.closest(".pc__tilt");
    var open = tilt.classList.toggle("is-open");
    more.setAttribute("aria-expanded", String(open));
  });

  /* ---------------- Wishlist hearts: handled by cart.js (window.Avelle.wishlistToggle) ----------------
     Fallback only if that script is missing. */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-wishlist-toggle]");
    if (!btn) return;
    e.preventDefault();
    if (window.Avelle && typeof window.Avelle.wishlistToggle === "function") return window.Avelle.wishlistToggle(btn);
    toast({ title: "Couldn't update your wishlist", message: "Please reload the page and try again.", type: "error" });
  });

  /* ---------------- Confirm before destructive forms: <form data-confirm="Remove this?"> ---------------- */
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* ---------------- Dashboard sidebar ---------------- */
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-sidebar-toggle]")) {
      document.body.classList.toggle("dash-nav-open");
    } else if (document.body.classList.contains("dash-nav-open") && !e.target.closest(".dash-sidebar")) {
      document.body.classList.remove("dash-nav-open");
    }
  });

  /* ---------------- Loading state for submitting forms ---------------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches || !form.matches("form[data-loading-form]")) return;
    if (e.defaultPrevented) return;
    form.querySelectorAll("button[type='submit'], .btn[type='submit']").forEach(function (b) {
      b.classList.add("is-loading");
      b.setAttribute("aria-busy", "true");
    });
  });

  /* ---------------- Boot ---------------- */
  window.Avelle = window.Avelle || {};
  window.Avelle.toast = toast;
  window.Avelle.prefersReducedMotion = prefersReducedMotion;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", seedToasts);
  } else {
    seedToasts();
  }
})();
