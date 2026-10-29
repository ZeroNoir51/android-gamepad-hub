# Plugin GamePad: FINAL FANTASY RESONANCE

Lee (solo lectura) el equipo, el nivel y la EXP, el HP, el MP y el Limit de cada miembro, y el Gil.
Solo funciona con la build **24250053** de Steam: si el ejecutable es otro, no lee nada.

## Instalar

```
gamepad plugin install gamepad-plugin-ffrs-<versión>.zip
```

Se instala en `~/.local/share/gamepad/plugins/ffrs/`. Actualizar GamePad no lo toca. Se usa en el próximo
arranque del juego con la opción de Steam `gamepad run mangohud %command%`; no hace falta reiniciar el servicio.

## Retratos

Pon tus propias imágenes (png, jpg, jpeg o webp) en `~/.local/share/gamepad/portraits/ffrs/`, con el ID
o el nombre en minúsculas: `1001.png` o `rain.png`, `lasswell`, `fina`, `lid`, `nichol`,
`archwitch_fina` (o `dark_fina`), `jake`, `sakura`.

## De dónde sale cada dato

Ver el docstring de `plugin.py`: rutas de la tabla `FFRS_Steam_24250053_Starter.CT` y lo verificado en el
juego real (HP/MP actual en el parámetro de la unidad, máximo en el ViewModel de la interfaz).

No lo uses en juegos online con anti-cheat.
