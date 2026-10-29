# GamePad Hub 0.2.4

Android (navegador hoy, APK después) → Wi-Fi local → PC Linux: mando virtual, telemetría (FPS, frametimes, CPU/GPU, RAM, latencia) y datos del juego leídos de memoria. **Nada se ejecuta como root.**

## Cómo está dividido

| Proceso | Qué hace | Qué no puede hacer |
|---|---|---|
| `gamepad serve` (servicio permanente) | mando virtual, telemetría, web y WebSocket en el puerto 8888 | leer la memoria de ningún juego |
| `gamepad run %command%` (lo lanza Steam) | lanza el juego como hijo, activa los logs de MangoHud y ejecuta el plugin | abrir puertos de red |

Linux (con `kernel.yama.ptrace_scope=1`, el valor de Ubuntu) solo deja leer la memoria de un proceso a su ancestro. Como el lanzador es el padre del juego, puede leerlo sin root. El servicio que da la cara a la red no tiene ese poder. Los dos se comunican por un socket Unix privado (`$XDG_RUNTIME_DIR/gamepad/hub.sock`, permisos 0600).

## Instalación (con tu usuario, sin sudo)

El proyecto vive siempre en la misma carpeta, `~/proyectos/gamepad`, y los zips se llaman `gamepad-<versión>.zip` y se descomprimen en ella. Así la ruta del comando no cambia entre versiones.

```
cd ~/proyectos && unzip -o gamepad-0.2.4.zip
cd gamepad && sh tools/install.sh
systemctl --user enable --now gamepad
```

Para actualizar: `unzip -o` del zip nuevo en `~/proyectos`, `sh tools/install.sh` y `systemctl --user restart gamepad`.

Solo necesita Python 3 y `aiohttp` (sin compilar nada: el mando virtual habla con `/dev/uinput` directamente). Funciona igual en sistemas inmutables como Bazzite.

Crea `~/.local/bin/gamepad` y el servicio de usuario `gamepad`, y te dice si tu usuario ya puede crear el mando virtual.

**Si vienes de `ps5gamepad` (hasta la v0.4.5):** `install.sh` detiene y quita el servicio antiguo, mueve los retratos a `~/.local/share/gamepad/portraits/` y deja `~/.local/bin/ps5gamepad` como alias del comando nuevo, para que el juego siga arrancando hasta que cambies la opción de Steam a `gamepad run mangohud %command%`. La sesión de Android se pide de nuevo una vez.

Si vienes de la v0.3 (que corría con sudo), detén ese servidor y quita de `~/.config/MangoHud/MangoHud.conf` las líneas `output_folder`, `autostart_log`, `log_interval` y `log_duration`: el lanzador ahora las pone por ti.

### Permisos del mando (`/dev/uinput`)

El paquete de Steam suele instalar reglas udev que dan acceso a `/dev/uinput` al usuario con sesión iniciada. Compruébalo con `ls -l /dev/uinput` y `getfacl /dev/uinput`, o mira lo que dice `install.sh`. Si falta, una sola vez:

```
sudo groupadd -f uinput
sudo usermod -aG uinput $USER
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/60-gamepad-uinput.rules
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Cierra sesión y vuelve a entrar. Se usa un grupo propio porque el grupo `input` también permite leer teclado y ratón.

### Firewall (Fedora, Bazzite y otros con firewalld)

Ubuntu no trae firewall activo; Fedora y Bazzite sí. Si Android dice "Address Unreachable", abre el puerto solo para tu red local (ajusta la zona, que ves con `sudo firewall-cmd --get-active-zones`, y el rango de tu red):

```
sudo firewall-cmd --permanent --zone=FedoraWorkstation --add-rich-rule='rule family="ipv4" source address="192.168.1.0/24" port port="8888" protocol="tcp" accept'
sudo firewall-cmd --reload
```

Si responde `RUNNING_BUT_FAILED`, firewalld no pudo cargar sus reglas y está en modo de emergencia. Mira el motivo con `journalctl -u firewalld -b | grep -i error`. En la PS5 con Bazzite (kernel 7.3.0) faltaba el módulo `nf_conntrack_netbios_ns`, que pide el servicio `samba-client` de la zona; se arregla con una copia de la zona sin ese servicio:

```
sudo cp /usr/lib/firewalld/zones/FedoraWorkstation.xml /etc/firewalld/zones/
sudo sed -i '/<service name="samba-client"\/>/d' /etc/firewalld/zones/FedoraWorkstation.xml
sudo systemctl restart firewalld
```

No desactives firewalld para salir del paso.

## Uso

1. Servicio: `systemctl --user start gamepad` (y `enable` para que arranque al iniciar sesión).
2. Código de acceso y URL: `gamepad status`. El código es fijo (se guarda en `~/.local/state/gamepad/code`, 0600); `gamepad code --new` lo cambia y cierra las sesiones abiertas (luego `systemctl --user restart gamepad`). Al arrancar, el servicio manda una notificación de escritorio con la URL y el código.
3. Android: abre `http://IP-DEL-PC:8888` y escribe el código. La sesión dura 24 h.
4. Steam, propiedades del juego, opciones de lanzamiento (ruta absoluta, cambia TU_USUARIO):
   ```
   /home/TU_USUARIO/.local/bin/gamepad run mangohud %command%
   ```

