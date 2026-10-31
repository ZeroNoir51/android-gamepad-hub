package dev.gamepad.client;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.DashPathEffect;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.view.View;

/** Número dentro de un engranaje (campos kind "gear", p. ej. la Brave Gauge de Trails). */
final class GearView extends View {
    private final Paint teeth = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint rim = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint core = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint outline = new Paint(Paint.ANTI_ALIAS_FLAG);
    private String value = "—";

    GearView(Context c) {
        super(c);
        teeth.setStyle(Paint.Style.STROKE);
        teeth.setColor(0xFF3A302A);
        rim.setStyle(Paint.Style.STROKE);
        core.setColor(0xFF17141A);
        for (Paint p : new Paint[] {text, outline}) {
            p.setTextAlign(Paint.Align.CENTER);
            p.setTypeface(Typeface.create(Ui.CONDENSED, Typeface.BOLD_ITALIC));
        }
        text.setColor(0xFFFF5A36);
        outline.setStyle(Paint.Style.STROKE);
        outline.setColor(0xFFFFF2E0);
        outline.setStrokeJoin(Paint.Join.ROUND);
    }

    void setText(String s) {
        if (s.equals(value)) return;
        value = s;
        invalidate();
    }

    @Override protected void onSizeChanged(int w, int h, int ow, int oh) {
        float u = Math.min(w, h) / 100f;   // mismas medidas que el SVG de la web (viewBox 100)
        teeth.setStrokeWidth(12 * u);
        float circ = (float) (2 * Math.PI * 42 * u);
        teeth.setPathEffect(new DashPathEffect(new float[] {circ * 9.4f / 98.5f, circ * 6.3f / 98.5f}, 0));
        rim.setStrokeWidth(7 * u);
        rim.setShader(new LinearGradient(0, h / 2f - 34 * u, 0, h / 2f + 34 * u, 0xFFFFB04A, 0xFFC8501E,
                Shader.TileMode.CLAMP));
        text.setTextSize(36 * u);
        outline.setTextSize(36 * u);
        outline.setStrokeWidth(3 * u);
    }

    @Override protected void onDraw(Canvas canvas) {
        float cx = getWidth() / 2f, cy = getHeight() / 2f, u = Math.min(getWidth(), getHeight()) / 100f;
        canvas.drawCircle(cx, cy, 42 * u, teeth);
        canvas.drawCircle(cx, cy, 34 * u, rim);
        canvas.drawCircle(cx, cy, 29 * u, core);
        float y = cy - (text.descent() + text.ascent()) / 2;
        canvas.drawText(value, cx, y, outline);
        canvas.drawText(value, cx, y, text);
    }
}
