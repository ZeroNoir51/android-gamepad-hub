#!/bin/sh
# Instala gamepad para el usuario actual. NO ejecutar con sudo.
# Se puede repetir: al actualizar, descomprime encima de la misma carpeta y vuelve a ejecutarlo.
set -eu
if [ "$(id -u)" = 0 ]; then echo "Ejecuta este script con tu usuario, sin sudo." >&2; exit 1; fi
DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$HOME/.local/bin"
UNITS="$HOME/.config/systemd/user"

[ -x "$DIR/.venv/bin/python" ] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"

mkdir -p "$BIN" "$UNITS"
cat > "$BIN/gamepad" <<EOS
#!/bin/sh
# Dentro de un Flatpak (Heroic) el python del venv puede no existir: \`run\` solo usa la
# biblioteca estándar, así que vale el python3 del sandbox. Sin ninguno, se lanza el juego solo.
PY="$DIR/.venv/bin/python"
if ! "\$PY" -c '' 2>/dev/null; then
  PY="\$(command -v python3 || true)"
  if [ -z "\$PY" ] && [ "\${1:-}" = run ]; then
    shift; [ "\${1:-}" = -- ] && shift
    exec "\$@"
  fi
fi
PYTHONPATH="$DIR" exec "\$PY" -m server "\$@"
EOS
chmod 755 "$BIN/gamepad"
cp "$DIR/tools/gamepad.service" "$UNITS/gamepad.service"

# --- migración desde el nombre anterior (ps5gamepad, hasta la v0.4.5) ---
if [ -f "$UNITS/ps5gamepad.service" ]; then
  systemctl --user disable --now ps5gamepad 2>/dev/null || true
  rm -f "$UNITS/ps5gamepad.service"
  echo "Migrado: servicio ps5gamepad detenido y sustituido por gamepad."
fi
if [ -e "$BIN/ps5gamepad" ]; then
  # La opción de lanzamiento antigua de Steam sigue funcionando hasta que la cambies.
  printf '#!/bin/sh\nexec "%s/gamepad" "$@"\n' "$BIN" > "$BIN/ps5gamepad"
  chmod 755 "$BIN/ps5gamepad"
  echo "Aviso: cambia en Steam la opción de lanzamiento a la de abajo (ps5gamepad seguirá funcionando mientras tanto)."
fi
OLD_DATA="${XDG_DATA_HOME:-$HOME/.local/share}/ps5gamepad"
NEW_DATA="${XDG_DATA_HOME:-$HOME/.local/share}/gamepad"
if [ -d "$OLD_DATA/portraits" ] && [ ! -e "$NEW_DATA/portraits" ]; then
  mkdir -p "$NEW_DATA" && chmod 700 "$NEW_DATA"
  mv "$OLD_DATA/portraits" "$NEW_DATA/portraits"
  echo "Migrado: retratos movidos a $NEW_DATA/portraits"
fi

# Plugins: desde 0.3 se instalan aparte (gamepad plugin install). Restos del formato antiguo:
for f in "$DIR/plugins/ffrs.py" "$DIR/plugins/_template.py"; do
  if [ -f "$f" ]; then rm -f "$f"; echo "Quitado $(basename "$f") antiguo (el plugin ahora se instala aparte)."; fi
done
PLUGINS="${XDG_DATA_HOME:-$HOME/.local/share}/gamepad/plugins"
if [ ! -d "$PLUGINS/ffrs" ] && [ ! -d "$DIR/plugins/ffrs" ]; then
  echo "Aviso: el plugin de FF Resonance no está instalado: gamepad plugin install gamepad-plugin-ffrs-<versión>.zip"
fi

systemctl --user daemon-reload

echo "Instalado: $BIN/gamepad (proyecto en $DIR)"
echo
if [ -w /dev/uinput ]; then
  echo "OK: tu usuario puede escribir en /dev/uinput (mando virtual sin root)."
else
  echo "FALTA: tu usuario no puede escribir en /dev/uinput. Ver README, sección 'Permisos del mando'."
fi
if systemctl is-active --quiet firewalld 2>/dev/null; then
  echo
  echo "AVISO: firewalld está activo (el servicio usa el puerto 8888). Si Android no conecta (\"Address Unreachable\"), ver README, sección 'Firewall'."
fi
echo
echo "Arrancar (y al iniciar sesión): systemctl --user enable --now gamepad"
echo "Reiniciar tras actualizar:      systemctl --user restart gamepad"
echo "Ver el código de acceso:        journalctl --user -u gamepad -n 20"
echo "Opción de Steam:                $BIN/gamepad run mangohud %command%"
echo "Plugins:                        $BIN/gamepad plugin list"
