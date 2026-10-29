package dev.gamepad.client;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.DashPathEffect;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.View;

/** Frametimes recientes (ms) con líneas de 30 y 60 FPS. Se redibuja solo al llegar telemetría. */
public final class ChartView extends View {
    private static final int MAX = 240;
    private final float[] ring = new float[MAX];
    private int count, head;
    private final Paint line = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint guide = new Paint();
    private final Paint label = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();

    public ChartView(Context c) {
        super(c);
        float d = c.getResources().getDisplayMetrics().density;
        line.setColor(Ui.AMBER);
        line.setStyle(Paint.Style.STROKE);
        line.setStrokeWidth(1.6f * d);
        guide.setColor(Ui.LINE);
        guide.setStrokeWidth(d);
        guide.setPathEffect(new DashPathEffect(new float[] {3 * d, 4 * d}, 0));
        label.setColor(Ui.MUTED);
        label.setTextSize(11 * d);
    }

    public void add(float[] values) {
        for (float v : values) {
            ring[head] = v;
            head = (head + 1) % MAX;
            count = Math.min(MAX, count + 1);
        }
        invalidate();
    }

    public void clear() {
        if (count == 0) return;
        count = 0;
        invalidate();
    }

    @Override protected void onDraw(Canvas c) {
        int w = getWidth(), h = getHeight();
        float top = 40f;
        for (int i = 0; i < count; i++) top = Math.max(top, ring[(head - count + i + MAX) % MAX]);
        top *= 1.1f;
        float[][] guides = {{16.7f, 0}, {33.3f, 1}};
        for (float[] g : guides) {
            if (g[0] > top) continue;
            float y = h - g[0] / top * h;
            c.drawLine(0, y, w, y, guide);
            c.drawText(g[1] == 0 ? "60 fps" : "30 fps", 4, y - 4, label);
        }
        if (count < 2) return;
        float step = (float) w / (MAX - 1), x0 = w - (count - 1) * step;
        path.reset();
        for (int i = 0; i < count; i++) {
            float v = ring[(head - count + i + MAX) % MAX];
            float x = x0 + i * step, y = h - v / top * h;
            if (i == 0) path.moveTo(x, y); else path.lineTo(x, y);
        }
        c.drawPath(path, line);
    }
}
