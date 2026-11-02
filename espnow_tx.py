# espnow_tx.py - ESP-NOW throughput benchmark (sender)
# Start espnow_rx.py on the other board first, then run this.
#
# One (rate, size) combination  -> runs until Ctrl-C and prints a live line every second.
# Several rates and/or sizes    -> sweep: runs each combination for STEP_S seconds.
#
# Every frame starts with an 8-byte header that espnow_rx.py uses to count what
# really arrived: magic(1) step(1) rate(1) flags(1) size(2) seq(4), little endian.
# The rest of the payload is the byte pattern (index & 0xFF).
# After each step, TX sends a few END frames carrying the number of frames it attempted.
import network, espnow, struct, time

CHANNEL   = 1       # must match RX
TXPOWER   = 2       # dBm (ESP32 range is about 2..20)
PEER      = b'\xff\xff\xff\xff\xff\xff'   # broadcast; or put RX's MAC here for unicast+ACK
SIZES     = [250]   # payload sizes in bytes, 16..espnow.MAX_DATA_LEN (250 on v1, 1470 on v2)
RATES     = [0]     # PHY rate codes: 0 = 1M_L, 1 = 2M_L, 3 = 11M_L, 0x0B = 6M, 0x10 = MCS0
STEP_S    = 5       # seconds per (rate, size) step when sweeping
REPORT_MS = 1000    # live line interval (single-step mode)
PAUSE_MS  = 500     # pause between steps so RX can print its summary
END_COPIES = 5

MAGIC    = 0xE5
HLEN     = 10
F_END    = 1
MIN_SIZE = 16


def set_rate(e, rate):
    try:
        e.config(rate=rate)
        print("PHY rate code set: 0x%02x" % rate)
    except Exception as ex:
        print("Could not set rate (old firmware?):", ex)


def send_end(e, step, rate, total):
    b = bytearray(MIN_SIZE)
    b[0] = MAGIC
    b[1] = step & 0xFF
    b[2] = rate & 0xFF
    b[3] = F_END
    struct.pack_into('<H', b, 4, MIN_SIZE)
    struct.pack_into('<I', b, 6, total)
    for _ in range(END_COPIES):
        try:
            e.send(PEER, b, True)
        except OSError:
            pass
        time.sleep_ms(2)


def run_step(e, step, rate, size, duration_ms):
    """Send as fast as possible. duration_ms None = until Ctrl-C, with a live line.
    Returns (frames attempted, ok, fail, elapsed ms, interrupted)."""
    buf = bytearray(size)
    buf[0] = MAGIC
    buf[1] = step & 0xFF
    buf[2] = rate & 0xFF
    struct.pack_into('<H', buf, 4, size)     # intended size, so RX can detect truncation
    for i in range(HLEN, size):
        buf[i] = i & 0xFF

    send = e.send
    pack = struct.pack_into
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff

    seq = ok = fail = 0
    ok_prev = fail_prev = 0
    t0 = t_rep = ticks_ms()
    interrupted = False
    try:
        while True:
            pack('<I', buf, 6, seq)
            # sync send: waits for the send callback, which paces us to the real air rate.
            # seq advances on every attempt, so RX sees a gap for any frame that failed.
            try:
                if send(PEER, buf, True):
                    ok += 1
                else:
                    fail += 1
            except OSError:
                fail += 1
            seq += 1

            now = ticks_ms()
            if duration_ms is not None:
                if ticks_diff(now, t0) >= duration_ms:
                    break
            else:
                dt = ticks_diff(now, t_rep)
                if dt >= REPORT_MS:
                    w_ok = ok - ok_prev
                    print("TX %7.2f KB/s (%6.1f kbit/s) | %5d pkt/s | fail %d" % (
                        w_ok * size * 1000 / 1024 / dt,
                        w_ok * size * 8 / dt,
                        w_ok * 1000 // dt,
                        fail - fail_prev))
                    ok_prev = ok
                    fail_prev = fail
                    t_rep = now
    except KeyboardInterrupt:
        interrupted = True
    return seq, ok, fail, ticks_diff(ticks_ms(), t0), interrupted


def main():
    maxlen = getattr(espnow, "MAX_DATA_LEN", 250)
    print("espnow.MAX_DATA_LEN =", maxlen)
    for s in SIZES:
        if s < MIN_SIZE or s > maxlen:
            raise ValueError("size %d is outside %d..%d" % (s, MIN_SIZE, maxlen))

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
    cur_rate = RATES[0]
    set_rate(e, cur_rate)
    e.add_peer(PEER)

    plan = [(r, s) for r in RATES for s in SIZES]
    steady = len(plan) == 1
    results = []
    tot_ok = tot_bytes = 0
    t_all = time.ticks_ms()

    if steady:
        print("TX started: %d-byte payloads, channel %d. Ctrl-C to stop." % (plan[0][1], CHANNEL))
    else:
        print("Sweep: %d steps of %d s" % (len(plan), STEP_S))

    for step in range(len(plan)):
        rate, size = plan[step]
        if rate != cur_rate:
            set_rate(e, rate)
            cur_rate = rate
        if not steady:
            print("--- step %d: rate 0x%02x, %d B ---" % (step, rate, size))
        seq, ok, fail, dt, stop = run_step(e, step, rate, size, None if steady else STEP_S * 1000)
        send_end(e, step, rate, seq)
        tot_ok += ok
        tot_bytes += ok * size
        if not steady and dt > 0:
            kbs = ok * size * 1000 / 1024 / dt
            print("TX step %d | rate 0x%02x | %4d B | attempted %d (ok %d, fail %d) | %.2f KB/s (TX view)" % (
                step, rate, size, seq, ok, fail, kbs))
            results.append((rate, size, ok * size * 8 / dt))
        if stop:
            break
        if step < len(plan) - 1:
            time.sleep_ms(PAUSE_MS)

    el = time.ticks_diff(time.ticks_ms(), t_all) / 1000
    if steady:
        print("\nDone. avg %.2f KB/s over %.1fs, %d frames sent ok (TX view)" % (
            tot_bytes / 1024 / el, el, tot_ok))
    else:
        print("\nTX-side summary (kbit/s the stack accepted; the RX STEP lines are the real numbers):")
        for rate, size, kbit in results:
            print("  rate 0x%02x %5d B -> %7.1f" % (rate, size, kbit))


if __name__ == "__main__":
    main()
