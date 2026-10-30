# GamePad Hub

Usa un dispositivo Android (un handheld con mando, un móvil o una tablet) como **mando y segunda pantalla** de un PC con Linux, por Wi-Fi local:

- **Mando virtual Xbox 360** en el PC: sirve para Steam Big Picture y para cualquier juego.
- **Telemetría** en Android: FPS y frametimes (vía MangoHud), CPU, GPU, RAM, latencia y jitter.
- **Datos del juego** leídos de memoria con plugins por juego (vida, magia, dinero, equipo…).
- **Nada se ejecuta como root.**

Componentes:

| Componente | Dónde corre | Qué es |
|---|---|---|
| Servicio (`gamepad serve`) | PC (host) | Mando virtual, telemetría, web y WebSocket en el puerto 8888 |
| Lanzador (`gamepad run %command%`) | PC, lo arranca Steam | Lanza el juego como hijo, activa MangoHud y ejecuta el plugin |
| App Android (`android/`) | Android | Cliente nativo y ligero (≈32 KB). Recomendado |
| Cliente web (`web/`) | Navegador del Android | Alternativa sin instalar nada: `http://IP-DEL-PC:8888` |
| Plugins (`plugins/`) | PC, dentro del lanzador | Uno por juego; se distribuyen e instalan aparte |
| Plugin de Decky (`decky/`) | PC, opcional | Aviso en Big Picture / Game Mode con la URL y el código |

## Requisitos

