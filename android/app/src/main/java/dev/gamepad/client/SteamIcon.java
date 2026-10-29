package dev.gamepad.client;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;

/** Icono estilo Steam del botón Guide (el mismo dibujo que el SVG de la web), en dos colores. */
final class SteamIcon extends Drawable {
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ring = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path clip = new Path();
    private final Path tail = new Path();
    private int fg, bg;

    SteamIcon(int fg, int bg) {
        ring.setStyle(Paint.Style.STROKE);
        setColors(fg, bg);
    }

    /** fg: círculo y anillos; bg: piezas interiores (el color del botón). */
    void setColors(int fg, int bg) {
        if (fg == this.fg && bg == this.bg) return;
        this.fg = fg;
        this.bg = bg;
        invalidateSelf();
    }

    @Override public void draw(Canvas c) {
        Rect b = getBounds();
        float s = Math.min(b.width(), b.height()) / 100f;
        c.save();
        c.translate(b.left + (b.width() - 100 * s) / 2f, b.top + (b.height() - 100 * s) / 2f);
        c.scale(s, s);
        fill.setColor(fg);
        c.drawCircle(50, 50, 47, fill);
        clip.reset();
        clip.addCircle(50, 50, 47, Path.Direction.CW);
        c.save();
        c.clipPath(clip);
        fill.setColor(bg);
        tail.reset();
        tail.moveTo(0, 44);
        tail.lineTo(36, 59);
        tail.lineTo(31, 72);
        tail.lineTo(0, 58);
        tail.close();
        c.drawPath(tail, fill);
        ring.setColor(bg);
        ring.setStrokeWidth(15);
        ring.setStrokeCap(Paint.Cap.ROUND);
        c.drawLine(36, 64, 64, 37, ring);
        c.drawCircle(64, 37, 17, fill);
        c.drawCircle(36, 64, 12, fill);
        c.restore();
        ring.setColor(fg);
        ring.setStrokeWidth(4);
        c.drawCircle(64, 37, 10, ring);
        ring.setStrokeWidth(3.5f);
        c.drawCircle(36, 64, 6.5f, ring);
        c.restore();
    }

    @Override public void setAlpha(int alpha) { fill.setAlpha(alpha); ring.setAlpha(alpha); }

    @Override public void setColorFilter(ColorFilter cf) { fill.setColorFilter(cf); ring.setColorFilter(cf); }

    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
}
