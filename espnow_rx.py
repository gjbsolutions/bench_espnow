# espnow_rx.py - ESP-NOW throughput benchmark (receiver)
# Start this first, then start espnow_tx.py on the other board.
#
# Every frame sent by espnow_tx.py starts with a 10-byte header:
#   magic(1) step(1) rate(1) flags(1) size(2) seq(4), little endian
# ('size' is the payload length TX intended to send.)
# The receiver uses it to count what really arrived:
#   - gaps in seq                      -> lost frames
#   - repeated / old seq               -> duplicates (not counted as throughput)
#   - length != size in header, or wrong last byte -> "bad" frames
#   - frames without the magic byte    -> "foreign" (other ESP-NOW traffic), ignored
# When TX finishes a step it sends END frames carrying the number of frames it
# attempted, so RX can also count frames lost at the very end of the step.
import network, espnow, struct, time

CHANNEL   = 1       # must match TX
TXPOWER   = 2       # only matters if TX uses unicast (ACKs)
REPORT_MS = 1000    # live line interval
IDLE_MS   = 1500    # no frames for this long -> the current step is closed
RXBUF     = 8192    # ring buffer in bytes; must hold several of the largest frames

MAGIC = 0xE5
HDR   = '<BBBBHI'   # magic, step, rate code, flags, size, seq
HLEN  = 10
F_END = 1


def rx_drops(e):
    # frames the radio received but the MicroPython ring buffer had no room for
    try:
        return e.stats()[4]
    except Exception:
        return 0


def step_summary(step, rate, size, got, last_seq, end_seq, nbytes, first_len, dt, dup, bad, drops):
    # end_seq < 0 means no END frame was seen: expected count is then only
    # "highest seq seen + 1", so frames lost at the very end are not counted.
    exp = last_seq + 1
    if end_seq > exp:
        exp = end_seq
    lost = exp - got
    if got > 1 and dt > 0:
        by = nbytes - first_len          # the first frame only starts the clock
        kbs = by * 1000 / 1024 / dt
        kbit = by * 8 / dt
        pps = (got - 1) * 1000 / dt
    else:
        kbs = kbit = pps = 0
    print("STEP %d | rate 0x%02x | %4d B | got %d of %d%s | lost %d (%.1f%%) | dup %d | bad %d | buf-drop %d | %.2f KB/s (%.1f kbit/s) | %.0f pkt/s" % (
        step, rate, size, got, exp, "" if end_seq >= 0 else "+ (no END seen)",
        lost, 100 * lost / exp if exp else 0, dup, bad, drops, kbs, kbit, pps))


def main():
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
    e.config(rxbuf=RXBUF)

    print("RX MAC:", ":".join("%02x" % b for b in sta.config('mac')))
    print("Listening on channel", CHANNEL)

    unpack = struct.unpack_from
    irecv = e.irecv
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff

    active = False                      # is a step currently being measured?
    cur_step = rate = size = 0
    got = nbytes = first_len = dup = bad = 0
    last_seq = end_seq = -1
    t_first = t_last = t_seen = t_rep = 0
    drop0 = last_drop = 0
    wp = wb = wlost = wdup = wbad = wforeign = 0     # 1-second window counters
    foreign = 0

    try:
        while True:
            # non-blocking poll: drain the ring buffer as fast as possible
            mac, msg = irecv(0)
            now = ticks_ms()

            if msg is None:
                if active and ticks_diff(now, t_seen) >= IDLE_MS:
                    step_summary(cur_step, rate, size, got, last_seq, end_seq, nbytes,
                                 first_len, ticks_diff(t_last, t_first), dup, bad,
                                 rx_drops(e) - drop0)
                    active = False
            else:
                n = len(msg)
                if n < HLEN or msg[0] != MAGIC:
                    foreign += 1
                    wforeign += 1
                else:
                    _, st, rt, flags, hsize, seq = unpack(HDR, msg, 0)
                    t_seen = now
                    if flags & F_END:
                        # END frames are sent several times; only the first one counts
                        if active and st == cur_step:
                            end_seq = seq
                            step_summary(cur_step, rate, size, got, last_seq, end_seq, nbytes,
                                         first_len, ticks_diff(t_last, t_first), dup, bad,
                                         rx_drops(e) - drop0)
                            active = False
                    else:
                        # new step id, or seq far below the last one (TX was restarted)
                        if active and (st != cur_step or last_seq - seq > 100):
                            step_summary(cur_step, rate, size, got, last_seq, end_seq, nbytes,
                                         first_len, ticks_diff(t_last, t_first), dup, bad,
                                         rx_drops(e) - drop0)
                            active = False
                        if not active:
                            active = True
                            cur_step = st
                            rate = rt
                            size = hsize             # payload size TX says it is sending
                            got = nbytes = dup = bad = 0
                            last_seq = end_seq = -1
                            first_len = n
                            t_first = t_rep = now
                            drop0 = last_drop = rx_drops(e)
                            wp = wb = wlost = wdup = wbad = wforeign = 0
                        if seq <= last_seq:
                            dup += 1
                            wdup += 1
                        else:
                            if seq > last_seq + 1:
                                wlost += seq - last_seq - 1
                            last_seq = seq
                            got += 1
                            nbytes += n
                            wp += 1
                            wb += n
                            t_last = now
                            if n != hsize or msg[n - 1] != (n - 1) & 0xFF:
                                bad += 1
                                wbad += 1

            if active:
                dt = ticks_diff(now, t_rep)
                if dt >= REPORT_MS:
                    d = rx_drops(e)
                    tot = wp + wlost
                    print("RX s%d %4dB %7.2f KB/s (%6.1f kbit/s) | %5d pkt/s | lost %d (%.1f%%) | buf-drop %d | dup %d | bad %d%s" % (
                        cur_step, size,
                        wb * 1000 / 1024 / dt,
                        wb * 8 / dt,
                        wp * 1000 // dt,
                        wlost,
                        100 * wlost / tot if tot else 0,
                        d - last_drop, wdup, wbad,
                        " | foreign %d" % wforeign if wforeign else ""))
                    last_drop = d
                    wp = wb = wlost = wdup = wbad = wforeign = 0
                    t_rep = now
    except KeyboardInterrupt:
        pass

    if active:
        step_summary(cur_step, rate, size, got, last_seq, end_seq, nbytes,
                     first_len, ticks_diff(t_last, t_first), dup, bad,
                     rx_drops(e) - drop0)
    if foreign:
        print("Ignored %d foreign frame(s) (no benchmark header)." % foreign)
    print("Done.")


if __name__ == "__main__":
    main()
