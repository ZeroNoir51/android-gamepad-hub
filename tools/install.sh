#!/bin/sh
# Instala ps5gamepad para el usuario actual. NO ejecutar con sudo.
set -eu
if [ "$(id -u)" = 0 ]; then echo "Ejecuta este script con tu usuario, sin sudo." >&2; exit 1; fi
DIR="$(cd "$(dirname "$0")/.." && pwd)"

[ -x "$DIR/.venv/bin/python" ] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"

mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/ps5gamepad" <<EOS
#!/bin/sh
PYTHONPATH="$DIR" exec "$DIR/.venv/bin/python" -m server "\$@"
EOS
chmod 755 "$HOME/.local/bin/ps5gamepad"

mkdir -p "$HOME/.config/systemd/user"
cp "$DIR/tools/ps5gamepad.service" "$HOME/.config/systemd/user/ps5gamepad.service"
systemctl --user daemon-reload

echo "Instalado: $HOME/.local/bin/ps5gamepad"
echo
if [ -w /dev/uinput ]; then
  echo "OK: tu usuario puede escribir en /dev/uinput (mando virtual sin root)."
else
  echo "FALTA: tu usuario no puede escribir en /dev/uinput. Ver README, sección 'Permisos del mando'."
fi
if systemctl is-active --quiet firewalld 2>/dev/null; then
  echo
  echo "AVISO: firewalld está activo. Si Android no conecta (\"Address Unreachable\"), ver README, sección 'Firewall'."
fi
echo
echo "Arrancar ahora:          systemctl --user start ps5gamepad"
echo "Arrancar al iniciar:     systemctl --user enable ps5gamepad"
echo "Ver el código de acceso: journalctl --user -u ps5gamepad -n 20"
echo "Opción de Steam:         $HOME/.local/bin/ps5gamepad run mangohud %command%"
