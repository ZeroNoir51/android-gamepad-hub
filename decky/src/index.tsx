import { callable, definePlugin, toaster } from "@decky/api";
import { ButtonItem, Field, PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { useEffect, useState } from "react";
import { FaGamepad } from "react-icons/fa";

type Status = { up: boolean; url: string | null; code: string | null };

const getStatus = callable<[], Status>("status");
const POLL_MS = 5000;

function describe(s: Status) {
  return `${s.url ?? "sin red"} · código ${s.code ?? "—"}`;
}

// Avisa en Big Picture / Game Mode cuando el servicio pasa a responder (también al iniciar
// Steam con el servicio ya activo) y cuando deja de hacerlo.
let lastUp: boolean | null = null;
async function poll() {
  let s: Status;
  try {
    s = await getStatus();
  } catch {
    return;
  }
  if (s.up && lastUp !== true) {
    toaster.toast({ title: "GamePad listo", body: describe(s), icon: <FaGamepad />, duration: 8000 });
  } else if (!s.up && lastUp === true) {
    toaster.toast({ title: "GamePad no responde", body: "systemctl --user status gamepad", icon: <FaGamepad /> });
  }
  lastUp = s.up;
}

function Content() {
  const [s, setS] = useState<Status | null>(null);
  const refresh = () => getStatus().then(setS).catch(() => setS(null));
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, []);
  return (
    <PanelSection title="Servicio">
      <PanelSectionRow>
        <Field label="Estado">{s == null ? "…" : s.up ? "Activo" : "No responde"}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Android">{s?.url ?? "—"}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Código">{s?.code ?? "—"}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={refresh}>Actualizar</ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => {
  poll();
  const timer = setInterval(poll, POLL_MS);
  return {
    name: "GamePad",
    titleView: <div className={staticClasses.Title}>GamePad</div>,
    content: <Content />,
    icon: <FaGamepad />,
    onDismount() {
      clearInterval(timer);
    },
  };
});
