package dev.gamepad.client;

import android.app.Activity;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.InputFilter;
import android.text.InputType;
import android.util.LruCache;
import android.view.Gravity;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.GridLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/**
 * Cliente nativo y ligero de GamePad Hub: mismo protocolo que web/index.html.
 * - Mando: eventos de Android (onKeyDown / onGenericMotionEvent), sin sondear cada fotograma.
 *   Se envía al cambiar y un latido cada HEARTBEAT_MS (el servidor suelta todo a los 500 ms).
 * - Pantalla: solo se redibuja al llegar datos (telemetría ~4 Hz, juego ~2 Hz).
 */
public final class MainActivity extends Activity {
    private static final long HEARTBEAT_MS = 200, PING_MS = 1000, GUIDE_PULSE_MS = 150;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final LruCache<String, Bitmap> portraitCache = new LruCache<>(16);
    private SharedPreferences prefs;

    // conexión
    private String host;
    private int port;
    private String cookie;
    private WsClient ws;
    private boolean started;
    private long retryMs = 1000;
    private int pingId;
    private final List<Long> rtts = new ArrayList<>();

    // mando
    private final PadState pad = new PadState();     // lo que se envía: mezcla de los dos
    private final PadState phys = new PadState();    // mando físico
    private PadState touchState = new PadState();    // mando táctil (lo rellena TouchPadView)
    private boolean dUp, dDown, dLeft, dRight, guideKey, guideTouch, l2Key, r2Key, guideShown;
    private int hatX, hatY;
    private float ltAxis, rtAxis;
    private long guideUntil, lastSent;
    private String padName = "";

    // vistas
    private View loginView, hudView;
    private EditText hostEdit, codeEdit;
    private TextView loginError, conn, rtt, fps, ft, mh, foot;
    private TextView cpuLoad, cpuTemp, mem, gpuLoad, gpuTemp, jitter;
    private View dot;
    private Button debugBtn, guideBtn;
    private ChartView chart;
    private GamePanel game;
    private LinearLayout body, left, telBox;
    private ScrollView right;
    private boolean debug, gameAttached;
    private SteamIcon guideIcon;
    private TouchPadView touchPad;
    private android.hardware.input.InputManager inputManager;

