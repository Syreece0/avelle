/* Style-guide demo: renders sample product cards and demonstrates that the three
   animation layers are independent. Demo only; the real system arrives in Phase 6. */
(function () {
  "use strict";
  var sprite = "../img/icons.svg";
  function icon(n, c) { return '<svg class="icon ' + (c || "") + '" aria-hidden="true"><use href="' + sprite + "#i-" + n + '"></use></svg>'; }

  var items = [
    { name: "Linen Camp Shirt", brand: "Avelle Atelier", price: 38500, was: null, badge: "New", tone: "#E9E1D5" },
    { name: "Pleated Wool Trouser", brand: "Avelle Atelier", price: 54000, was: 64000, badge: "-16%", tone: "#DDD3C3" },
    { name: "Silk Slip Dress", brand: "Maison Ade", price: 89500, was: null, badge: "New", tone: "#EFE7DA" },
    { name: "Structured Tote", brand: "Maison Ade", price: 72000, was: null, badge: "", tone: "#E2D8C8" },
    { name: "Cotton Ankara Set", brand: "Avelle Heritage", price: 46000, was: 52000, badge: "-12%", tone: "#E6DDCD" },
    { name: "Boys Oxford Shirt", brand: "Avelle Junior", price: 18500, was: null, badge: "", tone: "#EBE3D6" },
    { name: "Leather Loafer", brand: "Avelle Atelier", price: 67500, was: null, badge: "New", tone: "#DFD5C5" },
    { name: "Baby Knit Romper", brand: "Avelle Junior", price: 14500, was: null, badge: "", tone: "#EDE5D8" }
  ];

  function naira(v) { return "₦" + v.toLocaleString("en-NG"); }

  function cardHTML(p) {
    var badges = p.badge ? '<span class="badge ' + (p.badge[0] === "-" ? "badge--gold" : "badge--ink") + '">' + p.badge + "</span>" : "";
    return '<li class="product-grid__item"><div class="pc" data-pc><div class="pc__float" data-pc-float>' +
      '<article class="pc__tilt" data-pc-tilt>' +
      '<a class="pc__media" href="#" tabindex="-1" aria-hidden="true" style="background:' + p.tone + '"><span class="pc__placeholder">' + icon("shirt") + "</span></a>" +
      '<div class="pc__badges">' + badges + "</div>" +
      '<button class="pc__wish" type="button" aria-pressed="false" aria-label="Save ' + p.name + ' to wishlist">' + icon("heart") + "</button>" +
      '<div class="pc__body"><span class="pc__brand">' + p.brand + '</span><h3 class="pc__name"><a href="#">' + p.name + "</a></h3>" +
      '<p class="pc__price price"><span class="pc__price-now">' + naira(p.price) + "</span>" + (p.was ? '<span class="pc__price-was">' + naira(p.was) + "</span>" : "") + "</p></div>" +
      '<button class="pc__more" type="button" data-pc-more aria-expanded="false" aria-label="Show options for ' + p.name + '">' + icon("plus") + "</button>" +
      '<div class="pc__extra"><p class="pc__sizes">Sizes <strong>S, M, L, XL</strong></p><div class="pc__actions">' +
      '<a class="btn btn--sm" href="#">' + icon("bag", "icon--sm") + ' Choose size</a><button class="btn btn--secondary btn--sm" type="button">Quick view</button></div></div>' +
      "</article></div></div></li>";
  }

  var grid = document.getElementById("demo-grid");
  if (!grid) return;
  grid.innerHTML = items.map(cardHTML).join("");
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var MIXED = [
    { fx: "0px", fy: "48px", fs: 1 }, { fx: "-60px", fy: "0px", fs: 1 }, { fx: "60px", fy: "0px", fs: 1 },
    { fx: "0px", fy: "0px", fs: 0.94 }
  ];
  var DIRS = {
    bottom: function () { return { fx: "0px", fy: "48px", fs: 1 }; },
    left: function () { return { fx: "-64px", fy: "0px", fs: 1 }; },
    right: function () { return { fx: "64px", fy: "0px", fs: 1 }; },
    mixed: function (i) { return MIXED[i % MIXED.length]; }
  };

  function play(mode) {
    var cards = grid.querySelectorAll("[data-pc]");
    cards.forEach(function (pc, i) {
      var float = pc.querySelector("[data-pc-float]");
      // Cancel anything in flight so rapid switching never overlaps
      pc.classList.remove("demo-enter");
      float.classList.remove("demo-float");
      void pc.offsetWidth;
      if (reduce) return;
      var d = DIRS[mode](i);
      pc.style.setProperty("--fx", d.fx); pc.style.setProperty("--fy", d.fy); pc.style.setProperty("--fs", d.fs);
      pc.style.setProperty("--d", (i * 70) + "ms");
      pc.classList.add("demo-enter");
      float.style.setProperty("--fdur", (3.2 + (i % 4) * 0.5) + "s");
      float.style.setProperty("--fdelay", (i * -0.45) + "s");
      pc.onanimationend = function (e) {
        if (e.target === pc) float.classList.add("demo-float"); // float starts only after the entrance ends
      };
    });
  }

  document.querySelectorAll("[data-demo-mode]").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("[data-demo-mode]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      play(b.getAttribute("data-demo-mode"));
    });
  });

  // Tilt layer: pointer position drives CSS variables on the innermost element only
  if (window.matchMedia("(hover: hover) and (pointer: fine)").matches && !reduce) {
    grid.addEventListener("pointermove", function (e) {
      var tilt = e.target.closest("[data-pc-tilt]");
      if (!tilt) return;
      var r = tilt.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width - 0.5;
      var py = (e.clientY - r.top) / r.height - 0.5;
      tilt.classList.add("is-tracking", "is-active");
      tilt.style.setProperty("--tilt-y", (px * 9).toFixed(2) + "deg");
      tilt.style.setProperty("--tilt-x", (py * -9).toFixed(2) + "deg");
    });
    grid.addEventListener("pointerout", function (e) {
      var tilt = e.target.closest("[data-pc-tilt]");
      if (!tilt || tilt.contains(e.relatedTarget)) return;
      tilt.classList.remove("is-tracking", "is-active");
      tilt.style.setProperty("--tilt-x", "0deg");
      tilt.style.setProperty("--tilt-y", "0deg");
    });
  }

  grid.addEventListener("click", function (e) {
    var w = e.target.closest(".pc__wish");
    if (w) w.setAttribute("aria-pressed", String(w.getAttribute("aria-pressed") !== "true"));
  });

  play("mixed");
})();
