// Mostrar/ocultar contraseña y verificar en vivo que ambas coincidan.
(function () {
  "use strict";

  document.querySelectorAll(".ver-clave").forEach(function (boton) {
    boton.addEventListener("click", function () {
      var campo = document.getElementById(boton.dataset.objetivo);
      var visible = campo.type === "text";
      campo.type = visible ? "password" : "text";
      boton.textContent = visible ? "Mostrar" : "Ocultar";
      boton.setAttribute("aria-pressed", String(!visible));
    });
  });

  var clave = document.getElementById("password");
  var confirmar = document.getElementById("confirmar");
  if (!clave || !confirmar) return;

  var mensaje = document.getElementById("confirmar-msg");

  function revisar() {
    if (!confirmar.value) {
      mensaje.textContent = "";
      mensaje.classList.remove("msg--error");
      return;
    }
    var coincide = clave.value === confirmar.value;
    mensaje.textContent = coincide ? "" : "Las contraseñas no coinciden.";
    mensaje.classList.toggle("msg--error", !coincide);
  }

  clave.addEventListener("input", revisar);
  confirmar.addEventListener("input", revisar);
})();
