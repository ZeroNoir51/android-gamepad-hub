package dev.gamepad.client;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Outline;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.text.style.RelativeSizeSpan;
import android.view.Gravity;
import android.view.View;
import android.view.ViewOutlineProvider;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/** Panel del plugin: lo construye a partir de los campos del mensaje "game" y lo rellena con "gv". */
final class GamePanel {
    interface PortraitLoader {
        /** Carga la URL (ya validada) y llama a done en el hilo de la interfaz; null si falla. */
        void load(String url, java.util.function.Consumer<Bitmap> done);
    }

    private static final Pattern PORTRAIT = Pattern.compile("^/portraits/[a-z0-9_]+/[A-Za-z0-9_-]+\\.(png|jpe?g|webp)$");

    final LinearLayout view;
    private final Context c;
    private final PortraitLoader portraits;
    private final TextView title, sub, error, empty;
    private final LinearLayout party, stats, info;
    private final List<Binding> bindings = new ArrayList<>();
    private final Map<String, String> header = new LinkedHashMap<>();
    private String pidText = "";
    private final List<View> cards = new ArrayList<>();
    private int columns = 2;
    private boolean statsFirst;
    String pluginId, pluginName;
    private final NumberFormat nf = NumberFormat.getIntegerInstance(new Locale("es"));
    private boolean debug;

    private static final class Binding {
        String key, kind, section, maxKey, label;
        View card;            // tarjeta (party)
        View row;             // fila que se oculta si no hay dato
        TextView text, initial;
        BarView bar;
        ImageView image;
        String imageUrl;
        boolean isName;
    }

    GamePanel(Context c, PortraitLoader portraits) {
        this.c = c;
        this.portraits = portraits;
        view = Ui.column(c);
        int pad = Ui.dp(c, 14);
        view.setPadding(pad, Ui.dp(c, 10), pad, pad);
        title = Ui.text(c, 19, Ui.TEXT);
        title.setTypeface(null, android.graphics.Typeface.BOLD);
        sub = Ui.text(c, 13, Ui.MUTED);
        sub.setPadding(0, Ui.dp(c, 3), 0, Ui.dp(c, 8));
        party = Ui.column(c);
        stats = Ui.row(c);
        stats.setPadding(0, Ui.dp(c, 6), 0, 0);
        info = Ui.column(c);
        info.setPadding(0, Ui.dp(c, 8), 0, 0);
        error = Ui.text(c, 13, Ui.BAD);
        empty = Ui.text(c, 14, Ui.MUTED);
        empty.setText("Abre un juego que tenga plugin y aquí aparecerán sus datos.");
        for (View v : new View[] {title, sub, party, stats, info, error, empty}) view.addView(v);
        clear();
    }

    void setDebug(boolean on) {
        debug = on;
        info.setVisibility(on && info.getChildCount() > 0 ? View.VISIBLE : View.GONE);
    }

    void clear() {
        bindings.clear();
        cards.clear();
        pluginId = null;
        pluginName = null;
        header.clear();
        party.removeAllViews();
        stats.removeAllViews();
        info.removeAllViews();
        title.setText("Sin juego detectado");
        sub.setText("");
        error.setText("");
        empty.setVisibility(View.VISIBLE);
        setDebug(debug);
    }

