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
2. Abre **GamePad**, escribe `IP:puerto` del PC (por defecto `192.168.1.50:8888`) y el código de
   `gamepad status`. La sesión dura 24 h.

Las versiones nuevas se instalan encima: todas se firman con la clave de `keystore/` (guárdala).

## Qué hay en esta versión (0.1)

- Conexión con código, reconexión automática y vuelta al login si la sesión caduca.
- Mando: botones, cruceta (teclas o hat), sticks (Z/RZ o RX/RY según el mando), gatillos (analógicos o
  L2/R2). Usa el mapeo estándar de Android, así que normalmente no hace falta remapear.
- Botón **Guide** grande (también el botón Guide/Home del mando si Android lo deja pasar).
- FPS, frametimes, CPU/GPU/RAM, latencia y jitter.
- Panel del plugin: tarjetas del equipo con retrato, nivel, HP, MP y Limit; Gil; datos de **Debug**.
- **Servidor**: vuelve a la pantalla de conexión.

Pendiente: remapeo dentro de la APK y mando táctil.

## Compilar

Necesita JDK 17+ y el SDK de Android (plataforma 36). Con `sdk.dir` en `local.properties`:

```
./gradlew assembleRelease     # app/build/outputs/apk/release/app-release.apk
./gradlew lintRelease
```

Pruebas sin Android de la red y del estado del mando (`jvmtest/`), con el servicio en marcha
(`gamepad serve --pad null --token TEST --port 8099`):

```
javac -encoding UTF-8 -d /tmp/jt app/src/main/java/dev/gamepad/client/{Api,WsClient,PadState}.java jvmtest/dev/gamepad/client/*.java
java -cp /tmp/jt dev.gamepad.client.UnitTest
java -cp /tmp/jt dev.gamepad.client.NetTest 127.0.0.1 8099 TEST
```
