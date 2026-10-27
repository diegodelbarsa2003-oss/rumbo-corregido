// Carrusel del banner de destinos: automático, con flechas y puntos.
(function () {
  "use strict";
  var banner = document.querySelector("[data-banner]");
  if (!banner) return;
  var slides = banner.querySelectorAll(".banner__slide");
  var puntos = banner.querySelectorAll("[data-banner-punto]");
  if (slides.length < 2) return;
  var actual = 0, timer = null;
  var reducir = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ir(n) {
    actual = (n + slides.length) % slides.length;
    slides.forEach(function (s, i) {
      s.classList.toggle("is-activa", i === actual);
      s.setAttribute("aria-hidden", String(i !== actual));
    });
    puntos.forEach(function (p, i) { p.classList.toggle("is-activa", i === actual); });
  }
  function iniciar() { if (!reducir) { detener(); timer = setInterval(function () { ir(actual + 1); }, 5000); } }
  function detener() { if (timer) { clearInterval(timer); timer = null; } }

  banner.querySelector("[data-banner-ant]").addEventListener("click", function () { ir(actual - 1); iniciar(); });
  banner.querySelector("[data-banner-sig]").addEventListener("click", function () { ir(actual + 1); iniciar(); });
  puntos.forEach(function (p) {
    p.addEventListener("click", function () { ir(Number(p.dataset.bannerPunto)); iniciar(); });
  });
  banner.addEventListener("mouseenter", detener);
  banner.addEventListener("mouseleave", iniciar);
  banner.addEventListener("focusin", detener);
  banner.addEventListener("focusout", iniciar);
  iniciar();
})();
