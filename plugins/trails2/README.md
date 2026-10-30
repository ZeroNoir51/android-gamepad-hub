# Trails in the Sky 2nd Chapter (2026)

Plugin de solo lectura para `sora_2nd.exe` (Steam, GOG o Heroic, vía Proton). No modifica el juego ni inyecta código.

Muestra:

- **Grupo activo** (los 4 del juego, en su orden): retrato, nombre, nivel y EXP para el siguiente, HP, EP y CP, con tarjetas al estilo del juego (barras inclinadas y el CP como anillo del retrato).
- **Mira** y **tiempo de juego**.
- Con *Debug*: qué firmas se encontraron, dónde están los registros de personaje y la fórmula de EXP. `launcher.log` lista todos los personajes encontrados y los candidatos a la lista del grupo.

## Cómo encuentra los datos

Todo vive en este plugin (el hub solo le deja leer memoria):

- `scan.py` busca en el código del `.exe` las firmas de la tabla de Cheat Engine `sora_2nd-v2.CT` (Tuuuup!) y resuelve el puntero al bloque de estado del juego.
- El offset del tiempo de juego se **lee de la propia instrucción** que lo suma; Mira va justo antes. Si un parche mueve esos campos, el plugin los sigue.
- `roster.py` busca dentro del bloque los registros de personaje (ID, nivel, EXP, HP, EP, CP y estadísticas, con la estructura de la tabla) y elige el array de personajes conocidos con separación fija.

No usa direcciones fijas: si la versión del juego no coincide, lo dice (*Estado*) en vez de mostrar datos falsos.

## Pendiente de verificar en el juego

- Verificado (1.03.1): Mira, tiempo de juego, nivel, EXP, "Sig." (también Zin, × 0,98) y el grupo de dos partidas distintas.
- **Grupo activo**: lista de miembros en el bloque (+0x5145C en la 1.03.1, u16 en orden; los 4 primeros van en el grupo). Los registros de esos personajes se toman de la serie o, si no están en ella (en la 1.03.1, Estelle, Scherazard y Kloe están en otra zona), se buscan por ID en el bloque con la EXP validada por la fórmula. Si no cuadra, se muestran los primeros registros y *Diag. grupo* busca la lista.
- **Siguiente nivel** (verificado: Olivier 1.716 como en el menú): fórmula del propio juego (`expcurve.py`): EXP total del nivel N = 100·N·(N+3) × multiplicador; las constantes se leen de su código. Los personajes con multiplicador o tope propios (invitados como Zin, × 0,98) los leen de los datos del juego como hace él (`charparams.py`); si no cuadra, solo se muestra el nivel y *Diag. EXP* lo dice.
- **Cambios de grupo sin recargar** (verificado: Kloe -> Zin en el menú se ve en el panel): la lista de +0x5145C se actualiza al cargar; cada 2 s se compara la memoria y, si un personaje pasa a ser otro formando una lista válida, se lee el grupo de ahí.
- **Sin grupo fiable no hay tarjetas**: si la lista no cuadra, no se muestran personajes (antes salían los primeros registros, p. ej. Dorothy) y *Estado* dice "Grupo no identificado".
- Los nombres de los IDs 0-7 (orden habitual de la saga). Los invitados (Kurt, Anelace, Josette, Schwarz, Vander, Kevin, Dorothy) vienen de la tabla.

Si algo no cuadra, activa *Debug* y comparte los campos *Diag.* y `launcher.log`.

## Retratos y fondos

Imágenes tuyas (png, jpg o webp), en el PC:

- **Retratos**: `~/.local/share/gamepad/portraits/trails2/<nombre>.png`, con el nombre en minúsculas: `estelle`, `joshua`, `scherazard`, `olivier`, `kloe`, `agate`, `tita`, `zin`, `kurt`, `anelace`, `josette`, `schwarz`, `vander`, `kevin`, `dorothy` (o el ID: `0.png`, `2.png`...). Mejor cuadradas y con la cara centrada: se recortan en círculo.
- **Fondos**: `~/.local/share/gamepad/backgrounds/trails2/` (cualquier nombre con letras, números, `_` o `-`). Se eligen en *Ajustes*.

Aparecen sin reiniciar nada (los retratos en unos segundos; los fondos al volver a abrir *Ajustes* o el juego).
