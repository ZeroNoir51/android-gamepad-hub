package dev.gamepad.client;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.robolectric.Shadows.shadowOf;

import android.os.Looper;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

import org.json.JSONObject;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowDialog;

import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** La actividad real en la JVM: arranque, panel del juego, ajustes, mando táctil y físico. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35, qualifiers = "w800dp-h400dp-land")
public class MainActivityTest {
    private MainActivity a;

    @Before public void setUp() {
        a = Robolectric.buildActivity(MainActivity.class).create().start().resume().get();
        shadowOf(Looper.getMainLooper()).idle();
    }

    private Object field(String name) throws Exception {
        Field f = MainActivity.class.getDeclaredField(name);
        f.setAccessible(true);
        return f.get(a);
    }

    private Object call(String name, Class<?>[] types, Object... args) throws Exception {
        Method m = MainActivity.class.getDeclaredMethod(name, types);
        m.setAccessible(true);
        return m.invoke(a, args);
    }

    private void showHudWithGame() throws Exception {
        call("showHud", new Class<?>[0]);
        String meta = "{\"t\":\"game\",\"state\":\"attached\",\"id\":\"ffrs\",\"name\":\"Final Fantasy Resonance\",\"pid\":5,"
                + "\"fields\":[{\"key\":\"p1_name\",\"label\":\"Miembro 1\",\"kind\":\"text\",\"section\":\"party\",\"slot\":1},"
                + "{\"key\":\"p1_img\",\"label\":\"Retrato\",\"kind\":\"image\",\"section\":\"party\",\"slot\":1},"
                + "{\"key\":\"p1_hp\",\"label\":\"HP\",\"kind\":\"bar\",\"max_key\":\"p1_hp_max\",\"tone\":\"hp\",\"section\":\"party\",\"slot\":1},"
                + "{\"key\":\"p2_name\",\"label\":\"Miembro 2\",\"kind\":\"text\",\"section\":\"party\",\"slot\":2},"
                + "{\"key\":\"gil\",\"label\":\"Gil\",\"tone\":\"gold\",\"section\":\"stats\"},"
                + "{\"key\":\"battle\",\"label\":\"Batalla\",\"kind\":\"text\",\"section\":\"header\"},"
                + "{\"key\":\"status\",\"label\":\"Estado\",\"kind\":\"text\",\"section\":\"info\"}]}";
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject(meta));
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject(
                "{\"t\":\"gv\",\"v\":{\"p1_name\":\"Rain\",\"p1_img\":null,\"p1_hp\":228,\"p1_hp_max\":326,"
                        + "\"p2_name\":\"Lasswell\",\"gil\":1120,\"battle\":\"en batalla (2)\",\"status\":\"Lectura OK\"}}"));
        shadowOf(Looper.getMainLooper()).idle();
    }

    private PadState pad() throws Exception {
        return (PadState) field("pad");
    }

    private static TextView findText(View root, String text) {
        if (root instanceof TextView && text.contentEquals(((TextView) root).getText())) return (TextView) root;
        if (root instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) root;
            for (int i = 0; i < g.getChildCount(); i++) {
                TextView t = findText(g.getChildAt(i), text);
                if (t != null) return t;
            }
        }
        return null;
    }

    @Test public void arrancaEnLaPantallaDeConexion() {
        View content = a.findViewById(android.R.id.content);
        assertNotNull(findText(content, "Conectar con el servidor"));
    }

    @Test public void panelDelJuegoYDisposicion() throws Exception {
        showHudWithGame();
        View content = a.findViewById(android.R.id.content);
        assertNotNull(findText(content, "Rain"));
        assertNotNull(findText(content, "Lasswell"));
        assertNotNull(findText(content, "PID 5 · en batalla (2)"));
        assertNotNull(findText(content, "1.120"));
        // Telemetría oculta: solo queda el botón Guide (sin texto, con el icono)
        call("saveLayout", new Class<?>[] {String.class, Object.class}, "tel", "hidden");
        assertEquals(View.GONE, ((View) field("telBox")).getVisibility());
        assertEquals("", ((Button) field("guideBtn")).getText().toString());
        assertNotNull(((Button) field("guideBtn")).getCompoundDrawables()[0]);
        // A la derecha: el panel del juego pasa a ser el primero
        call("saveLayout", new Class<?>[] {String.class, Object.class}, "tel", "right");
        ViewGroup body = (ViewGroup) field("body");
        assertTrue(body.getChildAt(0) == field("right"));
        call("saveLayout", new Class<?>[] {String.class, Object.class}, "cols", 1);
        call("saveLayout", new Class<?>[] {String.class, Object.class}, "order", "stats");
        assertTrue(a.getSharedPreferences("gamepad", 0).getString("layout:ffrs", "").contains("\"cols\":1"));
    }

    @Test public void tarjetasAnilloSinMaximo() throws Exception {
        call("showHud", new Class<?>[0]);
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject(
                "{\"t\":\"game\",\"state\":\"attached\",\"id\":\"trails2\",\"name\":\"Trails\",\"pid\":7,\"style\":\"ring\",\"fields\":["
                + "{\"key\":\"p1_name\",\"label\":\"Miembro 1\",\"kind\":\"text\",\"section\":\"party\",\"slot\":1},"
                + "{\"key\":\"p1_hp\",\"label\":\"HP\",\"kind\":\"bar\",\"max_key\":\"p1_hp_max\",\"tone\":\"hp\",\"section\":\"party\",\"slot\":1},"
                + "{\"key\":\"p1_cp\",\"label\":\"CP\",\"kind\":\"bar\",\"max_key\":\"p1_cp_max\",\"tone\":\"limit\",\"section\":\"party\",\"slot\":1}]}"));
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject(
                "{\"t\":\"gv\",\"v\":{\"p1_name\":\"Estelle\",\"p1_hp\":3096,\"p1_hp_max\":3400,\"p1_cp\":187,\"p1_cp_max\":200}}"));
        shadowOf(Looper.getMainLooper()).idle();
        View content = a.findViewById(android.R.id.content);
        assertNotNull(findText(content, "3.096"));   // solo el número, sin "/ 3.400"
        assertNotNull(findText(content, "187"));
        assertNotNull(findText(content, "CP"));
    }

    @Test public void desconectarYConectarAMano() throws Exception {
        call("showHud", new Class<?>[0]);
        for (String[] kv : new String[][] {{"cookie", "x"}, {"host", "127.0.0.1"}}) {
            Field f = MainActivity.class.getDeclaredField(kv[0]);
            f.setAccessible(true);
            f.set(a, kv[1]);
        }
        Field port = MainActivity.class.getDeclaredField("port");
        port.setAccessible(true);
        port.setInt(a, 9);
        call("toggleLink", new Class<?>[0]);              // sin conexión: Conectar conecta ya
        Button link = (Button) field("linkBtn");
        assertNotNull(field("ws"));
        assertEquals("Desconectar", link.getText().toString());
        call("toggleLink", new Class<?>[0]);              // Desconectar: suelta y no reintenta
        shadowOf(Looper.getMainLooper()).idle();
        assertNull(field("ws"));
        assertEquals("Conectar", link.getText().toString());
        assertEquals("Desconectado · pulsa Conectar", ((TextView) field("conn")).getText().toString());
        shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(20));
        assertNull(field("ws"));                          // sin reconexión automática
    }

    @Test public void ajustesSeAbren() throws Exception {
        showHudWithGame();
        call("showSettings", new Class<?>[0]);
        shadowOf(Looper.getMainLooper()).idle();
        assertNotNull(ShadowDialog.getLatestDialog());
        assertTrue(ShadowDialog.getLatestDialog().isShowing());
    }

    @Test public void mandoTactilYFisicoSeMezclan() throws Exception {
        showHudWithGame();
        TouchPadView touch = (TouchPadView) field("touchPad");
        assertEquals("sin mando físico, el táctil se ve en modo automático", View.VISIBLE, touch.getVisibility());
        touch.layout(0, 0, 1920, 1080);
        float u = Math.min(1080 / 7f, 1920 / 15f);
        float ax = 1920 - 1.9f * u, ay = 1080 - 4.2f * u + 0.95f * u;
        long t = SystemClock.uptimeMillis();
        assertTrue(touch.dispatchTouchEvent(MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, ax, ay, 0)));
        assertEquals(1, pad().get(PadState.A));
        // Botón B del mando físico mientras se mantiene A en pantalla
        KeyEvent b = new KeyEvent(t, t, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_BUTTON_B, 0, 0, 0, 0, 0,
                InputDevice.SOURCE_GAMEPAD);
        assertTrue(a.dispatchKeyEvent(b));
        assertEquals(1, pad().get(PadState.A));
        assertEquals(1, pad().get(PadState.B));
        touch.dispatchTouchEvent(MotionEvent.obtain(t, t + 50, MotionEvent.ACTION_UP, ax, ay, 0));
        assertEquals(0, pad().get(PadState.A));
        assertEquals(1, pad().get(PadState.B));
        // Stick izquierdo: arrastrar a la derecha
        float sx = 1.9f * u, sy = 1080 - 3.9f * u;
        touch.dispatchTouchEvent(MotionEvent.obtain(t, t + 60, MotionEvent.ACTION_DOWN, sx, sy, 0));
        touch.dispatchTouchEvent(MotionEvent.obtain(t, t + 70, MotionEvent.ACTION_MOVE, sx + 2 * u, sy, 0));
        assertEquals(32767, pad().get(PadState.LX));
        touch.dispatchTouchEvent(MotionEvent.obtain(t, t + 80, MotionEvent.ACTION_UP, sx + 2 * u, sy, 0));
        assertEquals(0, pad().get(PadState.LX));
        // Guide del mando táctil (centro, abajo)
        touch.dispatchTouchEvent(MotionEvent.obtain(t, t + 82, MotionEvent.ACTION_DOWN, 960, 1080 - 0.75f * u, 0));
        assertEquals(1, pad().get(PadState.GUIDE));
        touch.dispatchTouchEvent(MotionEvent.obtain(t, t + 84, MotionEvent.ACTION_UP, 960, 1080 - 0.75f * u, 0));
        assertEquals(0, pad().get(PadState.GUIDE));
        // Un toque fuera de los controles no es del mando: pasa a la interfaz
        assertTrue(!touch.dispatchTouchEvent(MotionEvent.obtain(t, t + 90, MotionEvent.ACTION_DOWN, 960, 400, 0)));
        // Modo "Nunca": se oculta y suelta todo
        a.getSharedPreferences("gamepad", 0).edit().putInt("touchMode", 0).commit();
        call("updateTouchPad", new Class<?>[0]);
        assertEquals(View.GONE, touch.getVisibility());
    }

    @Test public void avisoSinMandoVirtual() throws Exception {
        call("showHud", new Class<?>[0]);
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject(
                "{\"t\":\"hello\",\"v\":\"0.4.1\",\"host\":\"pc\",\"pad\":\"sin mando virtual\",\"padErr\":\"sin permiso para /dev/uinput\"}"));
        TextView w = (TextView) field("padWarn");
        assertEquals(View.VISIBLE, w.getVisibility());
        assertTrue(w.getText().toString().contains("sin permiso para /dev/uinput"));
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject("{\"t\":\"pad\",\"name\":\"GamePad\",\"err\":null}"));
        assertEquals("Mando virtual listo en el PC.", w.getText().toString());
        shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(5));
        assertEquals(View.GONE, w.getVisibility());
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject(
                "{\"t\":\"hello\",\"v\":\"0.4.1\",\"host\":\"pc\",\"pad\":\"GamePad\",\"padErr\":null}"));
        assertEquals(View.GONE, w.getVisibility());
    }

    @Test public void sinJuegoNoHayFondoNiAjustesDePlugin() throws Exception {
        call("showHud", new Class<?>[0]);
        call("onMessage", new Class<?>[] {JSONObject.class}, new JSONObject("{\"t\":\"game\",\"state\":\"none\"}"));
        assertNull(((View) field("right")).getBackground());
        call("showSettings", new Class<?>[0]);
        shadowOf(Looper.getMainLooper()).idle();
        assertTrue(ShadowDialog.getLatestDialog().isShowing());
    }
}
