# Rumbo – Sistema de gestión y reserva de paquetes turísticos

Universidad Cooperativa de Colombia · Ingeniería de Sistemas · Ingeniería de Software

**Alcance de esta entrega:** los 28 requerimientos de la entrega anterior (RF-01 a RF-28) más 14
requerimientos nuevos (RF-29 a RF-42), para un total de 42. El docente corrigió el enunciado de
los antiguos RF-29 a RF-35 (que eran de cara al cliente) y los reemplazó por 7 requerimientos de
gestión operativa de la agencia (hoteles, transporte y vuelos), y pidió sumar 7 más con el mismo
enfoque operativo (RF-36 a RF-42). Esta entrega reemplaza por completo el contenido anterior de
RF-29 a RF-35.

**Ya implementado (RF-01 a RF-21, entrega anterior):**
- RF-01 Registro de cuenta del cliente (el administrador no se registra: la agencia le entrega sus credenciales y un token)
- RF-02 Autenticación (inicio de sesión)
- RF-03 Recuperar contraseña
- RF-04 Editar perfil y cambiar contraseña
- RF-05 Buscar destinos por nombre, país o región
- RF-06 Filtrar paquetes por precio, duración y categoría
- RF-07 Detalle del paquete (itinerario, incluidos, precio)
- RF-08 Comparar dos o más paquetes turísticos
- RF-09 Disponibilidad de cupos por fecha
- RF-10 Reservar un paquete seleccionando fecha y número de personas
- RF-11 Seleccionar servicios adicionales (seguro, transporte, tours)
- RF-12 Número de confirmación único por reserva
- RF-13 Cancelar una reserva dentro de los plazos establecidos
- RF-14 Modificar la fecha de una reserva ya realizada
- RF-15 Aviso de confirmación al completar una reserva
- RF-16 Pago en línea con tarjeta de crédito o débito
- RF-17 Pago en cuotas cuando el paquete lo permite
- RF-18 Comprobante de pago en PDF
- RF-19 Validar el cupo disponible antes de confirmar el pago
- RF-20 Calificar y comentar un paquete después del viaje
- RF-21 Solicitar a un asesor mediante chat de soporte

**Implementado (RF-22 a RF-28, entrega anterior):**
- RF-22 Notificar al cliente sobre cambios de itinerario o del destino de un paquete que ya
  reservó. Panel del cliente → "Notificaciones" (con contador de avisos sin leer en la barra).
- RF-23 El administrador crea, edita y elimina (desactiva) paquetes turísticos, junto con su
  itinerario, sus incluidos, sus servicios adicionales y sus fechas de salida con cupos.
  Panel del administrador → "Paquetes".
- RF-24 El administrador genera reportes de ventas por período (rango de fechas), con el total
  vendido, el desglose por paquete y el detalle de cada pago. Panel del administrador → "Reportes".
- RF-25 El administrador gestiona el inventario de proveedores (hoteles y restaurantes) por
  destino: crear, editar, activar/desactivar y eliminar. Panel del administrador → "Proveedores".
- RF-26 El cliente consulta los países disponibles como destino turístico, con el número de
  destinos y paquetes de cada uno. Panel del cliente → "Países".
- RF-27 El cliente filtra los destinos turísticos por región con un menú desplegable, además de
  la búsqueda libre de RF-05. Está en la misma pantalla de "Destinos".
- RF-28 El cliente busca paquetes turísticos escribiendo el nombre de un destino. Ya lo cubre el
  buscador de la pantalla "Paquetes" (RF-06), que compara el texto también contra el nombre del
  destino, el país y la región; no requirió una pantalla nueva.

> Nota: en una entrega anterior, RF-29 a RF-35 habían sido mostrar el precio total estimado al
> reservar y registrar los datos de los viajeros de una reserva. Esas dos pantallas se dejaron
> (siguen siendo útiles: el precio total se sigue viendo en el detalle del paquete al elegir
> personas y servicios, y "Mis reservas" sigue teniendo la sección "Datos de los viajeros"), pero
> ya no se documentan bajo esos números de RF porque el docente les dio otro contenido.

**Nuevo en esta entrega — gestión operativa (RF-29 a RF-42):**

