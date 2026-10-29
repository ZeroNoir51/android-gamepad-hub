package dev.gamepad.client;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Colores (los mismos que web/index.html) y pequeñas utilidades para construir vistas en código. */
final class Ui {
    static final int BG = 0xFF15171C, PANEL = 0xFF1D2027, LINE = 0xFF2B2F39, TEXT = 0xFFEBE7DD, MUTED = 0xFF8C919C;
    static final int AMBER = 0xFFFFB547, CYAN = 0xFF5FD0E0, BAD = 0xFFFF6B5B, OK = 0xFF7BD88F;
    static final int HP = 0xFFEF5B5B, MP = 0xFF5B8DEF, LIMIT = 0xFFF0A03C, GOLD = 0xFFE9C46A, XP = 0xFFA98BF0,
            NEUTRAL = 0xFFC9C5BB;
    static final Typeface CONDENSED = Typeface.create("sans-serif-condensed", Typeface.NORMAL);

    private Ui() {}

    static int tone(String name) {
        switch (name == null ? "" : name) {
            case "hp": return HP;
            case "mp": return MP;
            case "limit": return LIMIT;
            case "gold": return GOLD;
            case "xp": return XP;
            default: return NEUTRAL;
        }
    }

    static int dp(Context c, float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, c.getResources().getDisplayMetrics()));
    }

    static TextView text(Context c, float sp, int color) {
        TextView t = new TextView(c);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        t.setIncludeFontPadding(false);
        return t;
    }

    static TextView number(Context c, float sp, int color) {
        TextView t = text(c, sp, color);
        t.setTypeface(CONDENSED);
        t.setFontFeatureSettings("tnum");
        return t;
    }

    static GradientDrawable rounded(int fill, int stroke, float radiusDp, Context c) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(c, radiusDp));
        if (stroke != 0) g.setStroke(dp(c, 1), stroke);
        return g;
    }

    static LinearLayout row(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    static LinearLayout column(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    static View spacer(Context c) {
        View v = new View(c);
        v.setLayoutParams(new LinearLayout.LayoutParams(0, 1, 1f));
        return v;
    }

    /** Para setText sin provocar relayout si el texto no cambió. */
    static void set(TextView t, CharSequence s) {
        if (!s.toString().contentEquals(t.getText())) t.setText(s);
    }
}
