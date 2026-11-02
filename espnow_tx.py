# espnow_tx.py - ESP-NOW throughput benchmark (sender)
# Run this on one board, espnow_rx.py on the other.
import network, espnow, struct, time

CHANNEL  = 1       # must match RX
RATE     = 0       # 0 = WIFI_PHY_RATE_1M_L (1 Mbps). 3 = 11M_L, 0x0B = 6M, 0x10 = MCS0
TXPOWER  = 2       # dBm (ESP32 range is about 2..20)
PAYLOAD  = 250     # ESP-NOW max payload (bytes)
PEER     = b'\xff\xff\xff\xff\xff\xff'   # broadcast; or put RX's MAC here for unicast+ACK
REPORT_MS = 1000

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
sta.config(channel=CHANNEL)
try:
    sta.config(txpower=TXPOWER)
    print("TX power set to", sta.config('txpower'), "dBm")
except Exception as ex:
    print("Could not set txpower:", ex)

e = espnow.ESPNow()
e.active(True)
try:
    e.config(rate=RATE)
    print("PHY rate code set:", RATE)
except Exception as ex:
    print("Could not set rate (old firmware?):", ex)
e.add_peer(PEER)

buf = bytearray(PAYLOAD)
for i in range(4, PAYLOAD):
    buf[i] = i & 0xFF

seq = 0
ok = fail = 0
ok_bytes = 0
total_ok = total_bytes = 0
t0 = t_rep = time.ticks_ms()
pack = struct.pack_into

print("TX started: %d-byte payloads, channel %d" % (PAYLOAD, CHANNEL))
try:
    while True:
        pack('<I', buf, 0, seq)
        # sync send: waits for the send callback, which paces us to the real air rate
        if e.send(PEER, buf, True):
            ok += 1
            ok_bytes += PAYLOAD
            seq += 1
        else:
            fail += 1

        now = time.ticks_ms()
        dt = time.ticks_diff(now, t_rep)
        if dt >= REPORT_MS:
            print("TX %7.2f KB/s (%6.1f kbit/s) | %5d pkt/s | fail %d" % (
                ok_bytes / 1024 / (dt / 1000),
                ok_bytes * 8 / dt,
                ok * 1000 // dt,
                fail))
            total_ok += ok
            total_bytes += ok_bytes
            ok = fail = ok_bytes = 0
            t_rep = now
except KeyboardInterrupt:
    el = time.ticks_diff(time.ticks_ms(), t0) / 1000
    print("\nDone. avg %.2f KB/s over %.1fs, %d packets" % (
        total_bytes / 1024 / el, el, total_ok))