Toda la gestión operativa se encuentra en el panel del administrador → "Operación" (catálogos de
hoteles, conductores, vehículos, pilotos y aeronaves) y, dentro de cada paquete
("Paquetes" → "Editar" → "Recursos operativos →"), la asignación de esos recursos a las fechas de
salida de ese paquete.

- RF-29 El administrador registra los horarios de check-in y check-out de cada hotel asociado a
  la agencia. Los horarios se pueden registrar al crear el hotel y editar después desde
  "Operación" → "Hoteles".
- RF-30 El administrador registra las políticas y condiciones de cada hotel, como cancelaciones,
  mascotas y restricciones de hospedaje. Se guardan junto con la información del hotel y se pueden
  modificar desde "Editar".
- RF-31 El administrador registra los tipos de habitación de cada hotel (tipo, capacidad, tarifa
  por noche, características y número de habitaciones de ese tipo). Dentro de cada hotel, en
  "Operación", sección "Tipos de habitación" (y puede activarlos/desactivarlos).
- RF-32 El administrador consulta la disponibilidad de habitaciones según las fechas de un
  paquete. Al asignar una habitación a una salida del paquete (en "Recursos operativos"), la
  tabla de hoteles asignados muestra cuántas de esas habitaciones ya están comprometidas para esa
  fecha, de las disponibles en total.
- RF-33 El administrador registra conductores (datos personales, contacto y documento). Panel
  "Operación" → sección "Conductores".
- RF-34 El administrador registra los vehículos disponibles para transporte turístico (placa,
  tipo, capacidad y estado). Panel "Operación" → sección "Vehículos".
- RF-35 El administrador asigna un conductor y un vehículo al transporte de una fecha de salida
  de un paquete. "Recursos operativos" del paquete → sección "Transporte".
- RF-36 El administrador consulta la disponibilidad de conductores y vehículos para una fecha:
  al asignar transporte, el sistema avisa si ese conductor o ese vehículo ya tenían otro servicio
  asignado el mismo día, y el panel de conflictos (ver RF-42) los lista.
- RF-37 El administrador registra pilotos (datos profesionales, contacto, documento y licencia).
  Panel "Operación" → sección "Pilotos".
- RF-38 El administrador registra aeronaves (matrícula, modelo, capacidad) y, por cada paquete,
  los vuelos que lo componen (aeronave, origen, destino, fecha y horarios). Aeronaves en
  "Operación"; vuelos en "Recursos operativos" del paquete → sección "Vuelos".
- RF-39 El administrador asigna un piloto a cada vuelo programado. Desde la tabla de vuelos, en
  "Recursos operativos" del paquete.
- RF-40 El administrador consulta la disponibilidad de pilotos para una fecha: al asignar un
  piloto a un vuelo, el sistema avisa si ya tenía otro vuelo ese mismo día.
- RF-41 El administrador diseña y guarda diferentes versiones de un paquete para comparar sus
  combinaciones de servicios, duración y costo antes de publicar una versión definitiva. En
  "Paquetes" → "Editar" → "Versiones del paquete" puede guardar borradores, comparar sus datos
  en una tabla y publicar la versión elegida como definitiva.
- RF-42 El sistema detecta y notifica posibles conflictos de disponibilidad entre hoteles,
  conductores, vehículos y pilotos: apenas se genera una asignación que choca con otra (mismo
  conductor, vehículo o piloto el mismo día, o más habitaciones asignadas que las disponibles), se
  lo avisa al administrador al momento (mensaje de error al guardar) y además queda visible en una
  lista de conflictos vigentes, arriba del panel "Operación" y de "Recursos operativos" de cada
  paquete afectado.

**Cómo el administrador dispara la notificación de RF-22 para probarla:** entra a
"Paquetes" → "Editar" sobre un paquete que un cliente ya tenga reservado (pendiente o
confirmado) → agrega o elimina una actividad del itinerario, o cambia algún dato general (precio,
destino, etc.). El sistema le confirma a cuántos clientes avisó, y ese cliente lo verá en su
panel, en "Notificaciones".