Si el juego no muestra datos, el registro del lanzador está en `$XDG_RUNTIME_DIR/gamepad/launcher.log` (normalmente `/run/user/1000/gamepad/launcher.log`).

Para probar sin juego real: `gamepad run python3 tools/demo_game.py`.

### Aviso en Big Picture / Game Mode (Decky Loader, opcional)

Steam no deja que programas externos muestren avisos en Big Picture; con [Decky Loader](https://decky.xyz) sí. **Decky Loader corre como root** (en Bazzite: `ujust setup-decky`); el plugin de GamePad no pide root y corre con tu usuario: solo lee `~/.local/state/gamepad/code` y pregunta al servicio en `127.0.0.1` si responde.

- Aviso "GamePad listo" con la URL y el código cuando el servicio responde (también al iniciar Steam) y "GamePad no responde" si se cae.
- Panel en el menú de acceso rápido (botón `…`, icono de mando) con estado, URL y código.

Instalar: copia `gamepad-decky-<versión>.zip` a la PS5, activa el modo desarrollador en los ajustes de Decky e instala el plugin desde el ZIP. Para compilarlo tú: `sh tools/build-decky.sh` (necesita Node.js).

### En el cliente (Android)

- **Remapear:** si algún botón del mando físico no corresponde (el navegador lo marca como "mapeo no estándar"), pulsa *Remapear* y sigue los pasos: pulsa cada botón, gatillo o dirección que se pide. Lo que no exista se omite. El mapeo se guarda en ese navegador, por mando; *Volver al mapeo por defecto* lo borra. Mientras remapeas, el PC no recibe ninguna pulsación.
- **Debug:** muestra u oculta el panel de diagnóstico del plugin (estado, origen de HP/MP, mapa, ejecutable, diagnóstico de batalla y de curvas de nivel). Se recuerda en ese navegador.
- **Táctil:** mando en pantalla, por si no hay mando físico.
- **Guide:** botón grande (tamaño pulgar) arriba de los FPS. Equivale al botón Guide del mando (abre el menú de Steam); se puede mantener pulsado.

## FPS, frametimes y tamaño del log

El lanzador añade a tu configuración de MangoHud (sin tocar tu archivo) las opciones de log, con una fila por frame. El log y la configuración generada van a `~/.cache/gamepad/` (privado, 0700). Tiene que estar dentro de tu carpeta personal: los juegos de Proton corren en el contenedor de Steam, que comparte tu carpeta personal pero no `/run/user/...`. Para que no crezca:

- el servicio libera cada 4 MB la parte del archivo ya leída (el archivo conserva su tamaño aparente, pero deja de ocupar memoria);
- el lanzador borra el log al cerrar el juego, y también los de más de un día.

Si tu configuración de MangoHud es un archivo por juego (`wine-*.conf`), el lanzador usa el general (`MangoHud.conf`) como base. En ese caso, copia tus opciones al general.

## Plugins

Viven en `plugins/` y los ejecuta solo el lanzador, sobre los descendientes del juego que lanzó. Son código Python con acceso de lectura a la memoria del juego: instala solo los que hayas revisado.

Cada campo declara dónde se muestra en Android con `section`:

- `party`: tarjetas por miembro (`slot` 1-4) con nombre, HP y MP;
- `stats`: números grandes (Gil, EXP);
- `info`: texto pequeño de diagnóstico (solo se ve con *Debug* activado).

Si no hay juego con plugin, el panel derecho desaparece y la telemetría ocupa toda la pantalla.

### Final Fantasy Resonance (`plugins/ffrs.py`)

Solo para la build 24250053 de Steam: comprueba la cabecera PE del ejecutable (timestamp `0x6A586B2F`, tamaño `503013376`) y, si no coincide, no lee nada. Las rutas de memoria vienen de la tabla `FFRS_Steam_24250053_Starter.CT` (repositorio `shawnjohnjr/ff-RESONANCE-ct`); cada una está documentada al principio del plugin.

| Dato | Dónde se muestra | Origen |
|---|---|---|
| Gil | estadísticas | partida activa, ruta de la tabla |
| Nombre de los 4 miembros | tarjetas | equipo de la partida; en batalla, orden de la batalla |
| Nivel y EXP para el siguiente | línea bajo el nombre | EXP de la partida + curvas de nivel del juego (cálculo propio: compáralo con el menú) |
| HP y MP | barras de cada tarjeta | en batalla: reflexión de Unreal por nombre de propiedad; fuera de batalla: experimental (ver abajo) |
| Retrato | círculo junto al nombre | imágenes tuyas (ver "Retratos"); si no hay, la inicial |

**HP y MP.** La tabla no los lee, así que el plugin los busca por nombre en la descripción interna de la clase `CPP_BtlUnitParameter` (por ejemplo `HitPoint` y `MaxHitPoint`, el estilo de nombres que usa el juego). Antes de fiarse, comprueba que la reflexión encuentre dos offsets ya confirmados por la tabla (`0xD0`, ID del personaje, y `0x118`, Limit). Si la comprobación falla o un nombre es ambiguo, no muestra ese valor y lo indica en "Origen HP/MP". En la primera batalla escribe la lista completa de propiedades en `launcher.log`.

**HP y MP fuera de batalla (experimental).** La tabla los obtiene llamando a una función del juego, cosa que un lector no puede hacer. El plugin busca los objetos `CPP_UnitParameter` (la clase base de la de batalla) y usa uno solo si es el único con el ID de ese personaje; si hay varios o desaparece, no muestra nada hasta reescanear (cada 15 s como mucho). Aquí la reflexión solo se puede validar con `0xD0`. "Origen HP/MP" termina en "(experimental)" cuando el dato viene de esta vía: compáralo con el menú del juego.

### Retratos

No se incluye arte del juego: pones tus propias imágenes en

```
~/.local/share/gamepad/portraits/ffrs/
```

Está fuera de la carpeta del proyecto, así no se pierden al descomprimir otra versión. Formatos: `png`, `jpg`, `jpeg`, `webp` (SVG no). Se aceptan dos nombres por personaje: el ID o el nombre en minúsculas.

| ID | Personaje | Archivo |
|---|---|---|
| 1001 | Rain | `1001.png` o `rain.png` |
| 1002 | Lasswell | `1002.png` o `lasswell.png` |
| 1003 | Fina | `1003.png` o `fina.png` |
| 1004 | Lid | `1004.png` o `lid.png` |
| 1005 | Nichol | `1005.png` o `nichol.png` |
| 1006 | Archwitch Fina | `1006.png`, `archwitch_fina.png` o `dark_fina.png` |
| 1007 | Jake | `1007.png` o `jake.png` |
| 1008 | Sakura | `1008.png` o `sakura.png` |

Copia los archivos (no enlaces simbólicos que apunten fuera de la carpeta: se rechazan). Basta con una imagen cuadrada con la cara centrada; se recorta en círculo. Las imágenes nuevas aparecen en unos 10 s, sin reiniciar nada.

El escaneo de objetos para encontrar la partida tarda unos segundos; se hace una vez al cargar y, mientras estés en el título, se reintenta cada 10 s.

No uses plugins en juegos online con anti-cheat.

## Tests

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

`tests/fake_ue.py` monta en memoria la estructura de UE5 que describe la tabla CT y ejecuta el plugin real contra ella.

## Seguridad

- Los retratos se sirven solo con sesión, con nombres validados, sin SVG y sin salir de su carpeta.

- Ningún componente necesita root; el servicio corre con `NoNewPrivileges`.
- El servicio web no puede leer memoria de juegos; el lector no abre puertos.
- Solo red local de confianza, sin cifrado. No abras el puerto en el router ni en túneles.
- Código de 4 letras con bloqueo de 60 s tras 5 fallos; cookie de 24 h `HttpOnly` y `SameSite=Strict`; el WebSocket rechaza otros orígenes; un solo cliente a la vez.
- Para cerrar todas las sesiones: borra `~/.local/state/gamepad/sessions.json` y reinicia el servicio.

## Protocolo

WebSocket `/ws` (JSON). Cliente → servidor: `in` (estado del mando, al cambiar y cada 100 ms) y `ping`. Servidor → cliente: `hello`, `tel` (`cpu`, `gpu`, `mem`, `fps`, `ft`, `ftNew[]`, `mh`), `game` (metadatos y campos del plugin), `gv` (valores o `err`), `pong`, `err`. Si no llega `in` en 500 ms, se sueltan todos los controles.

Lanzador → servicio: líneas JSON por el socket Unix, solo de tipo `game` y `gv`.

## Estructura

```
server/
  cli.py        gamepad serve | run
  main.py       servicio: HTTP, WebSocket, watchdog, telemetría, socket puente
  launcher.py   lanzador: juego hijo, MangoHud, plugins, puente
  auth.py       código de acceso y sesiones
  pad.py        mando uinput (ioctl directos, sin evdev)
  telemetry.py  /proc, /sys y log de MangoHud
  memory.py     lectura de memoria y descendientes
  ue.py         lector de Unreal Engine 5 (nombres, objetos, GWorld)
  plugins.py    carga y ciclo de vida de plugins
  paths.py      rutas por usuario
  portraits.py  retratos del usuario: búsqueda y validación de rutas
plugins/        ffrs.py, demo_game.py, _template.py
tests/          arnés de memoria UE5 sintética y tests (pytest)
tools/          install.sh, gamepad.service, demo_game.py
web/index.html  cliente Android
```
