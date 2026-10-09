//! esp32_blink, in Rust -- smoke-test firmware for a classic ESP32 dev board.
//!
//! What ../esp32_blink.ino does, line for line on the wire: blinks the on-board
//! LED on GPIO 2 and prints a heartbeat at 115200 baud, so a fresh board and
//! toolchain can be verified end to end -- build, flash, and read back.
//!
//! Identification protocol (what `apothecary firmware listen` and a board's
//! Machine look for): print `apothecary <sketch>: hello` at boot and again
//! every ANNOUNCE_EVERY beats, so a monitor that attaches late still learns
//! which sketch is running without a reset. The sketch is esp32_blink whatever
//! it was written in, so the Machine hears this one as it hears the Arduino one.

#![no_std]
#![no_main]

use esp_backtrace as _;
use esp_hal::clock::CpuClock;
use esp_hal::delay::Delay;
use esp_hal::gpio::{Level, Output, OutputConfig};
use esp_hal::main;
use esp_println::println;

esp_bootloader_esp_idf::esp_app_desc!();

const LED_BUILTIN: u8 = 2;
const PERIOD_MS: u32 = 500;
const ANNOUNCE_EVERY: u32 = 10; // beats: one each time the LED comes on, once a second

fn announce() {
    println!("apothecary esp32_blink: hello");
    println!(
        "chip: {} rev {}, {} core(s), {} MHz, LED on GPIO {}",
        chip::model(),
        chip::revision(),
        chip::cores(),
        chip::cpu_mhz(),
        LED_BUILTIN
    );
}

#[main]
fn main() -> ! {
    let config = esp_hal::Config::default().with_cpu_clock(CpuClock::max());
    let peripherals = esp_hal::init(config);
    let mut led = Output::new(peripherals.GPIO2, Level::Low, OutputConfig::default());
    let delay = Delay::new();

    delay.delay_millis(100);
    println!();
    announce();

    let mut on = false;
    let mut beats: u32 = 0;
    loop {
        on = !on;
        led.set_level(if on { Level::High } else { Level::Low });
        if on {
            beats += 1;
            println!("blink {}", beats);
            if beats % ANNOUNCE_EVERY == 0 {
                announce();
            }
        }
        delay.delay_millis(PERIOD_MS);
    }
}

/// What the Arduino core's ESP.getChipModel(), getChipRevision(), getChipCores()
/// and getCpuFreqMHz() say on a classic ESP32, read from the same eFuses.
mod chip {
    use esp_hal::efuse;

    /// The package, from CHIP_PACKAGE; a revision 3 die is a -V3.
    pub fn model() -> &'static str {
        let package = efuse::read_field_le::<u8>(efuse::CHIP_PACKAGE) & 0x7;
        let v3 = efuse::chip_revision().major == 3;
        match package {
            0 if v3 => "ESP32-D0WDQ6-V3",
            0 => "ESP32-D0WDQ6",
            1 if v3 => "ESP32-D0WD-V3",
            1 => "ESP32-D0WD",
            2 => "ESP32-D2WD",
            3 => "ESP32-D0WDR2-V3",
            4 => "ESP32-PICO-D2",
            5 => "ESP32-PICO-D4",
            6 => "ESP32-PICO-V3-02",
            _ => "Unknown",
        }
    }

    /// The revision as ESP-IDF combines it: major * 100 + minor (301 for v3.1).
    pub fn revision() -> u16 {
        efuse::chip_revision().combined()
    }

    /// Two, unless the eFuse that disables the application CPU is burnt.
    pub fn cores() -> u32 {
        efuse::core_count()
    }

    /// What the CPU runs at now.
    pub fn cpu_mhz() -> u32 {
        esp_hal::clock::cpu_clock().as_mhz()
    }
}
