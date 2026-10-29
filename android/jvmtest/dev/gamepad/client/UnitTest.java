package dev.gamepad.client;

/** Pruebas sin red de PadState y Api.unescape. */
public final class UnitTest {
    public static void main(String[] a) {
        NetTest.check(Api.unescape("C\\u00f3digo incorrecto.").equals("Código incorrecto."), "unescape acentos");
        NetTest.check(Api.unescape("fin \\u00").equals("fin \\u00"), "unescape truncado no rompe");
        NetTest.check(Api.unescape("\\uZZZZ $1").equals("\\uZZZZ $1"), "unescape inválido se deja igual");
        PadState p = new PadState();
        NetTest.check(!p.set(PadState.A, 0), "sin cambio devuelve false");
        NetTest.check(p.set(PadState.A, 5) && p.get(PadState.A) == 1, "botón se normaliza a 1");
        p.set(PadState.LX, 99999); p.set(PadState.LT, -4); p.set(PadState.DX, -7);
        NetTest.check(p.get(PadState.LX) == 32767 && p.get(PadState.LT) == 0 && p.get(PadState.DX) == -1, "rangos recortados");
        NetTest.check(PadState.stick(-1f) == -32767 && PadState.trigger(1f) == 255, "conversión de ejes");
        NetTest.check(p.toMessage().startsWith("{\"t\":\"in\",\"s\":{\"a\":1,") && p.toMessage().contains("\"lx\":32767"), "mensaje");
        NetTest.check(p.neutral() && !p.neutral(), "neutral");
        System.out.println("TODO OK");
    }
}
