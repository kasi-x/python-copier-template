# MicroPython firmware

The template can generate a **MicroPython** project: firmware for a
microcontroller (ESP32, RP2/Pico, STM32, ...), deployed with
[mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html).
Unlike a normal Python package, the code runs *on the device*, so the
CPython toolchain (uv/ruff/pytest/basedpyright) is used for the parts that
run on your computer:

- **`firmware/`** — the code that runs on the device. `boot.py` runs first,
  then MicroPython auto-runs `/main.py`. `board_config.py` holds the
  board-specific pins; `core/` holds device-independent logic.
- **`tests/`** — CPython `pytest` tests for `firmware/core`. `core` never
  imports `machine`, so it runs under normal CPython.
- **`typings/`** — MicroPython type stubs (`micropython-<port>-stubs`),
  installed *into a folder* rather than the venv so they don't shadow
  CPython's stdlib during host-side checking.

## Choosing a port

| Port | Typical board | Notes |
|------|---------------|-------|
| **esp32** | ESP32 DevKitC | Most common; default |
| **esp8266** | NodeMCU | Legacy, low memory |
| **rp2** | Raspberry Pi Pico / Pico W | RP2040 / RP2350 |
| **stm32** | Pyboard | STM32 family |
| **samd** | Adafruit ItsyBitsy M0 | SAMD21 / SAMD51 |
| **unix** | your computer | Runs on the host — handy for tests |
| **windows** | your computer | Windows port |
| **mimxrt** | Teensy 4.x | NXP i.MX RT |

The `micropython-<port>-stubs` package describes the port's *generic* board.
Per-board differences (which GPIO the LED is on, etc.) are concentrated in
`firmware/board_config.py`, so moving to another board is a one-file edit.

## Setting up the dev environment

```sh
uv sync                              # ruff / pytest / basedpyright / mpremote
uv run pip install -r requirements-dev.txt --target typings   # port stubs
pre-commit install
```

The stubs are installed into `typings/` (git-ignored) so `basedpyright` can
type-check `firmware/` against MicroPython while `tests/` and
`firmware/core/` are checked against CPython.

## Running the tests

`firmware/core/` is written to be importable under CPython, so the logic is
unit-tested with ordinary `pytest`:

```sh
uv run pytest
```

This runs `tests/test_core.py`, which exercises the device-independent logic
without any hardware.

## Deploying to a device

Connect the device over USB and copy `firmware/` to it (MicroPython runs
`/main.py` at boot):

```sh
uv run mpremote connect auto fs cp -r firmware/ :
uv run mpremote connect auto reset
```

or use the generated task-runner commands (`task deploy`, `just deploy`, ...).
`mpremote connect auto` picks the first USB serial device; use
`mpremote connect list` to see them and pass `port:/dev/ttyACM0` (or `a0`)
to target a specific one.

To iterate on a single file without copying, `mpremote run firmware/main.py`
executes it from RAM.

## Adding a unix-port CI smoke test

The generated CI runs the CPython core tests and type-checks `firmware/`
against the stubs, but does **not** run the firmware itself. To also smoke-run
the code on the MicroPython unix port in CI, add a job that builds the unix
port and runs `main.py`:

```yaml
  unix-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - run: sudo apt-get install -y build-essential libffi-dev pkg-config
      - name: Build the unix port
        run: |
          git clone --depth 1 https://github.com/micropython/micropython.git
          make -C micropython/mpy-cross
          make -C micropython/ports/unix
      - name: Run main.py on the unix port
        run: |
          cd firmware
          ../micropython/ports/unix/build-standard/micropython main.py
```

Note the `unix` port has no on-board LED, so `board_config.py` sets
`LED_PIN = None`; the sample `main.py` will raise if it tries to blink on a
port without hardware. Adjust the smoke command to the logic you actually run.
