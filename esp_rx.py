# espnow_rx.py - ESP-NOW throughput benchmark (receiver)
# Start this first, then start espnow_tx.py on the other board.
import network, espnow, struct, time

CHANNEL   = 1      # must match TX
TXPOWER   = 2      # only matters if TX uses unicast (ACKs)
REPORT_MS = 1000

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
sta.config(channel=CHANNEL)
try:
    sta.config(txpower=TXPOWER)
except Exception:
    pass

e = espnow.ESPNow()
e.active(True)
e.config(rxbuf=8192)

print("RX MAC:", ":".join("%02x" % b for b in sta.config('mac')))
print("Listening on channel", CHANNEL)

unpack = struct.unpack_from
irecv = e.irecv
ticks_ms = time.ticks_ms
ticks_diff = time.ticks_diff

last_seq = -1
pk = by = lost = 0
total_pk = total_by = total_lost = 0
last_drop = 0
t0 = t_rep = None

try:
    while True:
        # non-blocking poll: drain the ring buffer as fast as possible
        mac, msg = irecv(0)
        if msg is not None:
            now = ticks_ms()
            if t0 is None:
                t0 = t_rep = now      # clock starts at first packet
            seq = unpack('<I', msg, 0)[0]
            if last_seq >= 0 and seq > last_seq + 1:
                lost += seq - last_seq - 1
            last_seq = seq
            pk += 1
            by += len(msg)
        else:
            now = ticks_ms()

        if t_rep is not None:
            dt = ticks_diff(now, t_rep)
            if dt >= REPORT_MS:
                drop = e.stats()[4]
                tot = pk + lost
                print("RX %7.2f KB/s (%6.1f kbit/s) | %5d pkt/s | lost %d (%.1f%%) | buf-drop/s %d" % (
                    by / 1024 / (dt / 1000),
                    by * 8 / dt,
                    pk * 1000 // dt,
                    lost,
                    100 * lost / tot if tot else 0,
                    drop - last_drop))
                last_drop = drop
                total_pk += pk; total_by += by; total_lost += lost
                pk = by = lost = 0
                t_rep = now
except KeyboardInterrupt:
    if t0 is not None:
        el = ticks_diff(ticks_ms(), t0) / 1000
        print("\nDone. avg %.2f KB/s over %.1fs, %d pkts, %d lost" % (
            total_by / 1024 / el, el, total_pk, total_lost))
