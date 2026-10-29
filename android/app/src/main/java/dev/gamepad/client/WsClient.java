package dev.gamepad.client;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Cliente WebSocket mínimo (RFC 6455) para /ws: texto, ping/pong y cierre. Sin dependencias ni Android.
 * Un hilo lee y otro escribe; send() no bloquea, así se puede llamar desde el hilo de la interfaz.
 */
public final class WsClient {
    public interface Listener {
        void onOpen();
        void onText(String text);
        /** Una sola vez. httpStatus != 0 si el servidor rechazó la conexión (403 sin sesión, 409 ocupado). */
        void onClose(String reason, int httpStatus);
    }

    private static final String GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    private static final byte[] POISON = new byte[0];
    private static final int MAX_MESSAGE = 1 << 20;

    private final String host;
    private final int port;
    private final String cookie;
    private final Listener listener;
    private final LinkedBlockingQueue<byte[]> queue = new LinkedBlockingQueue<>();
    private final AtomicBoolean closed = new AtomicBoolean();
    private final AtomicBoolean reported = new AtomicBoolean();
    private final SecureRandom random = new SecureRandom();
    private volatile Socket socket;
    private volatile boolean open;

    public WsClient(String host, int port, String cookie, Listener listener) {
        this.host = host;
        this.port = port;
        this.cookie = cookie;
        this.listener = listener;
    }

    public void start() {
        Thread t = new Thread(this::run, "ws-read");
        t.setDaemon(true);
        t.start();
    }

    public boolean isOpen() {
        return open && !closed.get();
    }

    public void send(String text) {
        if (isOpen()) queue.offer(frame(0x1, text.getBytes(StandardCharsets.UTF_8)));
    }

    public void close() {
        if (closed.getAndSet(true)) return;
        open = false;
        if (isSocketUsable()) queue.offer(frame(0x8, new byte[] {0x03, (byte) 0xE8}));   // 1000: normal
        queue.offer(POISON);
        Socket s = socket;
        if (s != null) {
            new Thread(() -> {   // dar tiempo a que salga el frame de cierre sin bloquear al llamador
                try { Thread.sleep(200); s.close(); } catch (Exception ignored) { }
            }).start();
        }
    }

    private boolean isSocketUsable() {
        Socket s = socket;
        return s != null && s.isConnected() && !s.isClosed();
    }

    private void run() {
        String reason = "conexión cerrada";
        int status = 0;
        try {
            Socket s = new Socket();
            socket = s;
            s.connect(new InetSocketAddress(host, port), 5000);
            s.setTcpNoDelay(true);
            s.setSoTimeout(20000);   // el servidor manda ping cada 5 s: 20 s sin nada = conexión muerta
            InputStream in = new BufferedInputStream(s.getInputStream());
            OutputStream out = s.getOutputStream();
            status = handshake(in, out);
            if (status != 101) throw new IOException(status == 403 ? "sin sesión" :
                    status == 409 ? "ya hay otro cliente conectado" : "el servidor respondió " + status);
            status = 0;
            Thread writer = new Thread(() -> writeLoop(out), "ws-write");
            writer.setDaemon(true);
            writer.start();
            open = true;
            listener.onOpen();
            readLoop(in);
        } catch (IOException e) {
            if (!closed.get() && e.getMessage() != null) reason = e.getMessage();
        } finally {
            open = false;
            closed.set(true);
            queue.offer(POISON);
            try { Socket s = socket; if (s != null) s.close(); } catch (IOException ignored) { }
            if (!reported.getAndSet(true)) listener.onClose(reason, status);
        }
    }

    private int handshake(InputStream in, OutputStream out) throws IOException {
        byte[] nonce = new byte[16];
        random.nextBytes(nonce);
        String key = Base64.getEncoder().encodeToString(nonce);
        StringBuilder req = new StringBuilder()
                .append("GET /ws HTTP/1.1\r\n")
                .append("Host: ").append(host).append(':').append(port).append("\r\n")
                .append("Upgrade: websocket\r\nConnection: Upgrade\r\n")
                .append("Sec-WebSocket-Key: ").append(key).append("\r\n")
                .append("Sec-WebSocket-Version: 13\r\n");
        if (cookie != null) req.append("Cookie: ").append(Api.COOKIE).append('=').append(cookie).append("\r\n");
        out.write(req.append("\r\n").toString().getBytes(StandardCharsets.US_ASCII));
        out.flush();
        String statusLine = readLine(in);
        String[] parts = statusLine.split(" ");
        int status = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
        String accept = null;
        for (String line; !(line = readLine(in)).isEmpty(); ) {
            int i = line.indexOf(':');
            if (i > 0 && line.substring(0, i).trim().equalsIgnoreCase("Sec-WebSocket-Accept")) {
                accept = line.substring(i + 1).trim();
            }
        }
        if (status == 101 && !expectedAccept(key).equals(accept)) throw new IOException("handshake inválido");
        return status;
    }

