package com.pulse.remote;

import android.app.Activity;
import android.content.Context;
import android.net.DhcpInfo;
import android.net.wifi.WifiManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;

public class NativeBridge {
    private static final int DISCOVERY_PORT = 48765;
    private static final String DISCOVERY_QUERY = "PULSE_DISCOVER?";
    private static final int WOL_REPEATS = 3;

    private final Activity activity;
    private final WebView webView;

    public NativeBridge(Activity activity, WebView webView) {
        this.activity = activity;
        this.webView = webView;
    }

    @JavascriptInterface
    public String platform() {
        return "android";
    }

    @JavascriptInterface
    public void wake(final String callbackId, final String mac, final String broadcast, final int port) {
        new Thread(() -> {
            JSONObject result;
            try {
                result = json("sent", sendMagicPacket(mac, broadcast, port));
            } catch (Exception error) {
                result = json("error", String.valueOf(error.getMessage()));
            }
            resolve(callbackId, result);
        }).start();
    }

    @JavascriptInterface
    public void discover(final String callbackId, final int timeoutMs) {
        new Thread(() -> {
            JSONObject result;
            try {
                result = json("servers", findServers(timeoutMs));
            } catch (Exception error) {
                result = json("error", String.valueOf(error.getMessage()));
            }
            resolve(callbackId, result);
        }).start();
    }

    private int sendMagicPacket(String mac, String broadcast, int port) throws Exception {
        byte[] macBytes = parseMac(mac);
        byte[] payload = new byte[6 + 16 * 6];
        for (int i = 0; i < 6; i++) {
            payload[i] = (byte) 0xFF;
        }
        for (int i = 0; i < 16; i++) {
            System.arraycopy(macBytes, 0, payload, 6 + i * 6, 6);
        }

        Set<String> targets = new LinkedHashSet<>();
        if (broadcast != null && !broadcast.trim().isEmpty()) {
            targets.add(broadcast.trim());
        }
        String wifi = wifiBroadcast();
        if (wifi != null) {
            targets.add(wifi);
        }
        targets.add("255.255.255.255");

        int sent = 0;
        DatagramSocket socket = new DatagramSocket();
        try {
            socket.setBroadcast(true);
            for (String target : targets) {
                InetAddress address;
                try {
                    address = InetAddress.getByName(target);
                } catch (Exception ignored) {
                    continue;
                }
                for (int i = 0; i < WOL_REPEATS; i++) {
                    try {
                        socket.send(new DatagramPacket(payload, payload.length, address, port));
                        sent++;
                    } catch (Exception ignored) {
                    }
                }
            }
        } finally {
            socket.close();
        }
        if (sent == 0) {
            throw new Exception("Не удалось отправить пакет: проверьте подключение к Wi-Fi");
        }
        return sent;
    }

    private JSONArray findServers(int timeoutMs) throws Exception {
        JSONArray servers = new JSONArray();
        Set<String> seen = new HashSet<>();
        byte[] query = DISCOVERY_QUERY.getBytes(StandardCharsets.UTF_8);

        Set<String> targets = new LinkedHashSet<>();
        targets.add("255.255.255.255");
        String wifi = wifiBroadcast();
        if (wifi != null) {
            targets.add(wifi);
        }

        DatagramSocket socket = new DatagramSocket();
        try {
            socket.setBroadcast(true);
            socket.setSoTimeout(250);
            for (String target : targets) {
                try {
                    socket.send(new DatagramPacket(query, query.length, InetAddress.getByName(target), DISCOVERY_PORT));
                } catch (Exception ignored) {
                }
            }
            long deadline = System.currentTimeMillis() + Math.max(500, timeoutMs);
            byte[] buffer = new byte[4096];
            while (System.currentTimeMillis() < deadline) {
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                try {
                    socket.receive(packet);
                } catch (SocketTimeoutException timeout) {
                    continue;
                }
                try {
                    String address = packet.getAddress().getHostAddress();
                    JSONObject reply = new JSONObject(
                            new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8));
                    if (!"pulse".equals(reply.optString("app"))) {
                        continue;
                    }
                    String key = address + ":" + reply.optInt("port", 8765);
                    if (seen.add(key)) {
                        reply.put("address", address);
                        servers.put(reply);
                    }
                } catch (Exception ignored) {
                }
            }
        } finally {
            socket.close();
        }
        return servers;
    }

    private String wifiBroadcast() {
        try {
            WifiManager wifi = (WifiManager) activity.getApplicationContext()
                    .getSystemService(Context.WIFI_SERVICE);
            DhcpInfo dhcp = wifi.getDhcpInfo();
            if (dhcp == null || dhcp.ipAddress == 0) {
                return null;
            }
            int broadcast = (dhcp.ipAddress & dhcp.netmask) | ~dhcp.netmask;
            byte[] quads = new byte[4];
            for (int k = 0; k < 4; k++) {
                quads[k] = (byte) ((broadcast >> (k * 8)) & 0xFF);
            }
            return InetAddress.getByAddress(quads).getHostAddress();
        } catch (Exception error) {
            return null;
        }
    }

    private static byte[] parseMac(String mac) {
        String hex = mac == null ? "" : mac.replaceAll("[^0-9A-Fa-f]", "");
        if (hex.length() != 12) {
            throw new IllegalArgumentException("Неверный MAC-адрес");
        }
        byte[] bytes = new byte[6];
        for (int i = 0; i < 6; i++) {
            bytes[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        }
        return bytes;
    }

    private static JSONObject json(String key, Object value) {
        JSONObject object = new JSONObject();
        try {
            object.put(key, value);
        } catch (JSONException ignored) {
        }
        return object;
    }

    private void resolve(final String callbackId, final JSONObject payload) {
        final String script = "window.PulseNativeResolve(" + JSONObject.quote(callbackId) + ","
                + payload.toString() + ")";
        activity.runOnUiThread(() -> webView.evaluateJavascript(script, null));
    }
}
