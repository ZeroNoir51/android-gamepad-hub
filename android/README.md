# GamePad para Android (APK nativa)

Cliente nativo y ligero de GamePad Hub. Usa el mismo protocolo que la página web (`web/index.html`), así que
no hay que cambiar nada en el PC. Sin librerías externas: la APK ocupa unos 32 KB.

## Por qué debería calentar menos que Chrome

- **Sin navegador**: ni WebView ni el proceso de GPU de Chrome.
- **El mando llega por eventos de Android** (`dispatchKeyEvent` / `dispatchGenericMotionEvent`). La web
  consulta la Gamepad API en cada fotograma (60-120 veces por segundo); aquí solo se trabaja cuando pulsas
  algo, más un latido cada 200 ms que exige el servidor (suelta los controles a los 500 ms sin mensajes).
- **La pantalla solo se redibuja al llegar datos** (telemetría ~4 Hz, juego ~2 Hz), y solo las vistas que
  cambian.

## Instalar

1. Copia `gamepad-android-<versión>.apk` al handheld y ábrelo (Android pedirá permitir instalar apps de
   esa fuente).
2. Abre **GamePad**, escribe `IP-DEL-PC:8888` y el código de `gamepad status`. La sesión dura 24 h.

Las versiones nuevas se instalan encima solo si están firmadas con la misma clave (ver "Firma").

## Qué hay en esta versión (0.3)

- Conexión con código, reconexión automática y vuelta al login si la sesión caduca.
- Mando: botones, cruceta (teclas o hat), sticks (Z/RZ o RX/RY según el mando), gatillos (analógicos o
  L2/R2). Usa el mapeo estándar de Android, así que normalmente no hace falta remapear.
- Botón **Guide** grande con el icono de Steam (también el botón Guide/Home del mando si Android lo deja pasar).
- **Mando táctil** semitransparente sobre el panel (sticks, cruceta, ABXY, LB/LT/RB/RT, Back/Guide/Start,
  L3/R3), multitáctil. En *Ajustes*: *Nunca*, *Automático* (solo si no hay mando físico conectado) o
  *Siempre*, y su opacidad. Se suma al mando físico. Los toques fuera de sus controles llegan a la interfaz.
- FPS, frametimes, CPU/GPU/RAM, latencia y jitter.
- Panel del plugin: tarjetas con retrato, nivel, HP, MP y Limit; Gil; **Debug**.
- **Ajustes** del panel por plugin (como en la web): fondo (imágenes del PC), oscurecido, telemetría a la
  izquierda/derecha/oculta, orden y columnas.
- **Servidor**: vuelve a la pantalla de conexión.
- Aviso si el PC no pudo crear el mando virtual (sin permiso para `/dev/uinput`), y otro cuando ya está listo.

## Compilar

Necesita JDK 17+ y el SDK de Android (plataforma 36). Con `sdk.dir` en `local.properties`:

```
./gradlew assembleRelease     # app/build/outputs/apk/release/app-release.apk
./gradlew lintRelease
```

### Firma

`app/build.gradle` lee `keystore/keystore.properties` (`storeFile`, `storePassword`, `keyAlias`,
`keyPassword`). Si no existe, la release se firma con la clave de depuración. `keystore/` está en
`.gitignore`: guarda tu clave fuera del repositorio y usa siempre la misma, o Android no instalará las
actualizaciones encima. Cómo crearla: ver el README principal.

### Pruebas de la app (Robolectric)

`app/src/test/` ejecuta la actividad real en la JVM: arranque, panel del juego, disposición, ajustes y el
mando táctil mezclado con el físico.

```
./gradlew testReleaseUnitTest
```

Robolectric descarga una imagen de Android (`android-all-instrumented`, ~200 MB) de Maven Central la primera
vez. Sin esa red: descárgala a una carpeta y pásala con `-Probolectric.dependency.dir=<carpeta>`. Para
guardar capturas de la interfaz: `-Pgamepad.screenshots=<carpeta>`.

### Pruebas sin Android

La red y el estado del mando (`Api`, `WsClient`, `PadState`) no dependen de Android y se prueban con el
JDK (`jvmtest/`), con el servicio en marcha (`gamepad serve --pad null --token TEST --port 8099`):

```
javac -encoding UTF-8 -d /tmp/jt app/src/main/java/dev/gamepad/client/{Api,WsClient,PadState}.java jvmtest/dev/gamepad/client/*.java
java -cp /tmp/jt dev.gamepad.client.UnitTest
java -cp /tmp/jt dev.gamepad.client.NetTest 127.0.0.1 8099 TEST
```
