// Convierte las secciones largas de una pantalla en pestañas (una a la vez).
// Se activa con <main data-secciones>. Las secciones con data-fijo siempre se ven.
(function () {
  "use strict";
  var main = document.querySelector("main[data-secciones]");
  if (!main) return;

  var secciones = Array.prototype.filter.call(main.children, function (el) {
    return el.tagName === "SECTION" && el.querySelector("h2") && !el.hasAttribute("data-fijo");
  });
  if (secciones.length < 2) return;

  var clave = "pestana:" + location.pathname;
  var lista = document.createElement("div");
  lista.className = "secciones";
  lista.setAttribute("role", "tablist");
  lista.setAttribute("aria-label", "Secciones de la página");

  var botones = secciones.map(function (sec, i) {
    var h2 = sec.querySelector("h2");
    var nombre = (h2.firstChild && h2.firstChild.nodeType === 3 ? h2.firstChild.textContent : h2.textContent).trim();
    if (!sec.id) sec.id = "seccion-" + (i + 1);
    h2.classList.add("solo-lectores"); // el nombre ya está en la pestaña
    var b = document.createElement("button");
    b.type = "button";
    b.id = "pestana-" + sec.id;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-controls", sec.id);
    b.textContent = nombre;
    if (sec.querySelector(".msg--error, .aviso--error:not(li), .campo--error")) {
      var punto = document.createElement("span");
      punto.className = "punto";
      punto.setAttribute("aria-label", "tiene errores");
      b.appendChild(punto);
    }
    sec.setAttribute("role", "tabpanel");
    sec.setAttribute("aria-labelledby", b.id);
    b.addEventListener("click", function () { mostrar(i, true); });
    b.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      var n = (i + d + botones.length) % botones.length;
      mostrar(n, true); botones[n].focus(); e.preventDefault();
    });
    lista.appendChild(b);
    return b;
  });

  main.insertBefore(lista, secciones[0]);
  main.setAttribute("data-secciones-activo", "");

  function mostrar(indice, guardar) {
    secciones.forEach(function (sec, i) {
      sec.hidden = i !== indice;
      botones[i].setAttribute("aria-selected", String(i === indice));
      botones[i].tabIndex = i === indice ? 0 : -1;
    });
    if (guardar) {
      try { sessionStorage.setItem(clave, secciones[indice].id); } catch (e) {}
      history.replaceState(null, "", "#" + secciones[indice].id);
    }
    botones[indice].scrollIntoView({ block: "nearest", inline: "center" });
  }

  // Qué pestaña abrir: la que tiene errores, la del enlace (#), la última usada, o la primera.
  var inicial = 0, idGuardado = "";
  try { idGuardado = sessionStorage.getItem(clave) || ""; } catch (e) {}
  var objetivo = location.hash.slice(1) || idGuardado;
  secciones.forEach(function (sec, i) { if (sec.id === objetivo) inicial = i; });
  secciones.forEach(function (sec, i) {
    if (sec.querySelector(".msg--error, .campo--error")) inicial = i;
  });
  mostrar(inicial, false);
})();
