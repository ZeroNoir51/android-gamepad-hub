package dev.gamepad.client;

import static org.robolectric.Shadows.shadowOf;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Looper;
import android.view.View;

import org.json.JSONObject;
import org.junit.Assume;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;

import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Capturas de la interfaz (solo si se pide: -Dgamepad.screenshots=<carpeta>). */
@RunWith(RobolectricTestRunner.class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = 35, qualifiers = "w800dp-h400dp-land-xhdpi")
public class ScreenshotTest {
    @Test public void capturas() throws Exception {
        String out = System.getProperty("gamepad.screenshots");
        Assume.assumeTrue(out != null);
        MainActivity a = Robolectric.buildActivity(MainActivity.class).setup().get();
        call(a, "showHud");
        msg(a, "{\"t\":\"game\",\"state\":\"attached\",\"id\":\"ffrs\",\"name\":\"Final Fantasy Resonance\",\"pid\":5,\"fields\":["
                + party(1) + "," + party(2) + "," + party(3)
                + ",{\"key\":\"gil\",\"label\":\"Gil\",\"tone\":\"gold\",\"section\":\"stats\"},"
                + "{\"key\":\"battle\",\"label\":\"Batalla\",\"kind\":\"text\",\"section\":\"header\"}]}");
        msg(a, "{\"t\":\"gv\",\"v\":{\"p1_name\":\"Rain\",\"p1_lv\":\"Nv 2 · faltan 70 EXP\",\"p1_hp\":228,\"p1_hp_max\":326,\"p1_mp\":35,\"p1_mp_max\":39,\"p1_lb\":40,\"p1_lb_max\":100,"
                + "\"p2_name\":\"Lasswell\",\"p2_lv\":\"Nv 2 · faltan 70 EXP\",\"p2_hp\":215,\"p2_hp_max\":288,\"p2_mp\":40,\"p2_mp_max\":45,\"p2_lb\":100,\"p2_lb_max\":100,"
                + "\"p3_name\":\"Fina\",\"p3_lv\":\"Nv 1 · faltan 25 EXP\",\"p3_hp\":180,\"p3_hp_max\":200,\"p3_mp\":50,\"p3_mp_max\":50,\"p3_lb\":0,\"p3_lb_max\":100,"
                + "\"gil\":1120,\"battle\":\"en batalla (3)\"}}");
        msg(a, "{\"t\":\"tel\",\"fps\":110,\"ft\":8.0,\"cpu\":{\"load\":32,\"temp\":83},\"gpu\":{\"load\":95,\"temp\":78},"
                + "\"mem\":{\"used\":8482560000,\"total\":15032385536},\"ftNew\":[8,8.2,7.9,9,8.1,12,8,8.3,8,7.8,8,8.4]}");
        shot(a, new File(out, "apk-1-normal.png"));
        call(a, "saveLayout", "tel", "hidden");
        call(a, "saveLayout", "cols", 4);
        shot(a, new File(out, "apk-2-sin-telemetria.png"));
        // Fondo: se inyecta la imagen ya "descargada" (aquí no hay servidor)
        String url = "/backgrounds/ffrs/degradado.png";
        Bitmap bg = Bitmap.createBitmap(960, 540, Bitmap.Config.ARGB_8888);
        Canvas cv = new Canvas(bg);
        android.graphics.Paint p = new android.graphics.Paint();
        p.setShader(new android.graphics.LinearGradient(0, 0, 960, 540, 0xFF1E3C8C, 0xFF8C3C78,
                android.graphics.Shader.TileMode.CLAMP));
        cv.drawRect(0, 0, 960, 540, p);
        set(a, "bgList", new java.util.ArrayList<>(java.util.Collections.singletonList(url)));
        set(a, "bgBitmap", bg);
        set(a, "bgBitmapUrl", url);
        call(a, "saveLayout", "tel", "left");
        call(a, "saveLayout", "cols", 2);
        a.getSharedPreferences("gamepad", 0).edit().putInt("touchMode", 0).commit();
        call(a, "updateTouchPad");
        shot(a, new File(out, "apk-3-fondo-sin-tactil.png"));
    }

    private static String party(int n) {
        return "{\"key\":\"p" + n + "_name\",\"label\":\"Miembro\",\"kind\":\"text\",\"section\":\"party\",\"slot\":" + n + "},"
                + "{\"key\":\"p" + n + "_lv\",\"label\":\"Nivel\",\"kind\":\"text\",\"section\":\"party\",\"slot\":" + n + "},"
                + "{\"key\":\"p" + n + "_hp\",\"label\":\"HP\",\"kind\":\"bar\",\"max_key\":\"p" + n + "_hp_max\",\"tone\":\"hp\",\"section\":\"party\",\"slot\":" + n + "},"
                + "{\"key\":\"p" + n + "_mp\",\"label\":\"MP\",\"kind\":\"bar\",\"max_key\":\"p" + n + "_mp_max\",\"tone\":\"mp\",\"section\":\"party\",\"slot\":" + n + "},"
                + "{\"key\":\"p" + n + "_lb\",\"label\":\"Limit\",\"kind\":\"bar\",\"max_key\":\"p" + n + "_lb_max\",\"tone\":\"limit\",\"section\":\"party\",\"slot\":" + n + "}";
    }

    private static void msg(MainActivity a, String json) throws Exception {
        Method m = MainActivity.class.getDeclaredMethod("onMessage", JSONObject.class);
        m.setAccessible(true);
        m.invoke(a, new JSONObject(json));
    }

    private static void call(MainActivity a, String name, Object... args) throws Exception {
        for (Method m : MainActivity.class.getDeclaredMethods()) {
            if (m.getName().equals(name) && m.getParameterCount() == args.length) {
                m.setAccessible(true);
                m.invoke(a, args);
                return;
            }
        }
        throw new NoSuchMethodException(name);
    }

    private static void set(MainActivity a, String name, Object value) throws Exception {
        Field f = MainActivity.class.getDeclaredField(name);
        f.setAccessible(true);
        f.set(a, value);
    }

    private static void shot(MainActivity a, File file) throws Exception {
        shadowOf(Looper.getMainLooper()).idle();
        View root = a.getWindow().getDecorView();
        int w = 1600, h = 800;
        root.measure(View.MeasureSpec.makeMeasureSpec(w, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(h, View.MeasureSpec.EXACTLY));
        root.layout(0, 0, w, h);
        Bitmap bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        root.draw(new Canvas(bmp));
        try (FileOutputStream f = new FileOutputStream(file)) {
            bmp.compress(Bitmap.CompressFormat.PNG, 100, f);
        }
    }
}
