package dev.gamepad.client;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Shader;
import android.view.View;

/** Barra inclinada con degradado (tarjetas "anillo"). Solo se redibuja si cambia la fracción. */
final class SlantBarView extends View {
    private final Paint track = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint edge = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private int from = Ui.HP, to = Ui.HP;
    private float fraction = -1f;

    SlantBarView(Context c) {
        super(c);
        track.setColor(0x73000000);
        edge.setStyle(Paint.Style.STROKE);
        edge.setStrokeWidth(Ui.dp(c, 1));
        edge.setColor(0x2EFFFFFF);
    }

    /** Degradado de izquierda a derecha. */
    void setColors(int from, int to) {
        this.from = from;
        this.to = to;
        if (getWidth() > 0) onSizeChanged(getWidth(), getHeight(), 0, 0);
        invalidate();
    }

    void setFraction(float f) {
        f = Math.max(0f, Math.min(1f, f));
        if (Math.abs(f - fraction) < 0.002f) return;
        fraction = f;
        invalidate();
    }

    @Override protected void onSizeChanged(int w, int h, int ow, int oh) {
        fill.setShader(new LinearGradient(0, 0, w, 0, from, to, Shader.TileMode.CLAMP));
    }

    private void slant(float right) {
        float h = getHeight(), skew = h * 0.55f;
        path.reset();
        path.moveTo(skew, 0);
        path.lineTo(Math.max(skew, right), 0);
        path.lineTo(Math.max(0, right - skew), h);
        path.lineTo(0, h);
        path.close();
    }

    @Override protected void onDraw(Canvas canvas) {
        slant(getWidth());
        canvas.drawPath(path, track);
        if (fraction > 0) {
            slant(getWidth() * fraction);
            canvas.drawPath(path, fill);
        }
        slant(getWidth());
        canvas.drawPath(path, edge);
    }
}
