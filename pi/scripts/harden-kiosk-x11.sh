#!/usr/bin/env bash
set -euo pipefail

USER_HOME="${HOME:-$(getent passwd "$(id -un)" | cut -d: -f6)}"
OPENBOX_DIR="$USER_HOME/.config/openbox"
OPENBOX_RC="$OPENBOX_DIR/lxde-pi-rc.xml"
SYSTEM_OPENBOX_RC="/etc/xdg/openbox/lxde-pi-rc.xml"

mkdir -p "$OPENBOX_DIR"

if [ ! -f "$OPENBOX_RC" ]; then
  if [ -f "$SYSTEM_OPENBOX_RC" ]; then
    cp "$SYSTEM_OPENBOX_RC" "$OPENBOX_RC"
  else
    cat >"$OPENBOX_RC" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <keyboard></keyboard>
</openbox_config>
XML
  fi
fi

python3 - "$OPENBOX_RC" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

path = Path(sys.argv[1])
ET.register_namespace("", "http://openbox.org/3.4/rc")
tree = ET.parse(path)
root = tree.getroot()
ns = "{http://openbox.org/3.4/rc}"

keyboard = root.find(f"{ns}keyboard")
if keyboard is None:
    keyboard = ET.SubElement(root, f"{ns}keyboard")

blocked_keys = {
    "A-F4",
    "C-q",
    "C-Q",
    "A-space",
    "A-Tab",
    "A-Escape",
    "C-A-Delete",
}

for keybind in list(keyboard.findall(f"{ns}keybind")):
    if keybind.attrib.get("key") in blocked_keys:
        keyboard.remove(keybind)

for key in sorted(blocked_keys):
    keybind = ET.SubElement(keyboard, f"{ns}keybind", {"key": key})
    ET.SubElement(keybind, f"{ns}action", {"name": "Execute"})

tree.write(path, encoding="UTF-8", xml_declaration=True)
PY

if command -v openbox --reconfigure >/dev/null 2>&1; then
  DISPLAY="${DISPLAY:-:0}" openbox --reconfigure || true
fi

printf 'KahrabaIQ kiosk X11 shortcut hardening applied to %s\n' "$OPENBOX_RC"
