# ESP-NOW Throughput Benchmark (MicroPython)

A minimal two-board benchmark that measures real ESP-NOW payload throughput. One board transmits, the other receives and reports what actually arrived: throughput, lost frames, duplicates, malformed frames and receive-buffer drops. It can run one fixed setting continuously, or sweep through several payload sizes and PHY rates in one go.

By default it runs 250-byte payloads at the **1 Mbps** PHY rate with **2 dBm** TX power. Rates, sizes and power are one-line settings.

## Files

| File | Run on | Purpose |
|------|--------|---------|
| `espnow_tx.py` | Sender board | Sends frames as fast as the radio allows, one fixed setting or a sweep, and reports what the stack accepted |
| `espnow_rx.py` | Receiver board | Counts what really arrived, detects loss from sequence numbers, prints a live line per second and a summary per step |

## Requirements

- Two ESP32-family boards (ESP32, S2, S3, C3, ...)
- A MicroPython build with the `espnow` module. Setting the PHY rate via `e.config(rate=...)` needs a reasonably recent build; if yours doesn't support it, TX prints a warning and uses the default rate.
- **Payloads above 250 bytes** need ESP-NOW v2 (ESP-IDF 5.4 or newer) and a MicroPython build that reports it: check that `espnow.MAX_DATA_LEN` prints `1470` on **both** boards. If the receiver doesn't support v2, the large steps show up on RX as 0 frames (or as `bad` frames).

## Usage

1. Copy `espnow_rx.py` to the receiver and `espnow_tx.py` to the sender (e.g. with `mpremote`, Thonny or `ampy`).
2. Start the receiver first:
   ```
   mpremote run espnow_rx.py
   ```
   It prints its MAC address and waits.
3. Edit `SIZES` / `RATES` at the top of `espnow_tx.py` if you want something other than the default, then start the sender:
   ```
   mpremote run espnow_tx.py
   ```
4. Read the **RX** output. In steady mode (one size, one rate) both boards print a line every second; press Ctrl-C on TX first (it tells RX the exact number of frames it sent), then on RX.

If you save the scripts on a board as `main.py` they run on boot; if you `import` them instead, call `main()` yourself.

### Sweep mode

Give `SIZES` and/or `RATES` more than one entry and TX runs every combination for `STEP_S` seconds each, for example:

```python
SIZES  = [50, 100, 250, 500, 750, 1000, 1250, 1470]
RATES  = [0, 1, 0x0B]
STEP_S = 5
```

That is 24 steps, a bit over two minutes. RX prints one `STEP` line per combination when it finishes. TX prints its own per-step line and a summary table at the end, but that is only what the sender's stack accepted: **use the RX `STEP` lines for results.**

## Configuration

Settings are constants at the top of each file.

| Setting | File | Default | Notes |
|---------|------|---------|-------|
| `CHANNEL` | both | `1` | Must match on both boards |
| `TXPOWER` | both | `2` | dBm, roughly 2-20 on ESP32. On RX it only matters for ACKs in unicast mode |
| `PEER` | TX | broadcast | Set to the receiver's MAC for unicast with ACKs and retries |
| `SIZES` | TX | `[250]` | Payload sizes in bytes, 16 up to `espnow.MAX_DATA_LEN` (250 on ESP-NOW v1, 1470 on v2) |
| `RATES` | TX | `[0]` | PHY rate codes, see below |
| `STEP_S` | TX | `5` | Seconds per step when sweeping |
| `PAUSE_MS` | TX | `500` | Pause between steps so RX can print its summary |
| `REPORT_MS` | TX, RX | `1000` | Live line interval |
| `IDLE_MS` | RX | `1500` | No frames for this long closes the current step |
| `RXBUF` | RX | `8192` | Receive ring buffer in bytes; must hold several of the largest frames |

PHY rate codes are values of ESP-IDF's `wifi_phy_rate_t`: `0` = 1 Mbps, `1` = 2 Mbps, `3` = 11 Mbps, `0x0B` = 6 Mbps (OFDM), `0x10` = MCS0. The MicroPython setting is write-only, so nothing can read the rate back: the `rate` shown by RX is the code TX **asked for**, and you only see whether it took effect from the throughput.

