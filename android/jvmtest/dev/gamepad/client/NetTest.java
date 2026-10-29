package dev.gamepad.client;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Prueba de Api + WsClient + PadState contra el servicio real (`gamepad serve --pad null`).
 *  Uso: java NetTest host port codigo  (lo lanza android/jvmtest/run.sh). */
public final class NetTest {
    static void check(boolean ok, String what) {
        if (!ok) throw new AssertionError(what);
        System.out.println("OK  " + what);
    }

    public static void main(String[] a) throws Exception {
        String host = a[0]; int port = Integer.parseInt(a[1]); String code = a[2];
        try { Api.login(host, port, "ZZZZ".equals(code) ? "AAAA" : "ZZZZ"); check(false, "código malo rechazado"); }
        catch (java.io.IOException e) { check(e.getMessage().equals("Código incorrecto."), "código malo rechazado: " + e.getMessage()); }
        String cookie = Api.login(host, port, code);
        check(cookie != null && cookie.length() > 20, "login devuelve cookie");
        check(Api.sessionValid(host, port, cookie), "sesión válida");
        check(!Api.sessionValid(host, port, "falsa"), "cookie falsa no vale");

        // Sin sesión: el handshake devuelve 403
        AtomicReference<Integer> denied = new AtomicReference<>();
        CountDownLatch d = new CountDownLatch(1);
        new WsClient(host, port, null, new WsClient.Listener() {
            public void onOpen() {}
            public void onText(String t) {}
            public void onClose(String r, int s) { denied.set(s); d.countDown(); }
        }).start();
        d.await(5, TimeUnit.SECONDS);
        check(Integer.valueOf(403).equals(denied.get()), "WebSocket sin sesión: 403");

        CountDownLatch hello = new CountDownLatch(1), pong = new CountDownLatch(1), tel = new CountDownLatch(1);
        AtomicReference<String> last = new AtomicReference<>();
        WsClient[] ws = new WsClient[1];
        ws[0] = new WsClient(host, port, cookie, new WsClient.Listener() {
            public void onOpen() {}
            public void onText(String t) {
                last.set(t);
                if (t.contains("\"t\":\"hello\"")) hello.countDown();
                if (t.matches(".*\"t\":\\s*\"pong\".*") && t.matches(".*\"id\":\\s*7\\b.*")) pong.countDown();
                if (t.contains("\"t\":\"tel\"")) tel.countDown();
            }
            public void onClose(String r, int s) { System.out.println("cerrado: " + r); }
        });
        ws[0].start();
        check(hello.await(5, TimeUnit.SECONDS), "hello recibido");
        PadState p = new PadState();
        p.set(PadState.A, 1); p.set(PadState.LX, PadState.stick(-1f)); p.set(PadState.RT, PadState.trigger(1f));
        ws[0].send(p.toMessage());
        ws[0].send("{\"t\":\"ping\",\"id\":7,\"ct\":1}");
        check(pong.await(5, TimeUnit.SECONDS), "ping -> pong");
        check(tel.await(5, TimeUnit.SECONDS), "telemetría recibida");
        // Mensaje grande (> 125 y > 65535 bytes no aplica: el servidor limita a 8 KB), probamos 126..65535
        StringBuilder big = new StringBuilder("{\"t\":\"ping\",\"id\":8,\"ct\":\"");
        for (int i = 0; i < 300; i++) big.append('x');
        ws[0].send(big.append("\"}").toString());
        Thread.sleep(500);
        check(ws[0].isOpen(), "frame de 300 bytes aceptado");
        // Segundo cliente mientras hay uno: 409
        AtomicReference<Integer> busy = new AtomicReference<>();
        CountDownLatch b = new CountDownLatch(1);
        new WsClient(host, port, cookie, new WsClient.Listener() {
            public void onOpen() {}
            public void onText(String t) {}
            public void onClose(String r, int s) { busy.set(s); b.countDown(); }
        }).start();
        b.await(5, TimeUnit.SECONDS);
        check(Integer.valueOf(409).equals(busy.get()), "segundo cliente: 409");
        ws[0].close();
        Thread.sleep(500);
        check(!ws[0].isOpen(), "cierre limpio");
        System.out.println("TODO OK");
    }
}
