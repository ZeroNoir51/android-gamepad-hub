package dev.gamepad.client;

import java.util.Arrays;

/** Estado completo del mando con las claves y rangos de server/protocol.py. Sin Android. */
public final class PadState {
    public static final String[] KEYS = {"a", "b", "x", "y", "lb", "rb", "back", "start", "guide", "ls", "rs",
            "lx", "ly", "rx", "ry", "lt", "rt", "dx", "dy"};
    public static final int A = 0, B = 1, X = 2, Y = 3, LB = 4, RB = 5, BACK = 6, START = 7, GUIDE = 8,
            LS = 9, RS = 10, LX = 11, LY = 12, RX = 13, RY = 14, LT = 15, RT = 16, DX = 17, DY = 18;

    private final int[] v = new int[KEYS.length];

    public int get(int i) { return v[i]; }

    /** true si el valor cambió. Recorta al rango del protocolo. */
    public boolean set(int i, int value) {
        int clamped;
        if (i <= RS) clamped = value != 0 ? 1 : 0;
        else if (i <= RY) clamped = Math.max(-32768, Math.min(32767, value));
        else if (i <= RT) clamped = Math.max(0, Math.min(255, value));
        else clamped = Integer.signum(value);
        if (v[i] == clamped) return false;
        v[i] = clamped;
        return true;
    }

    /** Eje -1..1 -> -32768..32767. */
    public static int stick(float f) {
        return Math.round(Math.max(-1f, Math.min(1f, f)) * 32767f);
    }

    /** Gatillo 0..1 -> 0..255. */
    public static int trigger(float f) {
        return Math.round(Math.max(0f, Math.min(1f, f)) * 255f);
    }

    public boolean neutral() {
        boolean changed = false;
        for (int i = 0; i < v.length; i++) changed |= set(i, 0);
        return changed;
    }

    public String toMessage() {
        StringBuilder sb = new StringBuilder(160).append("{\"t\":\"in\",\"s\":{");
        for (int i = 0; i < KEYS.length; i++) {
            if (i > 0) sb.append(',');
            sb.append('"').append(KEYS[i]).append("\":").append(v[i]);
        }
        return sb.append("}}").toString();
    }

    @Override public boolean equals(Object o) {
        return o instanceof PadState && Arrays.equals(v, ((PadState) o).v);
    }

    @Override public int hashCode() { return Arrays.hashCode(v); }
}
