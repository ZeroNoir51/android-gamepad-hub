package dev.gamepad.client;

import android.content.Context;
import android.graphics.BlurMaskFilter;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.View;

/** Arco alrededor del retrato (CP en las tarjetas "anillo"). Empieza abajo y gira en sentido horario. */
final class RingView extends View {
    static final int GREEN = 0xFF7BDC5F;
    private final Paint back = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint arc = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint glow = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();
    private float fraction = -1f;

    RingView(Context c) {
        super(c);
        float w = Ui.dp(c, 6);
        for (Paint p : new Paint[] {back, arc, glow}) {
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(w);
            p.setStrokeCap(Paint.Cap.ROUND);
        }
        back.setColor(0x80000000);
        arc.setColor(GREEN);
        glow.setColor(0x997BDC5F);
        glow.setMaskFilter(new BlurMaskFilter(Ui.dp(c, 3), BlurMaskFilter.Blur.NORMAL));
        setLayerType(LAYER_TYPE_SOFTWARE, null);   // BlurMaskFilter necesita dibujo por software
    }

    void setFraction(float f) {
        f = Math.max(0f, Math.min(1f, f));
        if (Math.abs(f - fraction) < 0.002f) return;
        fraction = f;
        invalidate();
    }

    @Override protected void onDraw(Canvas canvas) {
        float inset = arc.getStrokeWidth() / 2 + Ui.dp(getContext(), 3);
        oval.set(inset, inset, getWidth() - inset, getHeight() - inset);
        canvas.drawOval(oval, back);
        if (fraction > 0) {
            float sweep = 360f * fraction;
            canvas.drawArc(oval, 90, sweep, false, glow);
            canvas.drawArc(oval, 90, sweep, false, arc);
        }
    }
}
