# Trails in the Sky 2nd Chapter (2026)

Plugin de solo lectura para `sora_2nd.exe` (Steam, GOG o Heroic, vía Proton). No modifica el juego ni inyecta código.

Muestra:

- **Grupo** (4 primeros miembros): nombre, nivel y EXP, HP, EP y CP.
- **Mira**, **sepith** (los 7 tipos y masa) y **tiempo de juego**.
- Con *Debug*: qué firmas se encontraron y dónde están los registros de personaje.

## Cómo encuentra los datos

Todo vive en este plugin (el hub solo le deja leer memoria):

- `scan.py` busca en el código del `.exe` las firmas de la tabla de Cheat Engine `sora_2nd-v2.CT` (Tuuuup!) y resuelve el puntero al bloque de estado del juego.
- El offset del tiempo de juego se **lee de la propia instrucción** que lo suma; Mira y sepith van justo antes. Si un parche mueve esos campos, el plugin los sigue.
- `roster.py` busca dentro del bloque los registros de personaje (ID, nivel, EXP, HP, EP, CP y estadísticas, con la estructura de la tabla) y elige el array de personajes conocidos con separación fija.

No usa direcciones fijas: si la versión del juego no coincide, lo dice (*Estado*) en vez de mostrar datos falsos.

## Pendiente de verificar en el juego

- Que los registros de personaje estén en ese bloque (la tabla solo los localiza inyectando código).
- Qué miembros forman el grupo activo: por ahora se muestran los 4 primeros del array.
- Los nombres de los IDs 0-7 (orden habitual de la saga). Los invitados (Kurt, Anelace, Josette, Schwarz, Vander, Kevin, Dorothy) vienen de la tabla.

Si algo no cuadra, activa *Debug* y comparte los campos *Diag.* y `launcher.log`.

Retratos y fondos: por ahora no (llegarán en una versión posterior).