    void setMeta(JSONObject m) {
        clear();
        if (!"attached".equals(m.optString("state"))) return;
        empty.setVisibility(View.GONE);
        title.setText(m.optString("name"));
        String id = m.optString("id", "");
        pluginId = id.matches("[a-z0-9_]+") ? id : null;
        pluginName = m.optString("name");
        pidText = "PID " + m.optInt("pid");
        JSONArray fields = m.optJSONArray("fields");
        Map<Integer, LinearLayout> bySlot = new LinkedHashMap<>();
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject f = fields.optJSONObject(i);
            if (f == null) continue;
            Binding b = new Binding();
            b.key = f.optString("key");
            b.kind = f.optString("kind", "number");
            b.section = f.optString("section", "stats");
            b.maxKey = f.optString("max_key", null);
            b.label = f.optString("label");
            int color = Ui.tone(f.optString("tone"));
            switch (b.section) {
                case "header":
                    header.put(b.key, "");
                    break;
                case "party": {
                    int slot = f.optInt("slot");
                    LinearLayout card = bySlot.get(slot);
                    if (card == null) {
                        card = newCard();
                        bySlot.put(slot, card);
                        cards.add(card);
                    }
                    b.card = card;
                    bindParty(b, card, color);
                    break;
                }
                case "info": {
                    LinearLayout r = Ui.row(c);
                    r.setGravity(Gravity.TOP);
                    TextView dt = Ui.text(c, 12.5f, Ui.MUTED);
                    dt.setText(b.label);
                    dt.setMinWidth(Ui.dp(c, 110));
                    b.text = Ui.text(c, 12.5f, Ui.TEXT);
                    b.text.setText("—");
                    r.addView(dt);
                    r.addView(b.text, new LinearLayout.LayoutParams(0, -2, 1f));
                    r.setPadding(0, Ui.dp(c, 2), 0, Ui.dp(c, 2));
                    info.addView(r);
                    break;
                }
                default: {   // stats: número grande o barra suelta
                    LinearLayout box = Ui.column(c);
                    TextView lab = Ui.text(c, 13, Ui.MUTED);
                    lab.setText(b.label);
                    b.text = Ui.number(c, 26, color);
                    b.text.setText("—");
                    box.addView(lab);
                    box.addView(b.text);
                    box.setPadding(0, 0, Ui.dp(c, 24), 0);
                    stats.addView(box);
                }
            }
            bindings.add(b);
        }
        arrangeParty();
        updateSub();
        setDebug(debug);
    }

    /** Columnas del equipo (1, 2 o 4). */
    void setColumns(int n) {
        n = n == 1 || n == 4 ? n : 2;
        if (n == columns) return;
        columns = n;
        arrangeParty();
    }

    /** Estadísticas (Gil…) antes que el equipo. */
    void setStatsFirst(boolean on) {
        if (on == statsFirst) return;
        statsFirst = on;
        view.removeView(stats);
        view.addView(stats, view.indexOfChild(on ? party : info));
        stats.setPadding(0, on ? 0 : Ui.dp(c, 6), 0, on ? Ui.dp(c, 10) : 0);
    }

    /** Reparte las tarjetas en filas de `columns`; la última fila se completa con huecos. */
    private void arrangeParty() {
        for (View card : cards) {
            if (card.getParent() != null) ((LinearLayout) card.getParent()).removeView(card);
        }
        party.removeAllViews();
        LinearLayout row = null;
        for (int i = 0; i < cards.size(); i++) {
            if (i % columns == 0) {
                row = Ui.row(c);
                row.setGravity(Gravity.TOP);
                party.addView(row);
            }
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, -2, 1f);
            lp.setMargins(0, 0, Ui.dp(c, i % columns == columns - 1 ? 0 : 14), Ui.dp(c, 12));
            row.addView(cards.get(i), lp);
        }
        int rest = cards.size() % columns;
        for (int i = rest; rest > 0 && i < columns; i++) row.addView(new View(c), new LinearLayout.LayoutParams(0, 1, 1f));
    }

    private LinearLayout newCard() {
        LinearLayout card = Ui.column(c);
        LinearLayout head = Ui.row(c);
        FrameLayout ava = new FrameLayout(c);
        int size = Ui.dp(c, 46);
        ava.setBackground(Ui.rounded(Ui.PANEL, Ui.LINE, 23, c));
        ava.setOutlineProvider(new ViewOutlineProvider() {
            @Override public void getOutline(View v, Outline o) { o.setOval(0, 0, v.getWidth(), v.getHeight()); }
        });
        ava.setClipToOutline(true);
        TextView ini = Ui.text(c, 20, Ui.MUTED);
        ini.setGravity(Gravity.CENTER);
        ava.addView(ini, new FrameLayout.LayoutParams(-1, -1));
        ImageView img = new ImageView(c);
        img.setScaleType(ImageView.ScaleType.CENTER_CROP);
        img.setVisibility(View.GONE);
        ava.addView(img, new FrameLayout.LayoutParams(-1, -1));
        head.addView(ava, new LinearLayout.LayoutParams(size, size));
        LinearLayout names = Ui.column(c);
        names.setPadding(Ui.dp(c, 10), 0, 0, 0);
        head.addView(names, new LinearLayout.LayoutParams(0, -2, 1f));
        card.addView(head);
        card.setTag(new Object[] {ini, img, names});
        return card;
    }

    private void bindParty(Binding b, LinearLayout card, int color) {
        Object[] parts = (Object[]) card.getTag();
        TextView ini = (TextView) parts[0];
        ImageView img = (ImageView) parts[1];
        LinearLayout names = (LinearLayout) parts[2];
        switch (b.kind) {
            case "image":
                b.image = img;
                break;
            case "text":
                boolean first = names.getChildCount() == 0;
                b.text = Ui.text(c, first ? 17 : 13, first ? Ui.TEXT : Ui.MUTED);
                if (first) {
                    b.text.setTypeface(null, android.graphics.Typeface.BOLD);
                    b.text.setText(b.label);
                    b.isName = true;
                    b.initial = ini;
                }
                b.text.setSingleLine(true);
                names.addView(b.text);
                break;
            default: {   // barra (o número) dentro de la tarjeta
                LinearLayout r = Ui.column(c);
                LinearLayout top = Ui.row(c);
                top.setGravity(Gravity.BOTTOM);
                TextView lab = Ui.text(c, 13.5f, Ui.MUTED);
                lab.setText(b.label);
                b.text = Ui.number(c, 18, Ui.TEXT);
                top.addView(lab);
                top.addView(Ui.spacer(c));
                top.addView(b.text);
                r.addView(top);
                if ("bar".equals(b.kind)) {
                    b.bar = new BarView(c, color);
                    LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, Ui.dp(c, 9));
                    lp.topMargin = Ui.dp(c, 3);
                    r.addView(b.bar, lp);
                }
                r.setPadding(0, Ui.dp(c, 6), 0, 0);
                b.row = r;
                card.addView(r);
            }
        }
    }

    void setValues(JSONObject m) {
        String err = m.optString("err", "");
        Ui.set(error, err.isEmpty() ? "" : "Error de lectura: " + err);
        JSONObject v = m.optJSONObject("v");
        if (v == null) return;
        boolean headerChanged = false;
        for (Binding b : bindings) {
            Object raw = v.isNull(b.key) ? null : v.opt(b.key);
            if ("header".equals(b.section)) {
                String s = raw == null ? "" : String.valueOf(raw);
                if (!s.equals(header.put(b.key, s))) headerChanged = true;
                continue;
            }
            if (b.isName) {
                b.card.setVisibility(raw == null ? View.GONE : View.VISIBLE);
                Ui.set(b.text, raw == null ? b.label : String.valueOf(raw));
                String name = raw == null ? "" : String.valueOf(raw).trim();
                Ui.set(b.initial, name.isEmpty() ? "" : name.substring(0, 1).toUpperCase(Locale.ROOT));
                continue;
            }
            if (b.image != null) {
                setPortrait(b, raw instanceof String ? (String) raw : null);
                continue;
            }
            if ("text".equals(b.kind)) {
                Ui.set(b.text, raw == null ? ("party".equals(b.section) ? "" : "—") : String.valueOf(raw));
                if ("party".equals(b.section)) b.text.setVisibility(raw == null ? View.GONE : View.VISIBLE);
                continue;
            }
            if (b.row != null) b.row.setVisibility(raw == null ? View.GONE : View.VISIBLE);
            if (raw == null) continue;
            if (b.bar != null) {
                double val = toDouble(raw);
                Object maxRaw = b.maxKey == null || v.isNull(b.maxKey) ? null : v.opt(b.maxKey);
                if (maxRaw != null) {
                    double max = toDouble(maxRaw);
                    SpannableStringBuilder s = new SpannableStringBuilder(fmt(raw));
                    int start = s.length();
                    s.append(" / ").append(fmt(maxRaw));
                    s.setSpan(new ForegroundColorSpan(Ui.MUTED), start, s.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                    s.setSpan(new RelativeSizeSpan(0.75f), start, s.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                    Ui.set(b.text, s);
                    b.bar.setFraction(max > 0 ? (float) (val / max) : 0f);
                } else {
                    Ui.set(b.text, fmt(raw));
                    b.bar.setFraction(0f);
                }
            } else {
                Ui.set(b.text, fmt(raw));
            }
        }
        if (headerChanged) updateSub();
    }

    private void setPortrait(Binding b, String url) {
        if (url == null || !PORTRAIT.matcher(url).matches()) {
            b.imageUrl = null;
            b.image.setVisibility(View.GONE);
            return;
        }
        if (url.equals(b.imageUrl)) return;
        b.imageUrl = url;
        portraits.load(url, bmp -> {
            if (!url.equals(b.imageUrl)) return;
            if (bmp == null) {
                b.image.setVisibility(View.GONE);
            } else {
                b.image.setImageBitmap(bmp);
                b.image.setVisibility(View.VISIBLE);
            }
        });
    }

    private void updateSub() {
        StringBuilder s = new StringBuilder(pidText);
        for (String h : header.values()) if (!h.isEmpty()) s.append(" · ").append(h);
        Ui.set(sub, s);
    }

    private static double toDouble(Object o) {
        return o instanceof Number ? ((Number) o).doubleValue() : 0;
    }

    private String fmt(Object o) {
        if (o instanceof Integer || o instanceof Long) return nf.format(((Number) o).longValue());
        if (o instanceof Number) {
            double d = ((Number) o).doubleValue();
            return d == Math.rint(d) ? nf.format((long) d) : String.format(Locale.ROOT, "%.1f", d);
        }
        return String.valueOf(o);
    }
}
