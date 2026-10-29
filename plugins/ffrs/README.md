# Plugin GamePad: FINAL FANTASY RESONANCE

Lee (solo lectura) el equipo, el nivel y la EXP, el HP, el MP y el Limit de cada miembro, y el Gil.
Solo funciona con la build **24250053** de Steam: comprueba la cabecera PE del ejecutable (timestamp
`0x6A586B2F`, tamaño `503013376`) y, si no coincide, no lee nada para no mostrar datos falsos.

## Instalar

```
gamepad plugin install gamepad-plugin-ffrs-<versión>.zip
```

Se instala en `~/.local/share/gamepad/plugins/ffrs/` y se usa en el próximo arranque del juego con la opción
de Steam `gamepad run mangohud %command%`; no hace falta reiniciar el servicio. Para empaquetarlo desde el
repositorio: `sh tools/build-plugin.sh ffrs`.

## Qué muestra

| Dato | Dónde | Origen |
|---|---|---|
| Nombre de los miembros | tarjetas | equipo de la partida; en batalla, orden de la batalla |
| Nivel y EXP para el siguiente | bajo el nombre | EXP de la partida + curvas de nivel del juego |
| HP y MP | barras | actual: parámetro de la unidad (`+0x10C`/`+0x110`); máximo: ViewModel de la interfaz |
| Limit | barra | parámetro de la unidad (`+0x118`, tope `+0x2A0`) |
| Gil | estadísticas | partida activa |
| Retrato | junto al nombre | imágenes tuyas (abajo); si no hay, la inicial |
| Batalla | cabecera | "en batalla (n)" / "fuera de batalla" |

Las rutas de memoria vienen de la tabla `FFRS_Steam_24250053_Starter.CT` (repositorio
`shawnjohnjr/ff-RESONANCE-ct`) y de lo verificado en el juego; cada una está documentada al principio de
`plugin.py`.

**HP y MP.** El juego no los publica con nombre en la reflexión. El actual está en el parámetro de cada
unidad (`+0x10C` HP, que la tabla usa como "puede actuar si > 0"; `+0x110` MP), en batalla
(`CPP_BtlUnitParameter`) y fuera (`CPP_UnitParameter`). El máximo sale del ViewModel de la interfaz
(`CPP_VM_UnitParam` → `HitPointVM`/`MagicPointVM` → `MaxPoint`), localizado por nombre.

**Fuera de batalla.** El plugin busca los objetos `CPP_UnitParameter` y `CPP_VM_UnitParam` y usa uno solo si es
el único con el ID de ese personaje; si hay varios o desaparece, no muestra nada hasta reescanear (cada 15 s
como mucho). El escaneo inicial para encontrar la partida tarda unos segundos.

Con **Debug** activado se ven "Origen HP/MP", "Diag. HP/MP", "Diag. batalla" y "Diag. curvas", que dicen de dónde
sale cada dato o en qué paso falla.

## Retratos

No se incluye arte del juego. Pon tus propias imágenes (`png`, `jpg`, `jpeg` o `webp`; SVG no) en
`~/.local/share/gamepad/portraits/ffrs/`, con el ID o el nombre en minúsculas:

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

También puedes empaquetarlas **dentro del plugin** para instalarlo con todo en otro equipo (zip para tu uso,
no lo publiques: es arte con copyright):

```
sh tools/build-plugin.sh ffrs ~/Descargas --media    # incluye ~/.local/share/gamepad/portraits/ffrs/ y backgrounds/ffrs/
gamepad plugin install ~/Descargas/gamepad-plugin-ffrs-<versión>-media.zip
```

Fondos del panel: en `~/.local/share/gamepad/backgrounds/ffrs/` (o dentro del zip con `--media`); se eligen en
*Ajustes*. Si una imagen está en tu carpeta y en el plugin, gana la de tu carpeta.

Copia los archivos (no enlaces simbólicos que apunten fuera de la carpeta: se rechazan). Basta con una imagen
cuadrada con la cara centrada; se recorta en círculo. Las imágenes nuevas aparecen en unos 10 s.

No lo uses en juegos online con anti-cheat.
