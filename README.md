# ESP-NOW Throughput Benchmark (MicroPython)

A minimal two-board benchmark that measures real ESP-NOW payload throughput in KB/s. One board transmits, the other receives and reports what actually arrived, including packet loss and receive-buffer drops.

By default it runs at the **1 Mbps** PHY rate with **2 dBm** TX power, but both are one-line settings.

## Files

| File | Run on | Purpose |
|------|--------|---------|
| `espnow_tx.py` | Sender board | Sends 250-byte packets as fast as the radio allows, reports sent KB/s |
| `espnow_rx.py` | Receiver board | Counts received bytes, detects lost packets via sequence numbers, reports KB/s |

## Requirements

- Two ESP32-family boards (ESP32, S2, S3, C3, ...)
- A MicroPython build with the `espnow` module. Setting the PHY rate via `e.config(rate=...)` needs a reasonably recent build; if yours doesn't support it, TX prints a warning and uses the default rate.

## Usage

1. Copy `espnow_rx.py` to the receiver and `espnow_tx.py` to the sender (e.g. with `mpremote`, Thonny or `ampy`).
2. Start the receiver first:
   ```
   mpremote run espnow_rx.py
   ```
   It prints its MAC address and waits.
3. Start the sender:
   ```
   mpremote run espnow_tx.py
   ```
4. Both boards print a line every second. Press Ctrl-C to stop and see the average.

## Configuration

Settings are constants at the top of each file.

| Setting | File | Default | Notes |
|---------|------|---------|-------|
| `CHANNEL` | both | `1` | Must match on both boards |
| `RATE` | TX | `0` | PHY rate code. `0` = 1 Mbps, `3` = 11 Mbps, `0x0B` = 6 Mbps (OFDM), `0x10` = MCS0 |
| `TXPOWER` | TX (and RX) | `2` | dBm, roughly 2-20 on ESP32 |
| `PAYLOAD` | TX | `250` | Bytes per packet; 250 is the ESP-NOW maximum |
| `PEER` | TX | broadcast | Set to the receiver's MAC for unicast with ACKs and retries |

In broadcast mode (the default) there are no ACKs or retries, so any loss shows up in the receiver's numbers. TX can't know whether packets arrived, so **the RX line is the real throughput figure**.

## Example output

Receiver, 1 Mbps, 2 dBm, 250-byte payloads, boards close together:

```
RX   68.36 KB/s ( 560.0 kbit/s) |   280 pkt/s | lost 0 (0.0%) | buf-drop/s 0
RX   64.45 KB/s ( 528.0 kbit/s) |   264 pkt/s | lost 0 (0.0%) | buf-drop/s 0
RX   67.38 KB/s ( 552.0 kbit/s) |   276 pkt/s | lost 0 (0.0%) | buf-drop/s 0
RX   67.87 KB/s ( 556.0 kbit/s) |   278 pkt/s | lost 0 (0.0%) | buf-drop/s 0
```

That is about 67 KB/s of payload, roughly 44% of the raw 1 Mbps. The rest is spent on the long preamble, MAC and ESP-NOW headers, inter-frame spacing and send-callback latency. Your numbers will vary with board, firmware, RF environment and distance.

## Reading the output

- **KB/s / kbit/s**: payload bytes received per second (headers not counted)
- **pkt/s**: packets received per second
- **lost**: packets missing according to sequence-number gaps
- **buf-drop/s**: packets the radio received but the MicroPython RX buffer discarded because the receive loop didn't keep up

How to tell the two kinds of loss apart:

- `lost` > 0 and `buf-drop/s` = 0: packets were lost over the air (distance, interference, low TX power).
- `buf-drop/s` > 0: the receiver loop is too slow, not the radio.

## Implementation notes

- **TX uses synchronous sends** (`send(..., True)`), so it is paced by the air time rather than by how fast Python can queue packets.
- **RX uses a non-blocking `irecv(0)` loop.** An earlier version used a blocking `irecv(1000)` per packet and only managed about 120 pkt/s against a sender doing about 275 pkt/s. The buffer overflowed, producing about 56% apparent loss and about 29 KB/s. The loss was in the receiver, not the radio. Switching to the non-blocking drain loop fixed it with no other changes. I didn't pin down exactly why the blocking call was so slow.
- `irecv()` returns a buffer that is overwritten on the next call. If you build on this, copy the data (ideally into a preallocated `bytearray`) before the next call.
- At about 275 pkt/s the receive loop has roughly 3.6 ms per packet. Adding real work (flash writes, parsing, heavy `print()`) can eat into that, so watch `buf-drop/s`.

## Troubleshooting

- **No packets on RX:** check that both boards use the same `CHANNEL`, and start RX before TX.
- **"Could not set rate":** your MicroPython build is too old for `e.config(rate=...)`. Update the firmware.
- **High `lost` with `buf-drop/s` at 0:** move the boards closer, raise `TXPOWER`, or try a quieter channel.
- **High `buf-drop/s`:** reduce work in the RX loop, or increase `rxbuf` if the board has spare RAM.

## License

Add your preferred license here (e.g. MIT).