## Output

Live line on RX, once per second (format example; your numbers will differ):

```
RX s0  250B   67.38 KB/s ( 552.0 kbit/s) |   278 pkt/s | lost 0 (0.0%) | buf-drop 0 | dup 0 | bad 0
```

Step summary on RX, printed when a step ends (format example):

```
STEP 1 | rate 0x00 |  250 B | got 1390 of 1390 | lost 0 (0.0%) | dup 0 | bad 0 | buf-drop 0 | 67.10 KB/s (549.7 kbit/s) | 278 pkt/s
```

### Reading the output

- **KB/s**: payload bytes per second, with 1 KB = 1024 bytes. **kbit/s** uses 1000 bits. Headers are not counted.
- **pkt/s**: frames per second.
- **got X of Y**: frames received (each sequence number counted once) out of frames TX attempted. `Y` comes from the END frames TX sends at the end of a step. If they were all lost, RX prints `Y+ (no END seen)` and frames lost at the very end of the step are not counted.
- **lost**: `Y - X`. In the live line it is the sequence-number gaps seen in that second.
- **dup**: frames whose sequence number was already seen. They are not counted as throughput.
- **bad**: frames whose length differs from the size TX says it sent, or whose last byte is wrong. Should always be 0.
- **buf-drop**: frames the radio received but the MicroPython RX buffer had no room for, because the receive loop didn't keep up.
- **foreign** (only shown when non-zero): frames without the benchmark header, i.e. other ESP-NOW traffic on the channel. They are ignored and never counted as throughput.

Telling the two kinds of loss apart: dropped buffer frames also leave a gap in the sequence numbers, so they are included in `lost`. The loss over the air is roughly `lost - buf-drop`.

- `lost` > 0 and `buf-drop` = 0: frames were lost over the air (distance, interference, low TX power).
- `buf-drop` > 0: the receiver loop is too slow, not (only) the radio.

### Is TX throughput the same as RX throughput?

Not necessarily. In broadcast mode there are no ACKs or retries, so `send()` only tells TX that the frame went out. Compare the numbers:

- RX KB/s close to TX KB/s and `lost` near 0: the sender's figure is real.
- RX much lower: the difference is lost frames, and RX is the right figure.
- RX shows no `STEP` for a size: nothing of that size arrived (see Requirements).

## Example results

RX-side results of a sweep with this benchmark: broadcast, `TXPOWER = 2`, channel 1, 5 s per step. `lost`, `dup`, `bad` and `buf-drop` came from the RX `STEP` lines; `dup`, `bad` and `buf-drop` were 0 in every step, and TX and RX agreed on the number of frames sent. Your numbers will vary with board, firmware, RF environment and distance.

| Rate | Payload | Lost | KB/s | kbit/s | % of raw rate |
|------|---------|------|------|--------|---------------|
| 1 Mbps (`0x00`) | 250 B | 0.0% | 70.0 | 573.5 | 57% |
| 1 Mbps (`0x00`) | 500 B | 0.0% | 87.5 | 717.1 | 72% |
| 1 Mbps (`0x00`) | 750 B | 0.0% | 95.2 | 779.7 | 78% |
| 1 Mbps (`0x00`) | 1000 B | 0.0% | 97.6 | 799.8 | 80% |
| 2 Mbps (`0x01`) | 250 B | 0.0% | 106.2 | 869.5 | 43% |
| 2 Mbps (`0x01`) | 500 B | 0.0% | 145.5 | 1191.9 | 60% |
| 2 Mbps (`0x01`) | 750 B | 0.0% | 164.6 | 1348.1 | 67% |
| 2 Mbps (`0x01`) | 1000 B | 0.0% | 180.8 | 1481.2 | 74% |
| 6 Mbps (`0x0B`) | 250 B | 0.3% | 184.9 | 1514.6 | 25% |
| 6 Mbps (`0x0B`) | 500 B | 1.0% | 289.4 | 2371.0 | 40% |
| 6 Mbps (`0x0B`) | 750 B | 0.5% | 351.6 | 2880.0 | 48% |
| 6 Mbps (`0x0B`) | 1000 B | 0.6% | 397.9 | 3259.9 | 54% |

