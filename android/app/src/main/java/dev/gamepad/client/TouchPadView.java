package dev.gamepad.client;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.SparseArray;
import android.view.MotionEvent;
import android.view.View;

import java.util.ArrayList;
import java.util.List;

/**
 * Mando táctil multitáctil, semitransparente, encima del panel. Los toques que no caen en un
 * control pasan a la interfaz de debajo. Cada dedo queda ligado al control donde empezó.
 */
final class TouchPadView extends View {
    interface Listener {
        /** El estado táctil cambió (se llama en el hilo de la interfaz). */
        void onTouchPad(PadState state);
    }

    private static final int BUTTON = 0, STICK = 1, DPAD = 2;

    private static final class Control {
        final int type, key;   // key: índice de PadState (en STICK, el eje X; Y = key + 1)
        final String label;
        float cx, cy, r;
        boolean pressed;
        float knobX, knobY;    // STICK: desplazamiento -1..1
        int dirX, dirY;        // DPAD

        Control(int type, int key, String label) {
            this.type = type;
            this.key = key;
            this.label = label;
        }

        boolean hit(float x, float y) {
            float dx = x - cx, dy = y - cy;
            return dx * dx + dy * dy <= r * r * 1.15f;
        }
    }

    private final List<Control> controls = new ArrayList<>();
    private final SparseArray<Control> owners = new SparseArray<>();
    private final PadState state = new PadState();
    private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final Listener listener;
    private final float density;

    TouchPadView(Context c, Listener listener) {
        super(c);
        this.listener = listener;
        density = c.getResources().getDisplayMetrics().density;
        stroke.setStyle(Paint.Style.STROKE);
        stroke.setStrokeWidth(1.5f * density);
        text.setTextAlign(Paint.Align.CENTER);
        text.setFakeBoldText(true);
        add(STICK, PadState.LX, "");
        add(STICK, PadState.RX, "");
        add(DPAD, PadState.DX, "");
        add(BUTTON, PadState.A, "A");
        add(BUTTON, PadState.B, "B");
        add(BUTTON, PadState.X, "X");
        add(BUTTON, PadState.Y, "Y");
        add(BUTTON, PadState.LB, "LB");
        add(BUTTON, PadState.LT, "LT");
        add(BUTTON, PadState.RB, "RB");
        add(BUTTON, PadState.RT, "RT");
        add(BUTTON, PadState.BACK, "Back");
        add(BUTTON, PadState.START, "Start");
        add(BUTTON, PadState.GUIDE, "Guide");   // el Guide de la pantalla queda bajo LT/LB
        add(BUTTON, PadState.LS, "L3");
        add(BUTTON, PadState.RS, "R3");
    }

    private void add(int type, int key, String label) {
        controls.add(new Control(type, key, label));
    }

    private Control find(int type, int key) {
        for (Control c : controls) if (c.type == type && c.key == key) return c;
        throw new IllegalArgumentException();
    }

    /** Disposición en apaisado: sticks y cruceta a la izquierda, botones y stick derecho a la derecha. */
    @Override protected void onSizeChanged(int w, int h, int ow, int oh) {
        float u = Math.min(h / 7f, w / 15f);   // unidad: un botón mide ~1 u (w/15: R3 nunca toca Start)
        place(STICK, PadState.LX, 1.9f * u, h - 3.9f * u, 1.25f * u);
        place(DPAD, PadState.DX, 3.4f * u, h - 1.5f * u, 1.0f * u);
        place(STICK, PadState.RX, w - 3.4f * u, h - 1.5f * u, 1.1f * u);
        float bx = w - 1.9f * u, by = h - 4.2f * u, d = 0.95f * u, br = 0.5f * u;
        place(BUTTON, PadState.A, bx, by + d, br);
        place(BUTTON, PadState.B, bx + d, by, br);
        place(BUTTON, PadState.X, bx - d, by, br);
        place(BUTTON, PadState.Y, bx, by - d, br);
        float sr = 0.5f * u, top = 0.75f * u;
        place(BUTTON, PadState.LT, 0.75f * u, top, sr);
        place(BUTTON, PadState.LB, 2.0f * u, top, sr);
        place(BUTTON, PadState.RB, w - 2.0f * u, top, sr);
        place(BUTTON, PadState.RT, w - 0.75f * u, top, sr);
        place(BUTTON, PadState.LS, 0.75f * u, h - 1.5f * u, 0.42f * u);
        place(BUTTON, PadState.RS, w - 5.0f * u, h - 0.9f * u, 0.42f * u);
        place(BUTTON, PadState.BACK, w / 2f - 1.3f * u, h - 0.7f * u, 0.45f * u);
        place(BUTTON, PadState.GUIDE, w / 2f, h - 0.75f * u, 0.5f * u);
        place(BUTTON, PadState.START, w / 2f + 1.3f * u, h - 0.7f * u, 0.45f * u);
        text.setTextSize(0.36f * u);
    }

    private void place(int type, int key, float cx, float cy, float r) {
        Control c = find(type, key);
        c.cx = cx;
        c.cy = cy;
        c.r = r;
    }