    // panel del juego: fondo y disposición (por plugin, como en la web)
    private static final java.util.regex.Pattern BG_URL =
            java.util.regex.Pattern.compile("^/backgrounds/[a-z0-9_]+/[A-Za-z0-9_-]+\\.(?i:png|jpe?g|webp)$");
    private List<String> bgList = new ArrayList<>();
    private String bgShownKey, bgLoadingUrl;
    private Bitmap bgBitmap;
    private String bgBitmapUrl;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("gamepad", MODE_PRIVATE);
        host = prefs.getString("host", "");
        port = prefs.getInt("port", 8888);
        cookie = prefs.getString("cookie", null);
        debug = prefs.getBoolean("debug", false);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        loginView = buildLogin();
        hudView = buildHud();
        showLogin(null);
    }

    @Override protected void onResume() {
        super.onResume();
        started = true;
        immersive();
        if (inputManager == null) inputManager = getSystemService(android.hardware.input.InputManager.class);
        inputManager.registerInputDeviceListener(deviceListener, ui);
        updateTouchPad();
        if (cookie == null) {
            showLogin(null);
            return;
        }
        String h = host, c = cookie;
        int p = port;
        io.execute(() -> {
            Boolean ok;
            try { ok = Api.sessionValid(h, p, c); } catch (Exception e) { ok = null; }   // null: sin conexión
            Boolean result = ok;
            ui.post(() -> {
                if (!started) return;
                if (Boolean.FALSE.equals(result)) {
                    forgetSession();
                    showLogin("La sesión caducó. Escribe el código de nuevo.");
                } else {
                    showHud();
                    connect();
                }
            });
        });
    }

    @Override protected void onPause() {
        super.onPause();
        started = false;
        if (inputManager != null) inputManager.unregisterInputDeviceListener(deviceListener);
        if (touchPad != null) touchPad.releaseAll();
        disconnect();
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        io.shutdownNow();
    }

    @Override public void onConfigurationChanged(Configuration c) {
        super.onConfigurationChanged(c);   // mando conectado/girar: sin recrear la actividad
        layoutBody();
    }

    @Override public void onWindowFocusChanged(boolean focus) {
        super.onWindowFocusChanged(focus);
        if (focus) immersive();
        else releaseAll();   // diálogo del sistema encima: no dejar botones pulsados
    }

    // ---------------------------------------------------------------- conexión

    private void connect() {
        if (ws != null || !started || cookie == null) return;
        Ui.set(conn, "Conectando…");
        WsClient client = new WsClient(host, port, cookie, new WsClient.Listener() {
            @Override public void onOpen() { ui.post(() -> onOpened()); }
            @Override public void onText(String text) {
                JSONObject m;
                try { m = new JSONObject(text); } catch (Exception e) { return; }
                ui.post(() -> onMessage(m));
            }
            @Override public void onClose(String reason, int status) { ui.post(() -> onClosed(reason, status)); }
        });
        ws = client;
        client.start();
    }

    private void disconnect() {
        ui.removeCallbacks(heartbeat);
        ui.removeCallbacks(ping);
        ui.removeCallbacks(reconnect);
        if (ws != null) {
            phys.neutral();
            touchState.neutral();
            pad.neutral();
            ws.send(pad.toMessage());
            ws.close();
            ws = null;
        }
        setConnected(false, null);
    }

    private void onOpened() {
        retryMs = 1000;
        setConnected(true, null);
        sendState(true);
        ui.postDelayed(heartbeat, HEARTBEAT_MS);
        ui.postDelayed(ping, 300);
    }

    private void onClosed(String reason, int status) {
        ws = null;
        ui.removeCallbacks(heartbeat);
        ui.removeCallbacks(ping);
        setConnected(false, reason);
        resetTelemetry();
        game.clear();
        gameAttached = false;
        layoutBody();
        if (!started) return;
        if (status == 403) {
            forgetSession();
            showLogin("La sesión caducó. Escribe el código de nuevo.");
            return;
        }
        ui.postDelayed(reconnect, retryMs);
        retryMs = Math.min(retryMs * 2, 8000);
    }

    private final Runnable reconnect = this::connect;

    private final Runnable heartbeat = new Runnable() {
        @Override public void run() {
            updateGuide();
            sendState(SystemClock.uptimeMillis() - lastSent >= HEARTBEAT_MS - 20);
            ui.postDelayed(this, HEARTBEAT_MS);
        }
    };

    private final Runnable ping = new Runnable() {
        @Override public void run() {
            if (ws != null) ws.send("{\"t\":\"ping\",\"id\":" + (++pingId) + ",\"ct\":" + SystemClock.elapsedRealtime() + "}");
            ui.postDelayed(this, PING_MS);
        }
    };

    private void sendState(boolean force) {
        if (ws == null || !ws.isOpen()) return;
        if (force || pendingChange) {
            ws.send(pad.toMessage());
            lastSent = SystemClock.uptimeMillis();
            pendingChange = false;
        }
    }

    private boolean pendingChange;

    private void changed(boolean c) {
        if (!c || !merge()) return;
        pendingChange = true;
        sendState(false);   // al momento: la latencia la pone la red, no un temporizador
    }

    /** pad = físico + táctil: botones y gatillos, el mayor; sticks y cruceta, el táctil si se mueve. */
    private boolean merge() {
        boolean c = false;
        for (int i = 0; i < PadState.KEYS.length; i++) {
            int p = phys.get(i), t = touchState.get(i);
            int v;
            if (i <= PadState.RS || i == PadState.LT || i == PadState.RT) v = Math.max(p, t);
            else v = t != 0 ? t : p;
            c |= pad.set(i, v);
        }
        return c;
    }

    private void forgetSession() {
        cookie = null;
        prefs.edit().remove("cookie").apply();
    }

    // ---------------------------------------------------------------- mensajes

    private void onMessage(JSONObject m) {
        switch (m.optString("t")) {
            case "hello":
                Ui.set(conn, m.optString("host") + "  v" + m.optString("v"));
                break;
            case "pong": {
                long sent = m.optLong("ct", -1);
                if (sent < 0) break;
                rtts.add(SystemClock.elapsedRealtime() - sent);
                if (rtts.size() > 20) rtts.remove(0);
                List<Long> sorted = new ArrayList<>(rtts);
                Collections.sort(sorted);
                Ui.set(rtt, sorted.get(sorted.size() / 2) + " ms");
                if (sorted.size() > 3) {
                    Ui.set(jitter, (sorted.get((int) (sorted.size() * .9)) - sorted.get(0)) + " ms");
                }
                break;
            }
            case "tel":
                onTelemetry(m);
                break;
            case "game": {
                String before = game.pluginId;
                game.setMeta(m);
                gameAttached = "attached".equals(m.optString("state"));
                if (game.pluginId == null || !game.pluginId.equals(before)) bgList = new ArrayList<>();
                layoutBody();
                if (game.pluginId != null) fetchMedia(game.pluginId);
                break;
            }
            case "gv":
                game.setValues(m);
                break;
            default:
                break;
        }
    }

    private void onTelemetry(JSONObject m) {
        boolean hasFps = !m.isNull("fps") && m.has("fps");
        Ui.set(fps, hasFps ? String.valueOf(Math.round(m.optDouble("fps"))) : "--");
        fps.setTextColor(hasFps ? Ui.AMBER : Ui.LINE);
        Ui.set(ft, m.isNull("ft") || !m.has("ft") ? "— ms" : String.format(Locale.ROOT, "%.1f ms", m.optDouble("ft")));
        JSONObject cpu = m.optJSONObject("cpu"), gpu = m.optJSONObject("gpu"), mm = m.optJSONObject("mem");
        Ui.set(cpuLoad, fmt(cpu, "load", " %"));
        setTemp(cpuTemp, cpu, 85);
        Ui.set(gpuLoad, fmt(gpu, "load", " %"));
        setTemp(gpuTemp, gpu, 90);
        if (mm != null && mm.optDouble("used", 0) > 0) {
            Ui.set(mem, String.format(Locale.ROOT, "%.1f/%.0f G", mm.optDouble("used") / (1 << 30), mm.optDouble("total") / (1 << 30)));
        } else {
            Ui.set(mem, "—");
        }
        JSONArray news = m.optJSONArray("ftNew");
        if (!hasFps) {
            chart.clear();
        } else if (news != null && news.length() > 0) {
            float[] arr = new float[news.length()];
            for (int i = 0; i < arr.length; i++) arr[i] = (float) news.optDouble(i);
            chart.add(arr);
        }
        String mhText = m.optString("mh", "");
        mh.setVisibility(!hasFps && !mhText.isEmpty() ? View.VISIBLE : View.GONE);
        Ui.set(mh, "MangoHud: " + mhText);
    }

    private static String fmt(JSONObject o, String key, String unit) {
        if (o == null || o.isNull(key) || !o.has(key)) return "—";
        return Math.round(o.optDouble(key)) + unit;
    }

    private void setTemp(TextView t, JSONObject o, int hot) {
        Ui.set(t, fmt(o, "temp", " °C"));
        boolean isHot = o != null && !o.isNull("temp") && o.optDouble("temp", 0) >= hot;
        t.setTextColor(isHot ? Ui.BAD : Ui.TEXT);
    }

    private void resetTelemetry() {
        for (TextView t : new TextView[] {cpuLoad, cpuTemp, mem, gpuLoad, gpuTemp, jitter}) Ui.set(t, "—");
        Ui.set(fps, "--");
        fps.setTextColor(Ui.LINE);
        Ui.set(ft, "— ms");
        Ui.set(rtt, "— ms");
        rtts.clear();
        chart.clear();
        mh.setVisibility(View.GONE);
    }

    // ---------------------------------------------------------------- mando

    private static boolean fromGamepad(int source) {
        return (source & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                || (source & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK;
    }

    // KEYCODE_BACK solo se atiende si viene del mando (algunos mandan BACK en vez de SELECT);
    // el gesto "atrás" del sistema no pasa por aquí.
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public boolean dispatchKeyEvent(KeyEvent e) {
        if (hudView.getParent() == null || !(fromGamepad(e.getSource()) || KeyEvent.isGamepadButton(e.getKeyCode()))) {
            return super.dispatchKeyEvent(e);
        }
        if (e.getAction() == KeyEvent.ACTION_MULTIPLE) return true;
        boolean down = e.getAction() == KeyEvent.ACTION_DOWN;
        if (down && e.getRepeatCount() > 0) return true;
        noteDevice(e.getDevice());
        boolean c;
        switch (e.getKeyCode()) {
            case KeyEvent.KEYCODE_BUTTON_A: c = phys.set(PadState.A, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_B: c = phys.set(PadState.B, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_X: c = phys.set(PadState.X, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_Y: c = phys.set(PadState.Y, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_L1: c = phys.set(PadState.LB, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_R1: c = phys.set(PadState.RB, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_L2: l2Key = down; c = updateTriggers(); break;
            case KeyEvent.KEYCODE_BUTTON_R2: r2Key = down; c = updateTriggers(); break;
            case KeyEvent.KEYCODE_BUTTON_SELECT:
            case KeyEvent.KEYCODE_BACK: c = phys.set(PadState.BACK, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_START:
            case KeyEvent.KEYCODE_MENU: c = phys.set(PadState.START, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_MODE: guideKey = down; c = updateGuide(); break;
            case KeyEvent.KEYCODE_BUTTON_THUMBL: c = phys.set(PadState.LS, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_BUTTON_THUMBR: c = phys.set(PadState.RS, down ? 1 : 0); break;
            case KeyEvent.KEYCODE_DPAD_UP: dUp = down; c = updateDpad(); break;
            case KeyEvent.KEYCODE_DPAD_DOWN: dDown = down; c = updateDpad(); break;
            case KeyEvent.KEYCODE_DPAD_LEFT: dLeft = down; c = updateDpad(); break;
            case KeyEvent.KEYCODE_DPAD_RIGHT: dRight = down; c = updateDpad(); break;
            default: return super.dispatchKeyEvent(e);
        }
        changed(c);
        return true;
    }

    @Override public boolean dispatchGenericMotionEvent(MotionEvent e) {
        if (hudView.getParent() == null || !fromGamepad(e.getSource()) || e.getAction() != MotionEvent.ACTION_MOVE) {
            return super.dispatchGenericMotionEvent(e);
        }
        InputDevice dev = e.getDevice();
        noteDevice(dev);
        boolean zr = dev != null && dev.getMotionRange(MotionEvent.AXIS_Z, e.getSource()) != null
                && dev.getMotionRange(MotionEvent.AXIS_RZ, e.getSource()) != null;
        boolean c = phys.set(PadState.LX, PadState.stick(axis(e, dev, MotionEvent.AXIS_X)));
        c |= phys.set(PadState.LY, PadState.stick(axis(e, dev, MotionEvent.AXIS_Y)));
        c |= phys.set(PadState.RX, PadState.stick(axis(e, dev, zr ? MotionEvent.AXIS_Z : MotionEvent.AXIS_RX)));
        c |= phys.set(PadState.RY, PadState.stick(axis(e, dev, zr ? MotionEvent.AXIS_RZ : MotionEvent.AXIS_RY)));
        ltAxis = Math.max(axis(e, dev, MotionEvent.AXIS_LTRIGGER), axis(e, dev, MotionEvent.AXIS_BRAKE));
        rtAxis = Math.max(axis(e, dev, MotionEvent.AXIS_RTRIGGER), axis(e, dev, MotionEvent.AXIS_GAS));
        c |= updateTriggers();
        hatX = Math.round(e.getAxisValue(MotionEvent.AXIS_HAT_X));
        hatY = Math.round(e.getAxisValue(MotionEvent.AXIS_HAT_Y));
        c |= updateDpad();
        changed(c);
        return true;
    }

    /** Valor del eje con la zona muerta del propio dispositivo (o 0.08). */
    private static float axis(MotionEvent e, InputDevice dev, int axis) {
        float v = e.getAxisValue(axis);
        float flat = 0.08f;
        if (dev != null) {
            InputDevice.MotionRange r = dev.getMotionRange(axis, e.getSource());
            if (r != null) flat = Math.max(flat, r.getFlat());
        }
        return Math.abs(v) <= flat ? 0f : v;
    }

    private boolean updateDpad() {
        int dx = hatX != 0 ? hatX : (dRight ? 1 : 0) - (dLeft ? 1 : 0);
        int dy = hatY != 0 ? hatY : (dDown ? 1 : 0) - (dUp ? 1 : 0);
        return phys.set(PadState.DX, dx) | phys.set(PadState.DY, dy);
    }

    /** Gatillo = el mayor entre el eje analógico y la tecla L2/R2 (hay mandos que dan uno u otro). */
    private boolean updateTriggers() {
        boolean c = phys.set(PadState.LT, l2Key ? 255 : PadState.trigger(ltAxis));
        return phys.set(PadState.RT, r2Key ? 255 : PadState.trigger(rtAxis)) | c;
    }

    private boolean updateGuide() {
        boolean on = guideKey || guideTouch || SystemClock.uptimeMillis() < guideUntil;
        boolean c = phys.set(PadState.GUIDE, on ? 1 : 0);
        if (c || guideBtn.getBackground() == null || on != guideShown) {
            guideShown = on;
            guideBtn.setBackground(Ui.rounded(on ? Ui.AMBER : Ui.PANEL, on ? Ui.AMBER : Ui.LINE, 40, this));
            guideBtn.setTextColor(on ? 0xFF1A1408 : Ui.TEXT);
            guideIcon.setColors(on ? 0xFF1A1408 : Ui.TEXT, on ? Ui.AMBER : Ui.PANEL);
        }
        return c;
    }

    private void releaseAll() {
        dUp = dDown = dLeft = dRight = guideKey = guideTouch = l2Key = r2Key = false;
        hatX = hatY = 0;
        ltAxis = rtAxis = 0f;
        guideUntil = 0;
        changed(phys.neutral());
    }

    private void noteDevice(InputDevice dev) {
        if (dev == null || dev.getName().equals(padName)) return;
        padName = dev.getName();
        Ui.set(foot, "Mando: " + padName);
    }

    // ---------------------------------------------------------------- vistas

    private void showLogin(String msg) {
        disconnect();
        setContentView(loginView);
        hostEdit.setText(host.isEmpty() ? "" : host + ":" + port);
        hostEdit.setHint("192.168.1.50:8888");
        loginError.setText(msg == null ? "" : msg);
        codeEdit.requestFocus();
    }

    private void showHud() {
        if (hudView.getParent() == null) setContentView(hudView);
        layoutBody();
    }

    private View buildLogin() {
        LinearLayout box = Ui.column(this);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Ui.BG);
        int pad = Ui.dp(this, 20);
        box.setPadding(pad, pad, pad, pad);
        LinearLayout form = Ui.column(this);
        TextView h = Ui.text(this, 20, Ui.TEXT);
        h.setText("Conectar con el servidor");
        h.setTypeface(null, android.graphics.Typeface.BOLD);
        TextView p = Ui.text(this, 14, Ui.MUTED);
        p.setText("IP:puerto del PC y el código de 4 letras (gamepad status). No se vuelve a pedir en 24 horas.");
        p.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 12));
        hostEdit = new EditText(this);
        hostEdit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        hostEdit.setTextColor(Ui.TEXT);
        hostEdit.setSingleLine(true);
        codeEdit = new EditText(this);
        codeEdit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        codeEdit.setFilters(new InputFilter[] {new InputFilter.LengthFilter(4), new InputFilter.AllCaps()});
        codeEdit.setTextSize(32);
        codeEdit.setLetterSpacing(0.35f);
        codeEdit.setGravity(Gravity.CENTER);
        codeEdit.setTextColor(Ui.TEXT);
        codeEdit.setHint("ABCD");
        codeEdit.setImeOptions(EditorInfo.IME_ACTION_GO);
        Button go = new Button(this);
        go.setText("Entrar");
        go.setAllCaps(false);
        go.setTextColor(0xFF1A1408);
        go.setBackground(Ui.rounded(Ui.AMBER, 0, 8, this));
        loginError = Ui.text(this, 14, Ui.BAD);
        loginError.setPadding(0, Ui.dp(this, 10), 0, 0);
        Runnable submit = () -> login(go);
        go.setOnClickListener(v -> submit.run());
        codeEdit.setOnEditorActionListener((v, id, ev) -> { submit.run(); return true; });
        for (View v : new View[] {h, p, hostEdit, codeEdit, go, loginError}) form.addView(v);
        box.addView(form, new LinearLayout.LayoutParams(Ui.dp(this, 340), -2));
        ScrollView sv = new ScrollView(this);
        sv.setFillViewport(true);
        sv.setBackgroundColor(Ui.BG);
        sv.addView(box);
        return sv;
    }

    private void login(Button go) {
        String hp = hostEdit.getText().toString().trim();
        String code = codeEdit.getText().toString().trim().toUpperCase(Locale.ROOT);
        String h;
        int p;
        try {
            int i = hp.lastIndexOf(':');
            h = i > 0 ? hp.substring(0, i) : hp;
            p = i > 0 ? Integer.parseInt(hp.substring(i + 1)) : 8888;
            if (h.isEmpty() || p <= 0 || p > 65535) throw new NumberFormatException();
        } catch (NumberFormatException e) {
            loginError.setText("Escribe la dirección como IP:puerto, por ejemplo 192.168.1.50:8888.");
            return;
        }
        if (!code.matches("[A-Z]{4}")) {
            loginError.setText("El código son 4 letras.");
            return;
        }
        go.setEnabled(false);
        loginError.setText("");
        io.execute(() -> {
            String result, error = null;
            try { result = Api.login(h, p, code); } catch (Exception e) { result = null; error = e.getMessage(); }
            String c = result, err = error;
            ui.post(() -> {
                go.setEnabled(true);
                if (c == null) {
                    loginError.setText(err == null ? "No se pudo conectar." : err);
                    return;
                }
                host = h;
                port = p;
                cookie = c;
                prefs.edit().putString("host", h).putInt("port", p).putString("cookie", c).apply();
                codeEdit.setText("");
                showHud();
                connect();
            });
        });
    }

    private View buildHud() {
        LinearLayout root = Ui.column(this);
        root.setBackgroundColor(Ui.BG);

        // barra superior
        LinearLayout top = Ui.row(this);
        int px = Ui.dp(this, 14);
        top.setPadding(px, Ui.dp(this, 6), px, Ui.dp(this, 6));
        dot = new View(this);
        top.addView(dot, new LinearLayout.LayoutParams(Ui.dp(this, 9), Ui.dp(this, 9)));
        conn = Ui.text(this, 14, Ui.TEXT);
        conn.setPadding(Ui.dp(this, 10), 0, 0, 0);
        conn.setSingleLine(true);
        top.addView(conn);
        top.addView(Ui.spacer(this));
        rtt = Ui.number(this, 15, Ui.CYAN);
        rtt.setPadding(0, 0, Ui.dp(this, 12), 0);
        top.addView(rtt);
        Button settings = smallButton("Ajustes");
        settings.setOnClickListener(v -> showSettings());
        top.addView(settings);
        debugBtn = smallButton("Debug");
        debugBtn.setOnClickListener(v -> setDebug(!debug));
        LinearLayout.LayoutParams dlp = new LinearLayout.LayoutParams(-2, -2);
        dlp.leftMargin = Ui.dp(this, 8);
        top.addView(debugBtn, dlp);
        Button server = smallButton("Servidor");
        server.setOnClickListener(v -> showLogin(null));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
        lp.leftMargin = Ui.dp(this, 8);
        top.addView(server, lp);
        root.addView(top);
        root.addView(divider());

        // cuerpo: telemetría | juego
        body = new LinearLayout(this);
        left = Ui.column(this);
        left.setPadding(px, Ui.dp(this, 10), px, Ui.dp(this, 10));
        guideBtn = new Button(this);
        guideBtn.setText("Guide");
        guideBtn.setAllCaps(false);
        guideBtn.setTextSize(18);
        guideBtn.setMinHeight(Ui.dp(this, 72));
        guideBtn.setFocusable(false);   // el mando no navega por la interfaz: todo va al PC
        guideBtn.setPadding(Ui.dp(this, 8), 0, Ui.dp(this, 26), 0);
        guideIcon = new SteamIcon(Ui.TEXT, Ui.PANEL);
        guideIcon.setBounds(0, 0, Ui.dp(this, 56), Ui.dp(this, 56));
        guideBtn.setCompoundDrawables(guideIcon, null, null, null);
        guideBtn.setBackground(Ui.rounded(Ui.PANEL, Ui.LINE, 40, this));   // sin esperar a la primera pulsación
        guideBtn.setTextColor(Ui.TEXT);
        guideBtn.setCompoundDrawablePadding(Ui.dp(this, 12));
        guideBtn.setOnTouchListener((v, ev) -> {
            int a = ev.getActionMasked();
            if (a == MotionEvent.ACTION_DOWN) {
                guideTouch = true;
                guideUntil = SystemClock.uptimeMillis() + GUIDE_PULSE_MS;
                ui.postDelayed(this::guideTick, GUIDE_PULSE_MS + 5);
            } else if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) {
                guideTouch = false;
                if (a == MotionEvent.ACTION_UP) v.performClick();   // accesibilidad
            } else {
                return true;
            }
            changed(updateGuide());
            return true;
        });
        LinearLayout gr = Ui.row(this);
        gr.addView(guideBtn, new LinearLayout.LayoutParams(-2, Ui.dp(this, 72)));
        left.addView(gr);
        telBox = Ui.column(this);
        left.addView(telBox, new LinearLayout.LayoutParams(-1, 0, 1f));

        LinearLayout fpsRow = Ui.row(this);
        fpsRow.setGravity(Gravity.BOTTOM);
        fps = Ui.number(this, 60, Ui.LINE);
        fps.setText("--");
        LinearLayout meta = Ui.column(this);
        meta.setPadding(Ui.dp(this, 10), 0, 0, Ui.dp(this, 4));
        TextView fpsLabel = Ui.text(this, 12.5f, Ui.MUTED);
        fpsLabel.setText("FPS");
        ft = Ui.number(this, 17, Ui.TEXT);
        meta.addView(fpsLabel);
        meta.addView(ft);
        fpsRow.addView(fps);
        fpsRow.addView(meta);
        telBox.addView(fpsRow);
        chart = new ChartView(this);
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(-1, 0, 1f);
        clp.topMargin = Ui.dp(this, 6);
        clp.bottomMargin = Ui.dp(this, 6);
        telBox.addView(chart, clp);
        mh = Ui.text(this, 12, Ui.AMBER);
        mh.setVisibility(View.GONE);
        telBox.addView(mh);
        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(3);
        grid.setBackground(Ui.rounded(Ui.BG, Ui.LINE, 6, this));
        cpuLoad = readout(grid, "CPU");
        cpuTemp = readout(grid, "CPU temp.");
        mem = readout(grid, "RAM");
        gpuLoad = readout(grid, "GPU");
        gpuTemp = readout(grid, "GPU temp.");
        jitter = readout(grid, "Jitter");
        telBox.addView(grid);

        game = new GamePanel(this, this::loadPortrait);
        game.setDebug(debug);
        right = new ScrollView(this);
        right.addView(game.view);
        body.addView(left);
        body.addView(right);
        // mando táctil encima del cuerpo (no de la barra superior ni del pie); los toques que no
        // caen en un control llegan a la interfaz de debajo
        android.widget.FrameLayout bodyFrame = new android.widget.FrameLayout(this);
        bodyFrame.addView(body, new android.widget.FrameLayout.LayoutParams(-1, -1));
        touchPad = new TouchPadView(this, st -> { touchState = st; changed(true); });
        bodyFrame.addView(touchPad, new android.widget.FrameLayout.LayoutParams(-1, -1));
        root.addView(bodyFrame, new LinearLayout.LayoutParams(-1, 0, 1f));

        root.addView(divider());
        foot = Ui.text(this, 12.5f, Ui.MUTED);
        foot.setPadding(px, Ui.dp(this, 6), px, Ui.dp(this, 6));
        foot.setSingleLine(true);
        foot.setText("Pulsa un botón del mando para detectarlo.");
        root.addView(foot);
        setDebug(debug);
        resetTelemetry();
        setConnected(false, null);
        updateTouchPad();
        return root;
    }

    private void guideTick() {
        changed(updateGuide());
    }

    /** Sin juego: la telemetría ocupa todo. Con juego: la disposición elegida en Ajustes
     *  (telemetría a la izquierda, a la derecha u oculta) con columnas 1 : 1.45 como la web. */
    private void layoutBody() {
        if (body == null) return;
        JSONObject l = layout();
        String tel = gameAttached ? l.optString("tel", "left") : "left";
        boolean hidden = "hidden".equals(tel);
        boolean landscape = getResources().getConfiguration().orientation == Configuration.ORIENTATION_LANDSCAPE;
        body.setOrientation(landscape ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        body.removeAllViews();
        if ("right".equals(tel)) { body.addView(right); body.addView(left); }
        else { body.addView(left); body.addView(right); }
        right.setVisibility(gameAttached ? View.VISIBLE : View.GONE);
        telBox.setVisibility(hidden ? View.GONE : View.VISIBLE);
        guideBtn.setText(hidden ? "" : "Guide");
        guideBtn.setCompoundDrawablePadding(hidden ? 0 : Ui.dp(this, 12));
        guideBtn.setPadding(Ui.dp(this, 8), 0, Ui.dp(this, hidden ? 8 : 26), 0);
        if (landscape) {
            left.setLayoutParams(hidden ? new LinearLayout.LayoutParams(-2, -1) : new LinearLayout.LayoutParams(0, -1, 1f));
            right.setLayoutParams(new LinearLayout.LayoutParams(0, -1, 1.45f));
        } else {
            int h = hidden ? -2 : (gameAttached ? Ui.dp(this, 360) : 0);
            left.setLayoutParams(new LinearLayout.LayoutParams(-1, h, gameAttached || hidden ? 0 : 1f));
            right.setLayoutParams(new LinearLayout.LayoutParams(-1, 0, 1f));
        }
        game.setColumns(l.optInt("cols", 2));
        game.setStatsFirst("stats".equals(l.optString("order")));
        applyBackground(l);
    }

    // ---------------------------------------------------------------- ajustes

    /** Disposición del plugin actual (mismas claves que la web: bg, dim, tel, order, cols). */
    private JSONObject layout() {
        JSONObject l = new JSONObject();
        try {
            l.put("bg", "auto").put("dim", 55).put("tel", "left").put("order", "party").put("cols", 2);
            if (game != null && game.pluginId != null) {
                JSONObject saved = new JSONObject(prefs.getString("layout:" + game.pluginId, "{}"));
                for (java.util.Iterator<String> it = saved.keys(); it.hasNext(); ) {
                    String k = it.next();
                    l.put(k, saved.get(k));
                }
            }
        } catch (Exception ignored) { }
        return l;
    }

    private void saveLayout(String key, Object value) {
        if (game.pluginId == null) return;
        JSONObject l = layout();
        try { l.put(key, value); } catch (Exception ignored) { }
        prefs.edit().putString("layout:" + game.pluginId, l.toString()).apply();
        layoutBody();
    }

    private void fetchMedia(String pluginId) {
        String h = host, c = cookie;
        int p = port;
        io.execute(() -> {
            List<String> list = new ArrayList<>();
            try {
                JSONArray arr = new JSONObject(new String(Api.get(h, p, "/api/media/" + pluginId, c), "UTF-8"))
                        .optJSONArray("backgrounds");
                for (int i = 0; arr != null && i < arr.length(); i++) {
                    String u = arr.optString(i);
                    if (BG_URL.matcher(u).matches()) list.add(u);
                }
            } catch (Exception ignored) { }
            ui.post(() -> {
                if (!pluginId.equals(game.pluginId)) return;
                bgList = list;
                layoutBody();
            });
        });
    }

    /** Fondo del panel del juego: la imagen elegida (o la primera), recortada y oscurecida. */
    private void applyBackground(JSONObject l) {
        String bg = l.optString("bg", "auto");
        String url = !gameAttached || "none".equals(bg) ? null : (bgList.contains(bg) ? bg : (bgList.isEmpty() ? null : bgList.get(0)));
        float dim = Math.max(0, Math.min(90, l.optInt("dim", 55))) / 100f;
        String key = url == null ? null : url + "@" + dim;
        if (key == null ? bgShownKey == null : key.equals(bgShownKey)) return;
        if (url == null) {
            bgShownKey = null;
            right.setBackground(null);
            return;
        }
        if (url.equals(bgBitmapUrl) && bgBitmap != null) {
            bgShownKey = key;
            right.setBackground(new CoverDrawable(bgBitmap, dim));
            return;
        }
        if (url.equals(bgLoadingUrl)) return;
        bgLoadingUrl = url;
        String h = host, c = cookie;
        int p = port, target = Math.max(getResources().getDisplayMetrics().widthPixels,
                getResources().getDisplayMetrics().heightPixels);
        io.execute(() -> {
            Bitmap bmp = null;
            try {
                byte[] data = Api.get(h, p, url, c);
                BitmapFactory.Options o = new BitmapFactory.Options();
                o.inJustDecodeBounds = true;
                BitmapFactory.decodeByteArray(data, 0, data.length, o);
                int sample = 1;
                while (Math.max(o.outWidth, o.outHeight) / (sample * 2) >= target) sample *= 2;
                BitmapFactory.Options d = new BitmapFactory.Options();
                d.inSampleSize = sample;
                bmp = BitmapFactory.decodeByteArray(data, 0, data.length, d);
            } catch (Exception ignored) { }
            Bitmap result = bmp;
            ui.post(() -> {
                bgLoadingUrl = null;
                if (result == null) return;
                bgBitmap = result;
                bgBitmapUrl = url;
                bgShownKey = null;
                layoutBody();
            });
        });
    }

    private static final String[] TOUCH_MODES = {"Nunca", "Automático (si no hay mando físico)", "Siempre"};

    /** 0 nunca, 1 automático, 2 siempre. */
    private void updateTouchPad() {
        if (touchPad == null) return;
        int mode = prefs.getInt("touchMode", 1);
        boolean show = mode == 2 || (mode == 1 && !hasPhysicalPad());
        touchPad.setAlpha(prefs.getInt("touchAlpha", 50) / 100f);
        if (!show) touchPad.releaseAll();
        touchPad.setVisibility(show ? View.VISIBLE : View.GONE);
    }

    private static boolean hasPhysicalPad() {
        for (int id : InputDevice.getDeviceIds()) {
            InputDevice d = InputDevice.getDevice(id);
            if (d != null && !d.isVirtual() && fromGamepad(d.getSources())) return true;
        }
        return false;
    }

    private final android.hardware.input.InputManager.InputDeviceListener deviceListener =
            new android.hardware.input.InputManager.InputDeviceListener() {
                @Override public void onInputDeviceAdded(int id) { updateTouchPad(); }
                @Override public void onInputDeviceRemoved(int id) { updateTouchPad(); }
                @Override public void onInputDeviceChanged(int id) { updateTouchPad(); }
            };

    private void showSettings() {
        LinearLayout box = Ui.column(this);
        int pad = Ui.dp(this, 20);
        box.setPadding(pad, Ui.dp(this, 8), pad, 0);

        box.addView(section("Mando táctil"));
        android.widget.RadioGroup modes = new android.widget.RadioGroup(this);
        for (int i = 0; i < TOUCH_MODES.length; i++) {
            android.widget.RadioButton rb = new android.widget.RadioButton(this);
            rb.setText(TOUCH_MODES[i]);
            rb.setId(View.generateViewId());
            rb.setTag(i);
            modes.addView(rb);
            if (i == prefs.getInt("touchMode", 1)) rb.setChecked(true);
        }
        modes.setOnCheckedChangeListener((g, id) -> {
            prefs.edit().putInt("touchMode", (Integer) g.findViewById(id).getTag()).apply();
            updateTouchPad();
        });
        box.addView(modes);
        box.addView(slider("Opacidad", 20, 90, prefs.getInt("touchAlpha", 50), v -> {
            prefs.edit().putInt("touchAlpha", v).apply();
            updateTouchPad();
        }));

        boolean has = game.pluginId != null;
        box.addView(section(has ? "Panel del juego: " + game.pluginName : "Panel del juego"));
        if (!has) {
            TextView t = Ui.text(this, 14, Ui.MUTED);
            t.setText("Abre un juego con plugin para configurar su panel.");
            box.addView(t);
        } else {
            JSONObject l = layout();
            List<String> bgValues = new ArrayList<>();
            List<String> bgLabels = new ArrayList<>();
            bgValues.add("auto");
            bgLabels.add(bgList.isEmpty() ? "Automático (no hay imágenes)" : "Automático (la primera imagen)");
            bgValues.add("none");
            bgLabels.add("Ninguno");
            for (String u : bgList) {
                bgValues.add(u);
                bgLabels.add(u.substring(u.lastIndexOf('/') + 1));
            }
            box.addView(choice("Fondo", bgLabels, Math.max(0, bgValues.indexOf(l.optString("bg"))),
                    i -> saveLayout("bg", bgValues.get(i))));
            box.addView(slider("Oscurecer el fondo", 0, 90, l.optInt("dim", 55), v -> saveLayout("dim", v)));
            String[] tels = {"left", "right", "hidden"};
            box.addView(choice("Telemetría", java.util.Arrays.asList("A la izquierda", "A la derecha", "Oculta (solo Guide)"),
                    Math.max(0, java.util.Arrays.asList(tels).indexOf(l.optString("tel"))), i -> saveLayout("tel", tels[i])));
            box.addView(choice("Orden", java.util.Arrays.asList("Equipo primero", "Estadísticas primero"),
                    "stats".equals(l.optString("order")) ? 1 : 0, i -> saveLayout("order", i == 1 ? "stats" : "party")));
            int[] cols = {1, 2, 4};
            int ci = l.optInt("cols", 2) == 1 ? 0 : (l.optInt("cols", 2) == 4 ? 2 : 1);
            box.addView(choice("Columnas del equipo", java.util.Arrays.asList("1", "2", "4"), ci, i -> saveLayout("cols", cols[i])));
            TextView hint = Ui.text(this, 12.5f, Ui.MUTED);
            hint.setText("Los fondos son imágenes tuyas (png, jpg o webp) en ~/.local/share/gamepad/backgrounds/"
                    + game.pluginId + "/ del PC.");
            hint.setPadding(0, Ui.dp(this, 10), 0, Ui.dp(this, 6));
            box.addView(hint);
        }
        ScrollView sv = new ScrollView(this);
        sv.addView(box);
        new android.app.AlertDialog.Builder(this, android.R.style.Theme_Material_Dialog_Alert)
                .setTitle("Ajustes")
                .setView(sv)
                .setPositiveButton("Listo", null)
                .setOnDismissListener(d -> immersive())
                .show();
    }

    private TextView section(String title) {
        TextView t = Ui.text(this, 15, Ui.AMBER);
        t.setText(title);
        t.setPadding(0, Ui.dp(this, 14), 0, Ui.dp(this, 4));
        return t;
    }

    private View slider(String label, int min, int max, int value, java.util.function.IntConsumer onChange) {
        LinearLayout row = Ui.row(this);
        TextView l = Ui.text(this, 14, Ui.TEXT);
        l.setText(label);
        TextView v = Ui.number(this, 14, Ui.TEXT);
        v.setText(value + " %");
        v.setMinWidth(Ui.dp(this, 44));
        android.widget.SeekBar sb = new android.widget.SeekBar(this);
        sb.setMax(max - min);
        sb.setProgress(Math.max(0, Math.min(max, value) - min));
        sb.setOnSeekBarChangeListener(new android.widget.SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(android.widget.SeekBar s, int p, boolean user) {
                v.setText((p + min) + " %");
                if (user) onChange.accept(p + min);
            }
            @Override public void onStartTrackingTouch(android.widget.SeekBar s) { }
            @Override public void onStopTrackingTouch(android.widget.SeekBar s) { }
        });
        row.addView(l, new LinearLayout.LayoutParams(Ui.dp(this, 150), -2));
        row.addView(sb, new LinearLayout.LayoutParams(0, -2, 1f));
        row.addView(v);
        row.setPadding(0, Ui.dp(this, 4), 0, Ui.dp(this, 4));
        return row;
    }

    private View choice(String label, List<String> options, int selected, java.util.function.IntConsumer onChange) {
        LinearLayout row = Ui.row(this);
        TextView l = Ui.text(this, 14, Ui.TEXT);
        l.setText(label);
        android.widget.Spinner sp = new android.widget.Spinner(this);
        android.widget.ArrayAdapter<String> ad = new android.widget.ArrayAdapter<>(this,
                android.R.layout.simple_spinner_item, options);
        ad.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        sp.setAdapter(ad);
        sp.setSelection(Math.min(selected, options.size() - 1), false);
        sp.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(android.widget.AdapterView<?> p, View view, int pos, long id) {
                onChange.accept(pos);
            }
            @Override public void onNothingSelected(android.widget.AdapterView<?> p) { }
        });
        row.addView(l, new LinearLayout.LayoutParams(Ui.dp(this, 150), -2));
        row.addView(sp, new LinearLayout.LayoutParams(0, -2, 1f));
        row.setPadding(0, Ui.dp(this, 4), 0, Ui.dp(this, 4));
        return row;
    }

    private TextView readout(GridLayout grid, String label) {
        LinearLayout cell = Ui.column(this);
        cell.setPadding(Ui.dp(this, 8), Ui.dp(this, 4), Ui.dp(this, 8), Ui.dp(this, 4));
        TextView l = Ui.text(this, 11, Ui.MUTED);
        l.setText(label);
        TextView v = Ui.number(this, 16, Ui.TEXT);
        cell.addView(l);
        cell.addView(v);
        GridLayout.LayoutParams lp = new GridLayout.LayoutParams(GridLayout.spec(GridLayout.UNDEFINED),
                GridLayout.spec(GridLayout.UNDEFINED, 1f));
        lp.width = 0;
        grid.addView(cell, lp);
        return v;
    }

    private Button smallButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(14);
        b.setTextColor(Ui.TEXT);
        b.setMinHeight(0);
        b.setMinimumHeight(0);
        b.setPadding(Ui.dp(this, 12), Ui.dp(this, 6), Ui.dp(this, 12), Ui.dp(this, 6));
        b.setBackground(Ui.rounded(Ui.PANEL, Ui.LINE, 8, this));
        b.setFocusable(false);   // el mando no debe mover el foco por la barra
        return b;
    }

    private View divider() {
        View v = new View(this);
        v.setBackgroundColor(Ui.LINE);
        v.setLayoutParams(new LinearLayout.LayoutParams(-1, Ui.dp(this, 1)));
        return v;
    }

    private void setDebug(boolean on) {
        debug = on;
        prefs.edit().putBoolean("debug", on).apply();
        game.setDebug(on);
        debugBtn.setTextColor(on ? Ui.CYAN : Ui.TEXT);
        debugBtn.setBackground(Ui.rounded(Ui.PANEL, on ? Ui.CYAN : Ui.LINE, 8, this));
    }

    private void setConnected(boolean on, String reason) {
        if (dot == null) return;
        dot.setBackground(Ui.rounded(on ? Ui.OK : Ui.BAD, 0, 5, this));
        if (!on) Ui.set(conn, reason == null ? "Sin conexión" : "Desconectado: " + reason);
        updateGuide();
    }

    private void loadPortrait(String url, Consumer<Bitmap> done) {
        Bitmap cached = portraitCache.get(url);
        if (cached != null) {
            done.accept(cached);
            return;
        }
        String h = host, c = cookie;
        int p = port, target = Ui.dp(this, 46) * 2;
        io.execute(() -> {
            Bitmap bmp = null;
            try {
                byte[] data = Api.get(h, p, url, c);
                BitmapFactory.Options o = new BitmapFactory.Options();
                o.inJustDecodeBounds = true;
                BitmapFactory.decodeByteArray(data, 0, data.length, o);
                int sample = 1;
                while (Math.min(o.outWidth, o.outHeight) / (sample * 2) >= target) sample *= 2;
                BitmapFactory.Options d = new BitmapFactory.Options();
                d.inSampleSize = sample;
                bmp = BitmapFactory.decodeByteArray(data, 0, data.length, d);
            } catch (Exception ignored) { }
            Bitmap result = bmp;
            ui.post(() -> {
                if (result != null) portraitCache.put(url, result);
                done.accept(result);
            });
        });
    }

    @SuppressWarnings("deprecation")
    private void immersive() {
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                c.hide(WindowInsets.Type.systemBars());
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        }
    }
}
