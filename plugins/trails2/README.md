# Trails in the Sky 2nd Chapter (2026)

Plugin de solo lectura para `sora_2nd.exe` (Steam, GOG o Heroic, vía Proton). No modifica el juego ni inyecta código.

Muestra:

- **Grupo** (4 primeros registros, por ahora): retrato, nombre, nivel y EXP para el siguiente, HP, EP y CP, con tarjetas al estilo del juego (barras inclinadas y el CP como anillo del retrato).
- **Mira** y **tiempo de juego**.
- Con *Debug*: qué firmas se encontraron, dónde están los registros de personaje y la fórmula de EXP. `launcher.log` lista todos los personajes encontrados y los candidatos a la lista del grupo.

## Cómo encuentra los datos

Todo vive en este plugin (el hub solo le deja leer memoria):

- `scan.py` busca en el código del `.exe` las firmas de la tabla de Cheat Engine `sora_2nd-v2.CT` (Tuuuup!) y resuelve el puntero al bloque de estado del juego.
- El offset del tiempo de juego se **lee de la propia instrucción** que lo suma; Mira va justo antes. Si un parche mueve esos campos, el plugin los sigue.
- `roster.py` busca dentro del bloque los registros de personaje (ID, nivel, EXP, HP, EP, CP y estadísticas, con la estructura de la tabla) y elige el array de personajes conocidos con separación fija.

No usa direcciones fijas: si la versión del juego no coincide, lo dice (*Estado*) en vez de mostrar datos falsos.

## Pendiente de verificar en el juego

- Verificado (1.03.1): Mira, tiempo de juego, nivel y EXP.
- Qué miembros forman el grupo activo: por ahora se muestran los 4 primeros del array. *Diag. grupo* lista los candidatos a esa lista en memoria.
- **Siguiente nivel**: con la fórmula del propio juego (`expcurve.py`): EXP total del nivel N = 100·N·(N+3) × multiplicador; las constantes se leen de su código. Si la EXP de un personaje no cuadra (multiplicador propio), solo se muestra el nivel y *Diag. EXP* lo dice. Por confirmar contra el valor del menú.
- Los nombres de los IDs 0-7 (orden habitual de la saga). Los invitados (Kurt, Anelace, Josette, Schwarz, Vander, Kevin, Dorothy) vienen de la tabla.

Si algo no cuadra, activa *Debug* y comparte los campos *Diag.* y `launcher.log`.

## Retratos y fondos

Imágenes tuyas (png, jpg o webp), en el PC:

- **Retratos**: `~/.local/share/gamepad/portraits/trails2/<nombre>.png`, con el nombre en minúsculas: `estelle`, `joshua`, `scherazard`, `olivier`, `kloe`, `agate`, `tita`, `zin`, `kurt`, `anelace`, `josette`, `schwarz`, `vander`, `kevin`, `dorothy` (o el ID: `0.png`, `2.png`...). Mejor cuadradas y con la cara centrada: se recortan en círculo.
- **Fondos**: `~/.local/share/gamepad/backgrounds/trails2/` (cualquier nombre con letras, números, `_` o `-`). Se eligen en *Ajustes*.

Aparecen sin reiniciar nada (los retratos en unos segundos; los fondos al volver a abrir *Ajustes* o el juego).