    static String expectedAccept(String key) {
        try {
            byte[] sha = MessageDigest.getInstance("SHA-1").digest((key + GUID).getBytes(StandardCharsets.US_ASCII));
            return Base64.getEncoder().encodeToString(sha);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static String readLine(InputStream in) throws IOException {
        StringBuilder sb = new StringBuilder();
        for (int c; (c = in.read()) != '\n'; ) {
            if (c < 0) throw new EOFException("cabecera incompleta");
            if (c != '\r') sb.append((char) c);
            if (sb.length() > 8192) throw new IOException("cabecera demasiado larga");
        }
        return sb.toString();
    }

    private void readLoop(InputStream in) throws IOException {
        ByteArrayOutputStream message = new ByteArrayOutputStream();
        while (!closed.get()) {
            int b0 = readByte(in), b1 = readByte(in);
            boolean fin = (b0 & 0x80) != 0;
            int op = b0 & 0x0F;
            long len = b1 & 0x7F;
            if (len == 126) len = (readByte(in) << 8) | readByte(in);
            else if (len == 127) {
                len = 0;
                for (int i = 0; i < 8; i++) len = (len << 8) | readByte(in);
            }
            if (len > MAX_MESSAGE) throw new IOException("mensaje demasiado grande");
            byte[] mask = null;
            if ((b1 & 0x80) != 0) {
                mask = new byte[4];
                readFully(in, mask);
            }
            byte[] payload = new byte[(int) len];
            readFully(in, payload);
            if (mask != null) for (int i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];
            switch (op) {
                case 0x0: case 0x1:
                    message.write(payload);
                    if (message.size() > MAX_MESSAGE) throw new IOException("mensaje demasiado grande");
                    if (fin) {
                        listener.onText(message.toString("UTF-8"));
                        message.reset();
                    }
                    break;
                case 0x8:
                    queue.offer(frame(0x8, payload.length >= 2 ? new byte[] {payload[0], payload[1]} : new byte[0]));
                    return;
                case 0x9:
                    queue.offer(frame(0xA, payload));   // pong con el mismo contenido
                    break;
                default:
                    break;   // pong o binario: se ignoran
            }
        }
    }

    private void writeLoop(OutputStream out) {
        try {
            while (true) {
                byte[] f = queue.take();
                if (f == POISON) break;
                out.write(f);
                out.flush();
            }
        } catch (IOException | InterruptedException e) {
            Socket s = socket;
            try { if (s != null) s.close(); } catch (IOException ignored) { }
        }
    }

    private byte[] frame(int op, byte[] payload) {
        int n = payload.length;
        int header = n < 126 ? 2 : (n < 65536 ? 4 : 10);
        byte[] f = new byte[header + 4 + n];
        f[0] = (byte) (0x80 | op);
        if (n < 126) {
            f[1] = (byte) (0x80 | n);
        } else if (n < 65536) {
            f[1] = (byte) (0x80 | 126);
            f[2] = (byte) (n >> 8);
            f[3] = (byte) n;
        } else {
            f[1] = (byte) (0x80 | 127);
            for (int i = 0; i < 8; i++) f[2 + i] = (byte) ((long) n >> (56 - 8 * i));
        }
        byte[] mask = new byte[4];
        random.nextBytes(mask);   // el cliente siempre enmascara (RFC 6455)
        System.arraycopy(mask, 0, f, header, 4);
        for (int i = 0; i < n; i++) f[header + 4 + i] = (byte) (payload[i] ^ mask[i & 3]);
        return f;
    }

    private static int readByte(InputStream in) throws IOException {
        int b = in.read();
        if (b < 0) throw new EOFException("conexión cerrada por el servidor");
        return b;
    }

    private static void readFully(InputStream in, byte[] buf) throws IOException {
        for (int off = 0; off < buf.length; ) {
            int n = in.read(buf, off, buf.length - off);
            if (n < 0) throw new EOFException("conexión cerrada por el servidor");
            off += n;
        }
    }
}
