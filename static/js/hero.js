/* Hero framing. A landscape photo fills the hero (cover). A portrait photo or video would lose most of its
   height that way, so it is shown whole instead (contain), on the right, over a soft blurred copy of itself. */
(function () {
  "use strict";
  var hero = document.querySelector("[data-hero]");
  var media = hero && hero.querySelector(".hero__img");
  if (!media) return;

  function frame() {
    var w = media.naturalWidth || media.videoWidth, h = media.naturalHeight || media.videoHeight;
    if (w && h) hero.classList.toggle("hero--portrait", h > w * 1.05);
  }
  if (media.tagName === "VIDEO") {
    if (media.readyState >= 1) frame(); else media.addEventListener("loadedmetadata", frame, { once: true });
  } else if (media.complete) {
    frame();
  } else {
    media.addEventListener("load", frame, { once: true });
  }
})();
