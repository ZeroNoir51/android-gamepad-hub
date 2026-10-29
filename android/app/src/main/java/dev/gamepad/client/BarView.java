package dev.gamepad.client;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.View;

/** Barra de progreso plana (HP/MP/Limit). Solo se redibuja si cambia la fracción. */
public final class BarView extends View {
    private final Paint track = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private float fraction = -1f;

    public BarView(Context c, int color) {
        super(c);
        track.setColor(Ui.PANEL);
        fill.setColor(color);
    }

    public void setFraction(float f) {
        f = Math.max(0f, Math.min(1f, f));
        if (Math.abs(f - fraction) < 0.002f) return;
        fraction = f;
        invalidate();
    }

    @Override protected void onDraw(Canvas canvas) {
        float r = getHeight() / 3f;
        rect.set(0, 0, getWidth(), getHeight());
        canvas.drawRoundRect(rect, r, r, track);
        if (fraction > 0) {
            rect.right = getWidth() * fraction;
            canvas.drawRoundRect(rect, r, r, fill);
        }
    }
}