What the numbers show:

- **Bigger frames help a lot.** Each frame carries a fixed cost on top of its air time. Subtracting the air time leaves roughly 1 ms per frame at every rate and size (an estimate), so larger payloads spread that cost over more bytes. The effect is stronger at higher PHY rates, where air time is short: at 6 Mbps a 250-byte frame reaches only 25% of the raw rate.
- **Loss appears at 6 Mbps.** With broadcast there are no retries, so the 0.3-1.0% is real loss, and the throughput above is not the same as reliable goodput. With `buf-drop` at 0 it was lost over the air, most likely because of the low TX power (not verified). Unicast (`PEER` set to the receiver's MAC) adds ACKs and retries.
- **Not yet measured on RX:** payloads of 1250 and 1470 bytes, and rates above 6 Mbps.

## Implementation notes

- **Frame format.** Every frame starts with a 10-byte header, followed by the byte pattern `index & 0xFF`:

  | Offset | Size | Field |
  |--------|------|-------|
  | 0 | 1 | magic `0xE5` |
  | 1 | 1 | step number |
  | 2 | 1 | PHY rate code TX requested |
  | 3 | 1 | flags (bit 0 = END frame) |
  | 4 | 2 | payload size TX intended |
  | 6 | 4 | sequence number |

  The sequence number advances on **every attempt**, including attempts the stack reports as failed, so a failed send also shows up as a gap on RX. After each step TX sends 5 END frames whose sequence field holds the number of frames attempted; RX uses the first one.
- **Steps.** RX starts measuring a step at its first data frame and closes it on END, on a new step number, when the sequence number jumps far backwards (TX restarted), or after `IDLE_MS` without frames. The rate is calculated from the first to the last frame received, excluding the first frame, so start-up time doesn't count.
- **TX uses synchronous sends** (`send(..., True)`), so it is paced by the air time rather than by how fast Python can queue packets.
- **RX uses a non-blocking `irecv(0)` loop.** An earlier version used a blocking `irecv(1000)` per packet and only managed about 120 pkt/s against a sender doing about 275 pkt/s. The buffer overflowed, producing about 56% apparent loss and about 29 KB/s. The loss was in the receiver, not the radio. Switching to the non-blocking drain loop fixed it with no other changes. I didn't pin down exactly why the blocking call was so slow.
- `irecv()` returns a buffer that is overwritten on the next call. If you build on this, copy the data (ideally into a preallocated `bytearray`) before the next call.
- At about 275 pkt/s the receive loop has roughly 3.6 ms per packet. Parsing the header costs some of it, and adding real work (flash writes, heavy `print()`) can eat into the rest, so watch `buf-drop`. At high PHY rates with small payloads the packet rate goes up a lot.

## Troubleshooting

- **No packets on RX:** check that both boards use the same `CHANNEL`, and start RX before TX. If RX starts late it counts the frames it missed as lost.
- **`foreign` is non-zero:** other ESP-NOW devices are sending on the channel. Use another `CHANNEL`, or unicast to the receiver with `PEER`. If two boards run this benchmark at once, their steps will be mixed up.
- **`bad` is non-zero, or large steps get no frames:** check `espnow.MAX_DATA_LEN` on both boards. Frames above 250 bytes need ESP-NOW v2 end to end.
- **`dup` is non-zero:** frames were delivered twice (for example a retransmit after a lost ACK in unicast mode). Duplicates are not counted as throughput.
- **"Could not set rate":** your MicroPython build is too old for `e.config(rate=...)`. Update the firmware.
- **High `lost` with `buf-drop` at 0:** move the boards closer, raise `TXPOWER`, or try a quieter channel. Higher PHY rates need a stronger signal.
- **High `buf-drop`:** reduce work in the RX loop, or increase `RXBUF` if the board has spare RAM.
- **`(no END seen)` in a step summary:** all END frames were lost, so frames lost at the very end of that step are not counted. Usually harmless; the loss figure is then a slight underestimate.
- **Restarting TX while RX is running:** wait until RX prints the previous `STEP` line (about 1.5 s), or Ctrl-C on TX so it sends END before it exits.

## License

Add your preferred license here (e.g. MIT).