**Cómo probar RF-29, RF-30 y RF-41:** 1) En "Operación", registra un hotel indicando sus
horarios de check-in y check-out y sus políticas y condiciones; luego entra a "Editar" para
comprobar que se pueden modificar. 2) En "Paquetes" → "Editar", entra a "Versiones del paquete",
crea dos o más borradores con diferentes combinaciones de servicios, duración y costo. 3) Compara
las filas de la tabla y publica una de las versiones; el paquete adoptará su duración, costo y
combinación de servicios como configuración definitiva.

## Rediseño de la interfaz

- **Administrador:** menú lateral agrupado (Catálogo, Operación, Negocio, Ayuda). Las pantallas largas
  (Operación, Editar paquete, Recursos operativos, Reportes) se dividen en pestañas (`static/js/paneles.js`).
- **Cliente:** barra superior con las secciones principales y menú de usuario.
- **Panel de inicio:** muestra datos reales (próximo viaje, reservas sin pagar, ventas del mes, conflictos y
  paquetes incompletos) en lugar de una tabla de módulos.
- **Requerimientos:** los códigos RF ya no aparecen en las pantallas; ahora están en la página
  `/requerimientos` (buscable y filtrable por actor), con la pantalla donde se usa cada uno.
- Estilos en `static/css/estilos.css`; iconos en `templates/_iconos.html`.

## Tecnologías

| Capa | Tecnología |
|---|---|
| Backend | Python 3 + Flask |
| Base de datos | SQLite (incluida en Python, no requiere instalación) |
| Frontend | HTML5, CSS3 y JavaScript (plantillas Jinja2) |
| Comprobantes en PDF | ReportLab |
| Seguridad | Contraseñas con hash (scrypt), token CSRF, sesiones con cookie HttpOnly |

## Cómo ejecutarlo en Visual Studio Code

