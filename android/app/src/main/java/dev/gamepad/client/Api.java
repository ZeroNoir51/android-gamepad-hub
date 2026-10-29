package dev.gamepad.client;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** HTTP del servicio: login con el código, comprobar la sesión y descargar retratos. Sin Android. */
public final class Api {
    public static final String COOKIE = "gamepad_session";
    private static final Pattern MSG = Pattern.compile("\"msg\"\\s*:\\s*\"([^\"]*)\"");
    private static final Pattern OK_TRUE = Pattern.compile("\"ok\"\\s*:\\s*true");

    private Api() {}

    /** Devuelve el valor de la cookie de sesión, o lanza IOException con el mensaje del servidor. */
    public static String login(String host, int port, String code) throws IOException {
        HttpURLConnection c = open(host, port, "/api/login", null);
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/json");
        byte[] body = ("{\"token\":\"" + code.replaceAll("[^A-Za-z]", "") + "\"}").getBytes(StandardCharsets.UTF_8);
        try (OutputStream out = c.getOutputStream()) {
            out.write(body);
        }
        int status = c.getResponseCode();
        if (status != 200) {
            String text = read(c.getErrorStream());
            Matcher m = MSG.matcher(text);
            throw new IOException(m.find() ? unescape(m.group(1)) : "Error " + status);
        }
        for (Map.Entry<String, List<String>> h : c.getHeaderFields().entrySet()) {
            if (h.getKey() == null || !h.getKey().equalsIgnoreCase("Set-Cookie")) continue;
            for (String v : h.getValue()) {
                String first = v.split(";", 2)[0].trim();
                if (first.startsWith(COOKIE + "=")) return first.substring(COOKIE.length() + 1);
            }
        }
        throw new IOException("El servidor no devolvió la sesión");
    }

    /** true si la cookie sigue siendo válida; false si no; IOException si no hay conexión. */
    public static boolean sessionValid(String host, int port, String cookie) throws IOException {
        HttpURLConnection c = open(host, port, "/api/session", cookie);
        if (c.getResponseCode() != 200) return false;
        return OK_TRUE.matcher(read(c.getInputStream())).find();
    }

    /** GET de un recurso con la sesión (retratos). */
    public static byte[] get(String host, int port, String path, String cookie) throws IOException {
        HttpURLConnection c = open(host, port, path, cookie);
        if (c.getResponseCode() != 200) throw new IOException("HTTP " + c.getResponseCode());
        try (InputStream in = c.getInputStream()) {
            return readBytes(in, 4 << 20);
        }
    }

    /** El servidor manda JSON con los acentos escapados (\\u00f3). Sin regex: appendReplacement
     *  con StringBuilder no existe antes de Android 14. */
    static String unescape(String s) {
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (ch == '\\' && i + 5 < s.length() && s.charAt(i + 1) == 'u') {
                try {
                    sb.append((char) Integer.parseInt(s.substring(i + 2, i + 6), 16));
                    i += 5;
                    continue;
                } catch (NumberFormatException ignored) { }
            }
            sb.append(ch);
        }
        return sb.toString();
    }

    private static HttpURLConnection open(String host, int port, String path, String cookie) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL("http", host, port, path).openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(6000);
        c.setUseCaches(false);
        if (cookie != null) c.setRequestProperty("Cookie", COOKIE + "=" + cookie);
        return c;
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream s = in) {
            return new String(readBytes(s, 64 << 10), StandardCharsets.UTF_8);
        }
    }

    private static byte[] readBytes(InputStream in, int limit) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        for (int n; (n = in.read(buf)) > 0; ) {
            out.write(buf, 0, n);
            if (out.size() > limit) throw new IOException("respuesta demasiado grande");
        }
        return out.toByteArray();
    }
}
