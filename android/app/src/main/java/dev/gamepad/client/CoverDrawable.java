package dev.gamepad.client;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;

/** Fondo del panel del juego: la imagen recortada para cubrir ("cover", centrada) y oscurecida. */
final class CoverDrawable extends Drawable {
    private final Bitmap bitmap;
    private final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG);
    private final Paint shade = new Paint();
    private final Rect src = new Rect();

    CoverDrawable(Bitmap bitmap, float dim) {
        this.bitmap = bitmap;
        shade.setColor(Ui.BG);
        shade.setAlpha(Math.round(Math.max(0f, Math.min(0.9f, dim)) * 255));
    }

    @Override protected void onBoundsChange(Rect b) {
        float scale = Math.max((float) b.width() / bitmap.getWidth(), (float) b.height() / bitmap.getHeight());
        int w = Math.round(b.width() / scale), h = Math.round(b.height() / scale);
        int x = (bitmap.getWidth() - w) / 2, y = (bitmap.getHeight() - h) / 2;
        src.set(x, y, x + w, y + h);
    }

    @Override public void draw(Canvas c) {
        c.drawColor(Ui.BG);
        c.drawBitmap(bitmap, src, getBounds(), paint);
        c.drawRect(getBounds(), shade);
    }

    @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); }

    @Override public void setColorFilter(ColorFilter cf) { paint.setColorFilter(cf); }

    @Override public int getOpacity() { return PixelFormat.OPAQUE; }
}