    @SuppressLint("ClickableViewAccessibility")
    @Override public boolean onTouchEvent(MotionEvent e) {
        int a = e.getActionMasked();
        int idx = e.getActionIndex();
        boolean changed = false;
        switch (a) {
            case MotionEvent.ACTION_DOWN:
            case MotionEvent.ACTION_POINTER_DOWN: {
                Control c = null;
                for (Control k : controls) if (k.hit(e.getX(idx), e.getY(idx))) { c = k; break; }
                if (c == null) return a != MotionEvent.ACTION_DOWN;   // primer dedo fuera: a la interfaz
                owners.put(e.getPointerId(idx), c);
                changed = move(c, e.getX(idx), e.getY(idx), true);
                break;
            }
            case MotionEvent.ACTION_MOVE:
                for (int i = 0; i < e.getPointerCount(); i++) {
                    Control c = owners.get(e.getPointerId(i));
                    if (c != null && c.type != BUTTON) changed |= move(c, e.getX(i), e.getY(i), true);
                }
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_POINTER_UP: {
                Control c = owners.get(e.getPointerId(idx));
                owners.remove(e.getPointerId(idx));
                if (c != null) changed = move(c, 0, 0, false);
                if (a == MotionEvent.ACTION_UP) performClick();
                break;
            }
            case MotionEvent.ACTION_CANCEL:
                changed = releaseAll();
                break;
            default:
                break;
        }
        if (changed) {
            invalidate();
            listener.onTouchPad(state);
        }
        return true;
    }

    @Override public boolean performClick() {
        return super.performClick();
    }

    /** Suelta todo (al ocultar el mando o perder el foco). */
    boolean releaseAll() {
        owners.clear();
        boolean changed = false;
        for (Control c : controls) changed |= move(c, 0, 0, false);
        if (changed) {
            invalidate();
            listener.onTouchPad(state);
        }
        return changed;
    }

    private boolean move(Control c, float x, float y, boolean down) {
        c.pressed = down;
        switch (c.type) {
            case STICK: {
                float dx = down ? (x - c.cx) / c.r : 0, dy = down ? (y - c.cy) / c.r : 0;
                float len = (float) Math.hypot(dx, dy);
                if (len > 1) { dx /= len; dy /= len; }
                c.knobX = dx;
                c.knobY = dy;
                return state.set(c.key, PadState.stick(dx)) | state.set(c.key + 1, PadState.stick(dy));
            }
            case DPAD: {
                int dx = 0, dy = 0;
                if (down) {
                    float rx = x - c.cx, ry = y - c.cy;
                    if (Math.hypot(rx, ry) > c.r * 0.25f) {   // 8 direcciones, con zona muerta central
                        double ang = Math.atan2(ry, rx);
                        int sector = (int) Math.round(ang / (Math.PI / 4)) & 7;
                        int[][] dirs = {{1, 0}, {1, 1}, {0, 1}, {-1, 1}, {-1, 0}, {-1, -1}, {0, -1}, {1, -1}};
                        dx = dirs[sector][0];
                        dy = dirs[sector][1];
                    }
                }
                c.dirX = dx;
                c.dirY = dy;
                return state.set(PadState.DX, dx) | state.set(PadState.DY, dy);
            }
            default: {
                boolean trigger = c.key == PadState.LT || c.key == PadState.RT;
                return state.set(c.key, down ? (trigger ? 255 : 1) : 0);
            }
        }
    }

    @Override protected void onDraw(Canvas cv) {
        for (Control c : controls) {
            int a = c.pressed ? 200 : 150;
            stroke.setColor(Ui.TEXT);
            stroke.setAlpha(a);
            fill.setColor(c.pressed ? Ui.AMBER : Ui.PANEL);
            fill.setAlpha(c.pressed ? 170 : 110);
            cv.drawCircle(c.cx, c.cy, c.r, fill);
            cv.drawCircle(c.cx, c.cy, c.r, stroke);
            if (c.type == STICK) {
                fill.setColor(c.pressed ? Ui.AMBER : Ui.MUTED);
                fill.setAlpha(190);
                cv.drawCircle(c.cx + c.knobX * c.r * 0.6f, c.cy + c.knobY * c.r * 0.6f, c.r * 0.42f, fill);
            } else if (c.type == DPAD) {
                float s = c.r * 0.32f;
                for (int[] d : new int[][] {{0, -1}, {0, 1}, {-1, 0}, {1, 0}}) {
                    boolean on = (d[0] != 0 && d[0] == c.dirX) || (d[1] != 0 && d[1] == c.dirY);
                    fill.setColor(on ? Ui.AMBER : Ui.TEXT);
                    fill.setAlpha(on ? 230 : 150);
                    float cx = c.cx + d[0] * c.r * 0.58f, cy = c.cy + d[1] * c.r * 0.58f;
                    rect.set(cx - s, cy - s, cx + s, cy + s);
                    cv.drawRoundRect(rect, s * 0.3f, s * 0.3f, fill);
                }
            } else {
                text.setColor(c.pressed ? 0xFF1A1408 : Ui.TEXT);
                text.setAlpha(230);
                cv.drawText(c.label, c.cx, c.cy - (text.descent() + text.ascent()) / 2, text);
            }
        }
    }
}