1. Instala **Python 3.10 o superior** (https://www.python.org) y la extensión **Python** de VS Code.
2. Abre la carpeta del proyecto en VS Code (`Archivo > Abrir carpeta`).
3. Abre la terminal (`Ctrl + ñ`) y ejecuta:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python app.py
```

4. Abre http://127.0.0.1:5000 en el navegador.

La base de datos `instance/turismo.db` se crea sola la primera vez. Si quieres empezar de cero
(borrar todos los usuarios de prueba), simplemente borra ese archivo y vuelve a ejecutar `python app.py`.

## Estructura

```
rumbo/
├── app.py                          # Rutas, validaciones, reglas de negocio y acceso a datos
├── requirements.txt
├── templates/
│   ├── base.html                   # Estructura común
│   ├── layout_acceso.html          # Pantalla dividida (inicio y acceso)
│   ├── inicio.html                 # Elegir Cliente o Administrador
│   ├── acceso.html                 # Iniciar sesión / Crear cuenta
│   ├── recuperar.html              # RF-03: solicitar enlace de restablecimiento
│   ├── restablecer.html            # RF-03: crear nueva contraseña desde el enlace
│   ├── perfil.html                 # RF-04: editar datos y cambiar contraseña
│   ├── panel.html                  # Panel de cliente y de administrador
│   ├── _barra_cliente.html         # Barra de navegación del cliente (Destinos, Paquetes...)
│   ├── _barra_admin.html           # Barra de navegación del administrador (Paquetes, Proveedores, Reportes)
│   ├── cliente_destinos.html       # RF-05/RF-27: buscar destinos + filtro por región
│   ├── cliente_paises.html         # RF-26: países disponibles
│   ├── cliente_paquetes.html       # RF-06/RF-28: filtrar paquetes + buscar por destino + comparar
│   ├── cliente_paquete_detalle.html# RF-07/RF-09: detalle, cupos y formulario de reserva
│   ├── cliente_comparar.html       # RF-08: comparación lado a lado
│   ├── cliente_reservas.html       # Listado de "Mis reservas"
│   ├── cliente_reserva_detalle.html# RF-13/14/16/17/18/20: pagar, cancelar, calificar, viajeros...
│   ├── cliente_soporte.html        # RF-21: chat de soporte
│   ├── cliente_notificaciones.html # RF-22: avisos de cambios de itinerario
│   ├── admin_paquetes.html         # RF-23: listado de paquetes (crear/editar/eliminar)
│   ├── admin_paquete_formulario.html # RF-23: crear paquete
│   ├── admin_paquete_editar.html   # RF-23: editar datos, itinerario, incluidos, servicios y salidas
│   ├── admin_reportes.html         # RF-24: reportes de ventas por período
│   ├── admin_proveedores.html      # RF-25: inventario de proveedores
│   ├── admin_proveedor_formulario.html # RF-25: crear/editar proveedor
│   ├── admin_operacion.html        # RF-29 a RF-34/RF-37/RF-38: catálogos operativos
│   ├── admin_hotel_formulario.html # RF-30: editar un hotel
│   ├── admin_paquete_recursos.html # RF-32/RF-35/RF-36/RF-38 a RF-42: recursos de un paquete
│   ├── _campos.html                # Componentes de formulario reutilizables
│   └── ...
├── static/
│   ├── css/estilos.css
│   └── js/acceso.js                # Mostrar contraseña y verificación en vivo
└── instance/                        # Base de datos (no se sube a Git)
```

## Reglas de validación

**Registro (RF-01):**
- Nombres y apellidos: solo letras, 2 a 60 caracteres.
- Correo electrónico válido y único en todo el sistema.
- Contraseña: mínimo 8 caracteres con letras y números.
- Confirmar contraseña: debe coincidir.
- Cada cuenta pertenece a un solo rol: un cliente no puede entrar por la puerta de administrador y viceversa.

**Editar perfil (RF-04):**
- Mismas reglas de nombres, apellidos y correo que el registro.
- El correo debe seguir siendo único (no puede quedar igual al de otra cuenta).
- Para cambiar la contraseña hay que escribir la contraseña actual correcta.
- La nueva contraseña no puede ser igual a la actual.

## Cuenta de administrador y token de la agencia

Nadie puede registrarse como administrador desde la web: la ruta de registro solo existe para el
cliente (`/acceso/administrador/registro` responde 404). La cuenta de administrador la establece la
agencia, que entrega al encargado tres datos: correo, contraseña y **token de acceso de la agencia**.
El inicio de sesión como administrador exige los tres.

| Dato | Valor por defecto (solo pruebas) | Variable de entorno |
|---|---|---|
| Correo | `admin@rumbo.com` | `ADMIN_CORREO` |
| Contraseña | `Rumbo2026Admin` | `ADMIN_PASSWORD` |
| Token de la agencia | `RUMBO-AGENCIA-2026` | `ADMIN_TOKEN` |

- La cuenta se crea sola la primera vez que arranca la app, si todavía no existe ningún administrador.
- Si el token, el correo o la contraseña fallan, el mensaje es el mismo (no dice cuál falló).
- El administrador no puede recuperar la contraseña desde la pantalla; se la pide al encargado de la agencia.
- Ejemplo en Windows: `set ADMIN_TOKEN=MiTokenSecreto` antes de `python app.py`.

## Fotos de los destinos

Cada destino muestra su foto en el panel del cliente, en "Destinos", en "Paquetes", en el detalle del
paquete y en la pantalla de inicio. Las fotos vienen de Wikimedia Commons (licencias Creative Commons,
se requiere conexión a internet): Cartagena (`70 - Carthagène - Décembre 2008.jpg`), Eje Cafetero
(`Valle de Cocora, Colombia 04.jpg`), San Andrés (`Johnny Cay (8304072347).jpg`), Tayrona
(`Arrecifes.jpg`), Cusco (`80 - Machu Picchu - Juin 2009 - edit.jpg`) y Ciudad de México
(`Federal District buildings on Zocalo Mexico City.jpg`). Los autores y licencias se ven en la página
de cada archivo en commons.wikimedia.org.

Para usar tus propias fotos sin internet, guarda un archivo en `static/img/destinos/` con el nombre del
destino en minúsculas, sin tildes y con guiones (`cartagena-de-indias.jpg`, `san-andres.jpg`...). Ese
archivo tiene prioridad sobre la foto de internet. Si una foto no carga, la tarjeta muestra un fondo
de color con el nombre del destino.

## Nota sobre "recuperar contraseña" (RF-03)

(Aplica solo a clientes.) Este proyecto no tiene un servidor de correo configurado (eso requeriría una cuenta SMTP real,
como Gmail o SendGrid, con usuario y contraseña de aplicación). Por eso, en vez de enviar el
enlace de restablecimiento por correo, la aplicación lo muestra directamente en pantalla, con una
nota que lo explica. La lógica es la misma que usaría un sistema real:

- Se genera un token único e impredecible.
- El enlace vence a los 30 minutos.
- El enlace se invalida apenas se usa una vez.
- El sistema responde igual exista o no una cuenta con ese correo, para no revelar esa información.

Lo único que cambia frente a un sistema en producción es el medio de entrega del enlace.

## Catálogo de ejemplo (destinos y paquetes)

RF-22 en adelante (que el administrador cree y edite paquetes) es de la siguiente entrega, así
que por ahora `app.py` siembra automáticamente 6 destinos y 6 paquetes de ejemplo la primera vez
que se ejecuta (función `sembrar_catalogo`), cada uno con itinerario, incluidos, servicios
adicionales y varias fechas de salida con cupos. Así el cliente tiene algo real que buscar,
filtrar, comparar y reservar.

**Fecha de prueba:** cada paquete incluye una fecha de salida que ya pasó (hace 2 días), marcada
en pantalla como "(fecha de prueba, ya pasó)". Se dejó así a propósito para que el docente pueda
probar de inmediato todo el flujo sin esperar semanas:
1. Reserva ese paquete eligiendo la fecha de prueba.
2. Paga la reserva (RF-16/RF-17) y descarga el comprobante en PDF (RF-18).
3. Como la fecha ya pasó, el botón para calificar (RF-20) aparece de inmediato.
4. Para probar RF-13 (cancelar) y RF-14 (modificar fecha), reserva con una de las fechas futuras:
   ahí sí aplican los plazos de cancelación normales.

## Reglas de negocio de este módulo (RF-05 a RF-21)

- **RF-09/RF-19 (cupos):** el cupo de una salida se descuenta apenas se crea la reserva (para que
  nadie más pueda reservar sobre el mismo cupo mientras el cliente paga) y se vuelve a validar al
  confirmar el pago. Si la reserva se cancela o cambia de fecha, el cupo se libera.
- **RF-13/RF-14 (plazos):** cada paquete tiene su propio plazo de cancelación en días
  (`plazo_cancelacion_dias`); cancelar o cambiar la fecha solo es posible si aún faltan, como
  mínimo, esos días para el viaje.
- **RF-16/RF-17 (pago):** es una pasarela simulada (no hay una cuenta real con un banco); valida
  formato de tarjeta (16 dígitos), vencimiento futuro (MM/AA) y CVV, y solo guarda los últimos 4
  dígitos de la tarjeta. Las cuotas (1, 3, 6 o 12) solo se ofrecen si el paquete las permite.
- **RF-18 (comprobante):** se genera al vuelo con ReportLab a partir del pago y la reserva; no se
  guarda un PDF por separado en disco, cada descarga se arma en el momento.
- **RF-20 (calificar):** solo se habilita cuando la reserva está pagada y la fecha del viaje ya
  pasó, y solo se puede calificar una vez por reserva.
- **RF-21 (soporte):** como el panel de administrador para atender el chat es del siguiente
  entregable (RF-22 en adelante), el sistema confirma la recepción del mensaje con una respuesta
  automática del lado del servidor.

## Reglas de negocio de los requerimientos nuevos (RF-22 a RF-25)

- **RF-22 (notificaciones):** se generan solo cuando el paquete editado tiene clientes con una
  reserva en estado "pendiente" o "confirmada" (no se notifica a reservas ya canceladas o
  finalizadas). Por ahora el "canal" es la bandeja dentro de la app (tabla `notificaciones`),
  igual que RF-03/RF-15 muestran el enlace o el aviso en pantalla en vez de enviarlo por correo:
  no hay un servidor de correo conectado en este proyecto.
- **RF-23 (paquetes):** "eliminar" es un borrado lógico (`activo = 0`) y no uno físico, porque un
  paquete puede tener reservas, pagos y calificaciones asociadas que no se deben perder; el
  paquete desactivado deja de aparecer en el catálogo del cliente pero el administrador lo puede
  reactivar. Para que un paquete nuevo se pueda reservar necesita, además de sus datos generales,
  al menos una fecha de salida con cupos.
- **RF-24 (reportes):** se consideran "ventas" los pagos ya aprobados (tabla `pagos`), filtrados
  por la fecha en que se realizó el pago; el reporte muestra el total del período, el desglose por
  paquete y el detalle de cada pago.
- **RF-25 (proveedores):** cada proveedor (hotel o restaurante) pertenece a un destino existente;
  el administrador puede editarlo, desactivarlo/activarlo o eliminarlo del inventario en cualquier
  momento, ya que no está referenciado por otras tablas.

## Reglas de negocio de los requerimientos nuevos (RF-29 a RF-42)

- **Precio total y viajeros (herencia de una entrega anterior, ya no ligados a estos números de
  RF):** el total estimado al reservar se calcula en el navegador con JavaScript, a partir del
  precio por persona, el número de personas y los servicios marcados; el total real y definitivo
  siempre se calcula y valida en el servidor (`subtotal_paquete`, `subtotal_servicios`, `total`).
  Los datos de cada viajero se guardan en `reserva_viajeros` y solo se pueden agregar/quitar
  mientras la reserva esté "pendiente" o "confirmada".
- **RF-29/RF-30 (hoteles):** un hotel pertenece a un destino existente. Desactivarlo no borra sus
  tipos de habitación ni las asignaciones ya hechas a paquetes, para no perder el historial.
- **RF-31/RF-32 (habitaciones y disponibilidad):** cada tipo de habitación tiene un número fijo de
  unidades (`cupos_totales`); la disponibilidad para una fecha se calcula sumando cuánto se ha
  asignado ya de ese mismo tipo de habitación en esa fecha, en cualquier paquete (no solo en el
  que se está editando), porque dos paquetes distintos con la misma fecha de viaje comparten el
  mismo inventario real de habitaciones del hotel.
- **RF-33/RF-34 (conductores y vehículos):** solo se registran sus datos; no tienen un estado
  "editar" propio (no lo pidió el enunciado), solo activar/desactivar. La placa del vehículo debe
  ser única.
- **RF-35/RF-36 (transporte y su disponibilidad):** un conductor o un vehículo se consideran
  "ocupados" si ya tienen otra asignación de transporte ese mismo día, sin impedir la asignación
  (el administrador puede tener una razón válida para duplicarla, por ejemplo dos turnos), pero
  el sistema se lo advierte de inmediato y lo deja visible como conflicto.
- **RF-37 a RF-40 (pilotos, vuelos y su disponibilidad):** un piloto solo puede asignarse a un
  vuelo ya existente del paquete (primero se registra el vuelo con su aeronave, luego se le asigna
  el piloto); igual que con el transporte, un piloto con dos vuelos el mismo día no se bloquea,
  pero se avisa como conflicto.
- **RF-41 (versiones):** las alternativas de duración, costo y combinación de servicios se gestionan desde "Versiones del paquete" antes de publicar una versión definitiva.

## Notas para producción

- Definir la variable de entorno `SECRET_KEY` con un valor largo y aleatorio.
- Ejecutar sin `debug=True`.
- Conectar un servicio de correo real (SMTP) para enviar el enlace de RF-03 y el aviso de
  confirmación de reserva de RF-15 por email real, en vez de mostrarlos en pantalla.
- Conectar una pasarela de pago real (por ejemplo PSE, Wompi o Stripe) para RF-16/RF-17 en vez de
  la validación simulada de tarjeta.
- Conectar el chat de soporte (RF-21) a un panel real de asesores/administrador.
- Cambia `SECRET_KEY`, `ADMIN_TOKEN`, `ADMIN_CORREO` y `ADMIN_PASSWORD` por valores propios (variables
  de entorno) antes de publicar el sistema; los valores por defecto son solo para pruebas.
- El catálogo de paquetes (`sembrar_catalogo`) es solo para esta entrega; en la siguiente
  (RF-22 en adelante) el administrador lo reemplaza por su propia gestión desde el panel.