**Host (PC):** Linux con `systemd` (sesión de usuario), Python 3.9 o superior y acceso a `/dev/uinput` (ver [Permisos del mando](#permisos-del-mando-devuinput)). Para los FPS, [MangoHud](https://github.com/flightlessmango/MangoHud). Funciona también en distribuciones inmutables (Fedora Atomic, Bazzite, SteamOS…): no hace falta compilar nada ni instalar paquetes del sistema.

**Android:** 8.0 o superior para la app; para el cliente web, cualquier navegador moderno. El mando del dispositivo (o uno Bluetooth/USB) se reenvía al PC.

## Compilación

### Host

No hay que compilar: es Python. `tools/install.sh` crea un entorno virtual en `.venv/` con `aiohttp` (la única dependencia).

### App de Android

Necesita JDK 17 o superior y el SDK de Android (plataforma 36, build-tools 35+). El proyecto usa el Gradle Wrapper, no hace falta instalar Gradle.

```
cd android
echo "sdk.dir=$HOME/Android/Sdk" > local.properties     # ruta de tu SDK
./gradlew assembleRelease
```

Resultado: `android/app/build/outputs/apk/release/app-release.apk`.

**Firma.** Sin más configuración, la APK de release se firma con la clave de depuración (se instala, pero una APK firmada con otra clave no podrá actualizarla). Para firmar con tu propia clave, que debes guardar fuera del repositorio:

```
cd android && mkdir -p keystore
keytool -genkeypair -keystore keystore/gamepad.jks -alias gamepad -keyalg RSA -keysize 3072 -validity 36500
cat > keystore/keystore.properties <<'EOF'
storeFile=keystore/gamepad.jks
storePassword=TU_CONTRASEÑA
keyAlias=gamepad
keyPassword=TU_CONTRASEÑA
EOF
```

`android/keystore/` está en `.gitignore`. Usa siempre la misma clave: Android solo instala una actualización encima si está firmada con la clave original.

Más detalles en [android/README.md](android/README.md).

### Plugins

Cada plugin se empaqueta aparte como `gamepad-plugin-<id>-<versión>.zip`:

```
sh tools/build-plugin.sh ffrs                    # crea gamepad-plugin-ffrs-1.0.0.zip y lo valida
sh tools/build-plugin.sh ffrs ~/Descargas --media   # …-media.zip, con tus retratos y fondos dentro
```

`--media` añade las imágenes de `~/.local/share/gamepad/portraits/<id>/` y `~/.local/share/gamepad/backgrounds/<id>/` (también vale ponerlas en `plugins/<id>/portraits/` y `plugins/<id>/backgrounds/`, que git ignora). Ese zip es para tu uso: el arte de los juegos tiene copyright y no se publica en el repositorio.

### Plugin de Decky (opcional)

Necesita Node.js:

```
sh tools/build-decky.sh                  # crea gamepad-decky-<versión>.zip
```

## Instalación en el host

Con tu usuario, **sin sudo**:

```
git clone <este repositorio> ~/gamepad          # o descomprime un zip en una carpeta fija
cd ~/gamepad && sh tools/install.sh
systemctl --user enable --now gamepad
gamepad status
```

`install.sh` crea `~/.local/bin/gamepad` (apunta a la carpeta del proyecto: no la muevas, o vuelve a ejecutarlo) y el servicio de usuario `gamepad`, y te dice si tu usuario ya puede crear el mando virtual. Se puede ejecutar las veces que haga falta.

`gamepad status` muestra si el servicio está activo, la URL para Android y el **código de acceso** (4 letras, fijo; `gamepad code --new` lo cambia y cierra las sesiones abiertas).

**Actualizar:** `git pull` (o descomprime el zip nuevo encima), `sh tools/install.sh` y `systemctl --user restart gamepad`.

### Steam

Para que el lanzador lea FPS y datos del juego, en las propiedades del juego → **Opciones de lanzamiento** (ruta absoluta; cambia `TU_USUARIO`):

```
/home/TU_USUARIO/.local/bin/gamepad run mangohud %command%
```

Sin esto, el mando y la telemetría del sistema funcionan igual; solo faltan FPS y datos del juego.

### Heroic (también Flatpak)

Heroic no tiene `%command%`: usa un *wrapper*. En la configuración del juego → **Otros** → **Usar wrapper**, añade uno con comando `/home/TU_USUARIO/.local/bin/gamepad` y argumentos `run`. En sistemas atómicos (Bazzite, Silverblue, Kinoite) usa la ruta real de tu carpeta personal, la que muestra `echo $HOME` (`/var/home/TU_USUARIO/...`): dentro del Flatpak `/home` puede no existir y Heroic no encontraría el wrapper (el juego no abre). Para los FPS, activa también MangoHud en Heroic (en Flatpak necesita la extensión `org.freedesktop.Platform.VulkanLayer.MangoHud`).

Dentro del Flatpak el lanzador usa el `python3` del sandbox (solo necesita la biblioteca estándar), se comunica con el servicio por `~/.cache/gamepad/hub.sock` y deja su registro en `~/.cache/gamepad/launcher.log`. Si en el sandbox no hubiera Python, el juego se lanza igual, sin datos. Requiere que Heroic tenga acceso a tu carpeta personal.

### Permisos del mando (`/dev/uinput`)

El paquete de Steam suele instalar reglas udev que dan acceso a `/dev/uinput` al usuario con sesión iniciada; `install.sh` lo comprueba. Si falta, una sola vez:

```
sudo groupadd -f uinput
sudo usermod -aG uinput $USER
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/60-gamepad-uinput.rules
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Cierra sesión y vuelve a entrar. Se usa un grupo propio porque el grupo `input` también permite leer teclado y ratón.

Mientras falte el permiso, el servicio **arranca igual sin mando virtual** (web, telemetría y datos del juego funcionan), avisa en el log y en Android, y reintenta crear el mando cada 10 s: en cuanto el permiso aparece, el mando funciona sin reiniciar nada. Con `gamepad serve --pad uinput` el mando es obligatorio (falla sin él).

### Firewall

Si el dispositivo Android no llega al PC ("Address Unreachable" o "Connection refused"), abre el puerto 8888 **solo para tu red local**. Con firewalld (Fedora y derivadas), ajustando la zona (`sudo firewall-cmd --get-active-zones`) y el rango de tu red:

```
sudo firewall-cmd --permanent --zone=FedoraWorkstation --add-rich-rule='rule family="ipv4" source address="192.168.1.0/24" port port="8888" protocol="tcp" accept'
sudo firewall-cmd --reload
```

Con ufw: `sudo ufw allow from 192.168.1.0/24 to any port 8888 proto tcp`.

Si firewalld responde `RUNNING_BUT_FAILED`, no pudo cargar sus reglas y está en modo de emergencia: mira el motivo con `journalctl -u firewalld -b | grep -i error`. Un caso conocido: con kernels sin el módulo `nf_conntrack_netbios_ns`, el servicio `samba-client` de la zona impide cargarla; se arregla con una copia de la zona sin ese servicio:

```
sudo cp /usr/lib/firewalld/zones/FedoraWorkstation.xml /etc/firewalld/zones/
sudo sed -i '/<service name="samba-client"\/>/d' /etc/firewalld/zones/FedoraWorkstation.xml
sudo systemctl restart firewalld
```

No desactives el firewall para salir del paso.

### Plugins de juegos

```
gamepad plugin install gamepad-plugin-ffrs-1.0.0.zip    # instala o actualiza (pide confirmación)
gamepad plugin list                                     # incluidos e instalados, con versión
gamepad plugin remove ffrs                              # desinstala
```

Se instalan en `~/.local/share/gamepad/plugins/<id>/` y se cargan cada vez que lanzas un juego; no hace falta reiniciar el servicio.

### Aviso en Big Picture / Game Mode (Decky Loader, opcional)

Steam no deja que programas externos muestren avisos en Big Picture; con [Decky Loader](https://decky.xyz) sí. **Decky Loader corre como root**; el plugin de GamePad no pide root y corre con tu usuario: solo lee `~/.local/state/gamepad/code` y pregunta al servicio en `127.0.0.1` si responde. Muestra "GamePad listo" con la URL y el código al arrancar (o "no responde" si se cae) y un panel en el menú de acceso rápido.

Instalar: activa el modo desarrollador en los ajustes de Decky e instala `gamepad-decky-<versión>.zip` desde el ZIP.

## Instalación en Android

### App (recomendada)

1. Copia `app-release.apk` (o `gamepad-android-<versión>.apk`) al dispositivo y ábrelo; Android pedirá permitir instalar apps de esa fuente.
2. Abre **GamePad**, escribe `IP-DEL-PC:8888` y el código de `gamepad status`. La sesión dura 24 h.

El mando llega por eventos de Android (no se consulta en cada fotograma) y la pantalla solo se redibuja al llegar datos: calienta y gasta mucho menos que el navegador.

### Navegador (sin instalar nada)

Abre `http://IP-DEL-PC:8888` y escribe el código. Pulsa un botón del mando para que el navegador lo detecte. Si el navegador no ofrece el mando en `http://`, usa la app.

Solo puede haber un cliente conectado a la vez.

## Uso

- **Guide:** botón grande arriba de los FPS; equivale al botón Guide del mando (abre el menú de Steam) y se puede mantener pulsado.
- **Ajustes** (app y web): disposición del panel del juego, **por plugin**:
  - *Fondo*: automático (la primera imagen), ninguno o una concreta, y cuánto se oscurece;
  - *Telemetría*: a la izquierda, a la derecha u oculta (queda solo el botón Guide);
  - *Orden*: el equipo o las estadísticas primero; *Columnas del equipo*: 1, 2 o 4.

  En la app, además, el **mando táctil**: *Nunca*, *Automático* (solo si no hay un mando físico conectado) o *Siempre*, con su opacidad. Se suma al mando físico (por ejemplo, un botón en pantalla mientras usas los físicos).
- **Debug:** muestra u oculta el diagnóstico del plugin.
- **Remapear** (web): si algún botón no corresponde ("mapeo no estándar"), pulsa *Remapear* y sigue los pasos; se guarda por mando en ese navegador. La app usa el mapeo estándar de Android.
- **Táctil** (web): mando en pantalla, por si no hay mando físico. En la app se configura en *Ajustes*.
- Si no hay juego con plugin, la telemetría ocupa toda la pantalla.

Si el juego no muestra datos, el registro del lanzador está en `$XDG_RUNTIME_DIR/gamepad/launcher.log` (normalmente `/run/user/1000/gamepad/launcher.log`; con Heroic Flatpak, `~/.cache/gamepad/launcher.log`). Para probar sin un juego: `gamepad run python3 tools/demo_game.py`.

### FPS y MangoHud

El lanzador añade a tu configuración de MangoHud (sin tocar tu archivo) las opciones de log, con una fila por frame. El log va a `~/.cache/gamepad/` (dentro de tu carpeta personal, que el contenedor de Steam comparte con los juegos de Proton). Para que no crezca, el servicio libera la parte ya leída cada 4 MB y el lanzador lo borra al cerrar el juego. Si usas configuración por juego (`wine-*.conf`), el lanzador toma como base la general (`MangoHud.conf`).

## Plugins

Un plugin lee los datos de un juego concreto. Lo ejecuta solo el lanzador, sobre los descendientes del juego que lanzó (Linux, con `kernel.yama.ptrace_scope=1`, solo deja leer la memoria de un proceso a su ancestro: por eso no hace falta root). Es código Python con acceso de lectura a la memoria del juego: instala solo los que hayas revisado.

Formato (API 2):

```
mi_juego/
  plugin.json   {"id": "mi_juego", "name": "Mi Juego", "version": "1.0.0", "api": 2, "entry": "plugin.py"}
  plugin.py     class Plugin(GamePlugin): ...   (importa SOLO de server.plugin_api)
  *.py          módulos propios del plugin, opcionales (from .busqueda import ...)
```

- **La búsqueda de valores es del plugin.** El hub solo da lectura de memoria (`read`, `u32`, `ptr`, `pointer`, `module_base`…) y `pe_info` para reconocer la build; no conoce juegos ni motores. Punteros, firmas AOB, estructuras y lectores de motor (como el de Unreal Engine de `plugins/ffrs/ue.py`) van dentro de cada plugin.
- `id`: a-z, 0-9 y `_`; igual que el nombre de la carpeta y que `Plugin.id`.
- `api`: versión de la API de plugins (`server/plugin_api.py`). Los plugins de otra API no se cargan (si tienes instalado uno de la API 1, como ffrs 1.0.0, se ignora y se usa el incluido; reinstálalo con la versión nueva).
- Si un id está a la vez en `plugins/` del proyecto y en los instalados, gana el instalado.
- Plantilla: `plugins/_template/`. Empaquetar: `sh tools/build-plugin.sh <id>`.
- Al instalar se valida el zip: una sola carpeta `<id>/`, sin rutas `..` ni enlaces simbólicos, tamaño acotado y API compatible.
- Si `read()` tarda más de 5 s, se avisa en Android y no se lanza otra lectura hasta que termine.

Cada campo declara dónde se muestra con `section`: `party` (tarjetas por miembro, `slot` 1-4), `stats` (números grandes), `header` (junto al nombre del juego) o `info` (diagnóstico, solo con *Debug*). `kind`: `number`, `bar` (con `max_key`), `text` o `image`. `tone` (color): `hp`, `mp`, `limit`, `gold`, `xp` o `neutral`.

Las imágenes las pone el usuario; el proyecto no incluye arte de ningún juego:

- **Retratos**: `~/.local/share/gamepad/portraits/<id>/` (cada plugin decide los nombres).
- **Fondos** del panel: `~/.local/share/gamepad/backgrounds/<id>/` (`png`, `jpg`, `jpeg` o `webp`, nombres con letras, números, `_` o `-`; hasta 15 MB). Se eligen en *Ajustes*; aparecen al volver a abrir el juego o los Ajustes.
- Un plugin también puede **traer sus imágenes** (`<id>/portraits/` y `<id>/backgrounds/` dentro del zip, ver `--media`). Si hay una imagen con el mismo nombre en tu carpeta personal, gana la tuya.

Plugins incluidos en el repositorio:

- [`plugins/ffrs`](plugins/ffrs/README.md): FINAL FANTASY RESONANCE (Steam).
- `plugins/demo_game.py`: para `tools/demo_game.py`.

No uses plugins en juegos online con anti-cheat.

## Seguridad

- Ningún componente necesita root; el servicio corre con `NoNewPrivileges`.
- El servicio que da la cara a la red no puede leer memoria de juegos; el lanzador, que sí puede, no abre puertos. Se comunican por un socket Unix privado (`$XDG_RUNTIME_DIR/gamepad/hub.sock`, 0600).
- **Solo red local de confianza**, sin cifrado. No abras el puerto en el router ni en túneles.
- Código de 4 letras con bloqueo de 60 s tras 5 fallos; cookie de 24 h `HttpOnly` y `SameSite=Strict`; el WebSocket rechaza otros orígenes; un solo cliente a la vez.
- Las imágenes se sirven solo con sesión, con nombres validados, sin SVG y sin salir de su carpeta.
- Para cerrar todas las sesiones: `gamepad code --new` y `systemctl --user restart gamepad`.

## Desarrollo

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest -q
```

`tests/fake_ue.py` monta en memoria una estructura de Unreal Engine 5 y ejecuta el plugin real (con su lector `plugins/ffrs/ue.py`) contra ella. La red de la app Android se prueba sin Android con `android/jvmtest/` (ver [android/README.md](android/README.md)).

Protocolo: WebSocket `/ws` (JSON). Cliente → servidor: `in` (estado del mando, al cambiar y como latido) y `ping`. Servidor → cliente: `hello`, `tel` (`cpu`, `gpu`, `mem`, `fps`, `ft`, `ftNew[]`, `mh`), `game` (metadatos y campos del plugin), `gv` (valores o `err`), `pong`, `err`. Si no llega `in` en 500 ms, se sueltan todos los controles. Lanzador → servicio: líneas JSON por el socket Unix, solo `game` y `gv`.

```
server/
  cli.py        gamepad serve | run | status | code | plugin
  main.py       servicio: HTTP, WebSocket, watchdog, telemetría, socket puente
  launcher.py   lanzador: juego hijo, MangoHud, plugins, puente
  auth.py       código de acceso y sesiones
  status.py     gamepad status/code y notificación al arrancar
  pad.py        mando uinput (ioctl directos, sin dependencias)
  telemetry.py  /proc, /sys y log de MangoHud
  memory.py     lectura de memoria y descendientes
  pe.py         cabecera PE: build del .exe (para que los plugins la comprueben)
  plugins.py    carga y ciclo de vida de plugins
  plugin_api.py API estable para plugins
  plugin_pkg.py gamepad plugin list/install/remove
  portraits.py  imágenes del usuario: búsqueda y validación de rutas
  paths.py      rutas por usuario
plugins/        demo_game.py, _template/, ffrs/
web/index.html  cliente web
android/        app nativa (Java, sin dependencias)
decky/          plugin de Decky Loader
tests/          pytest
tools/          install.sh, gamepad.service, build-plugin.sh, build-decky.sh, demo_game.py
```

## Créditos

Creado por [ZeroNoir51](https://github.com/ZeroNoir51), con [Claude](https://claude.ai) (Anthropic) como asistente de programación: diseño, código, pruebas y documentación se hicieron en colaboración, y los commits lo indican con `Co-Authored-By: Claude`.

Las rutas de memoria del plugin de FINAL FANTASY RESONANCE parten de la tabla de Cheat Engine `FFRS_Steam_24250053_Starter.CT` de shawnjohnjr/ff-RESONANCE-ct.
