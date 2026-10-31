# Trails in the Sky 2nd Chapter (2026)

Plugin de solo lectura para `sora_2nd.exe` (Steam, GOG o Heroic, vía Proton). No modifica el juego ni inyecta código.

Muestra:

- **Brave Gauge**: número en un engranaje (el juego la muestra en centenas: 500 = 5; tope 5, 6 o 7).
- **Mira** y **tiempo de juego**.
- Con *Debug*: qué firmas se encontraron y la cadena de punteros de la Brave Gauge con su valor en bruto.

## Cómo encuentra los datos

Todo vive en este plugin (el hub solo le deja leer memoria). `scan.py` busca en el código del `.exe` las firmas de la tabla de Cheat Engine `sora_2nd-v2.CT` (Tuuuup!):

- **Mira y tiempo de juego**: puntero al bloque de estado del juego. El offset del tiempo se lee de la instrucción que lo suma; Mira va justo antes. Si un parche mueve esos campos, el plugin los sigue.
- **Brave Gauge**: el código que la limita (script "max Brave Rush on hit") da la cadena `[[[exe+G1]+0x2C50]+0x260]+0x48` y el tope (500/600/700 según un indicador). Todos los offsets se leen de esas instrucciones.

No usa direcciones fijas: si la versión del juego no coincide, lo dice (*Estado*) en vez de mostrar datos falsos.

## Lo que se probó y se descartó

- **Personajes del grupo** (nivel, EXP, HP/EP/CP): se leían bien, pero el juego no guarda el grupo activo en un sitio fiable y a veces salían personajes equivocados. Se quitaron; el trabajo está en el historial de git (hasta la 0.7.7).
- **Bracer Points y rango**: la tabla solo da los BP de cada misión, y solo inyectando código con la pantalla de rango abierta; no hay un total que leer.

## Fondos

Imágenes tuyas (png, jpg o webp) en `~/.local/share/gamepad/backgrounds/trails2/`; se eligen en *Ajustes*.
