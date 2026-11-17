/* ==========================================================================
   Homepage interactions
   - Newsletter signup (fetch, works without GSAP)
   - GSAP hero intro (enhancement only). Scroll reveals, parallax and product-card
     motion live in motion.js, shared by every page.

   If GSAP/ScrollTrigger fail to load, or the visitor prefers reduced motion,
   everything stays visible and static. Mobile gets reveals but no parallax.
   ========================================================================== */
(function () {
  "use strict";

  var root = document.documentElement;

  /* ---------------- Newsletter ---------------- */
  function initNewsletter() {
    var form = document.querySelector("[data-newsletter]");
    var status = document.querySelector("[data-newsletter-status]");
    if (!form || !status || !window.fetch) return; // falls back to a normal form POST

    function setStatus(message, isError) {
      status.textContent = message;
      status.classList.toggle("is-error", !!isError);
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var email = form.elements.email;
      if (!email.value.trim() || !email.checkValidity()) {
        setStatus("Please enter a valid email address.", true);
        email.focus();
        return;
      }
      var button = form.querySelector("button[type='submit']");
      button.classList.add("is-loading");
      button.disabled = true;
      setStatus("", false);

      fetch(form.action, {
        method: "POST",
        body: new FormData(form), // includes the CSRF token and honeypot field
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
        credentials: "same-origin"
      })
        .then(function (response) {
          return response.json().catch(function () {
            return { ok: false, message: "Something went wrong. Please try again." };
          });
        })
        .then(function (data) {
          setStatus(data.message, !data.ok);
          if (data.ok) form.reset();
        })
        .catch(function () {
          setStatus("Network error. Please check your connection and try again.", true);
        })
        .then(function () {
          button.classList.remove("is-loading");
          button.disabled = false;
        });
    });
  }

  /* ---------------- GSAP enhancement ---------------- */
  function heroIntro() {
    var lines = gsap.utils.toArray("[data-hero-line]");
    var items = gsap.utils.toArray("[data-hero-item]");
    var ghost = document.querySelector("[data-hero-ghost]");
    var image = document.querySelector(".hero__img");

    // Take over the hidden state from the CSS class, then play.
    gsap.set(lines, { yPercent: 110, opacity: 1 });
    gsap.set(items, { autoAlpha: 0, y: 24 });
    if (ghost) gsap.set(ghost, { autoAlpha: 0 });
    root.classList.remove("hero-pending");

    var tl = gsap.timeline({ defaults: { ease: "power3.out" } });
    if (image) tl.fromTo(image, { scale: 1.14 }, { scale: 1, duration: 2.6, ease: "power2.out" }, 0);
    if (ghost) tl.to(ghost, { autoAlpha: 1, duration: 2 }, 0);
    tl.to(".hero__eyebrow", { autoAlpha: 1, y: 0, duration: 0.8 }, 0.25)
      .to(lines, { yPercent: 0, duration: 1.25, stagger: 0.14 }, 0.3)
      .to(".hero__lead, .hero__cta, .hero__scroll", { autoAlpha: 1, y: 0, duration: 0.9, stagger: 0.12 }, "-=0.55");
  }

  function initMotion() {
    var reduced = window.Avelle && window.Avelle.prefersReducedMotion && window.Avelle.prefersReducedMotion();
    if (!window.gsap || !window.ScrollTrigger || reduced) {
      root.classList.remove("hero-pending"); // content stays visible and static
      return;
    }
    gsap.registerPlugin(ScrollTrigger);

    var mm = gsap.matchMedia();
    mm.add(
      {
        desktop: "(min-width: 900px) and (prefers-reduced-motion: no-preference)",
        mobile: "(max-width: 899px) and (prefers-reduced-motion: no-preference)"
      },
      function (context) {
        heroIntro();
        return function () {}; // matchMedia reverts animations when the breakpoint changes
      }
    );
    mm.add("(prefers-reduced-motion: reduce)", function () {
      root.classList.remove("hero-pending");
    });
  }

  initNewsletter();
  initMotion();
})();
