"""
Pixie Frog Enclosure Monitor
Raspberry Pi 5 — Multi-sensor Flask app with dynamic sensor configuration
Run with: python3 app.py
"""

import threading
import time
import sqlite3
import json
import random
import os
from collections import deque
from datetime import datetime
from flask import Flask, jsonify, render_template, request

HABITATOS_VERSION = "0.07"
HABITATOS_CODENAME = "Thicket"

# ─── Hardware library imports (gracefully mock if not on Pi) ──────────────────
ON_PI = False
try:
    import RPi.GPIO as GPIO
    ON_PI = True
except (ImportError, RuntimeError):
    pass

try:
    import Adafruit_DHT
    HAS_DHT = True
except ImportError:
    HAS_DHT = False

try:
    import smbus2 as smbus
    HAS_I2C = True
except ImportError:
    HAS_I2C = False

try:
    import spidev
    HAS_SPI = True
except ImportError:
    HAS_SPI = False

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

if not ON_PI:
    print("[WARN] Not running on a Pi — all sensors will be simulated.")


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

LOG_INTERVAL_SECONDS  = 5
READ_INTERVAL_SECONDS = 1
IDLE_TIMEOUT_SECONDS  = 120
AVG_WINDOW            = 600   # 10-minute rolling average at 1Hz

DB_PATH     = "enclosure.db"
CONFIG_PATH = "config.json"

RELAY_PINS = {
    "ch1": 17,
    "ch2": 18,
    "ch3": 27,
    "ch4": 22,
}


# ─────────────────────────────────────────────────────────────────────────────
# ENCLOSURE PROFILES
# Each profile sets default sensors, relay labels/icons, and thresholds.
# ─────────────────────────────────────────────────────────────────────────────

PROFILES = {
    "tropical_frog": {
        "label": "Tropical frog / amphibian",
        "relay_labels": {"ch1": "Environmental light", "ch2": "Heat lamp", "ch3": "Misting pump", "ch4": "Circulation fan"},
        "relay_icons":  {"ch1": "🌿", "ch2": "🔥", "ch3": "💧", "ch4": "🌀"},
        "sensors": [
            {"id": "s1", "type": "dht11", "enabled": True,  "name": "Main enclosure", "pin": "4",
             "interface": "gpio", "readings": [
                {"key": "temp_f",   "label": "Temperature", "unit": "°F", "min": 75.0, "max": 85.0},
                {"key": "humidity", "label": "Humidity",    "unit": "%",  "min": 60.0, "max": 80.0}
             ], "calibration": {}},
        ],
    },
    "aquatic": {
        "label": "Aquatic / semi-aquatic",
        "relay_labels": {"ch1": "Water heater", "ch2": "Filter pump", "ch3": "Air pump", "ch4": "UV steriliser"},
        "relay_icons":  {"ch1": "🌡️", "ch2": "🔄", "ch3": "💨", "ch4": "☀️"},
        "sensors": [
            {"id": "s1", "type": "dht11",  "enabled": True,  "name": "Ambient",       "pin": "4",       "interface": "gpio", "readings": [{"key": "temp_f", "label": "Air temp", "unit": "°F", "min": 72.0, "max": 82.0}, {"key": "humidity", "label": "Humidity", "unit": "%", "min": 60.0, "max": 80.0}], "calibration": {}},
            {"id": "s2", "type": "ph",     "enabled": True,  "name": "Water pH",      "pin": "i2c:99",  "interface": "ezo",  "readings": [{"key": "ph", "label": "pH", "unit": "pH", "min": 6.5, "max": 7.5}], "calibration": {}},
            {"id": "s3", "type": "ammonia","enabled": True,  "name": "Ammonia NH3",   "pin": "i2c:97",  "interface": "ezo",  "readings": [{"key": "nh3", "label": "Ammonia", "unit": "ppm", "min": 0.0, "max": 0.25}], "calibration": {}},
            {"id": "s4", "type": "nitrite","enabled": True,  "name": "Nitrite NO2",   "pin": "i2c:96",  "interface": "ezo",  "readings": [{"key": "no2", "label": "Nitrite", "unit": "ppm", "min": 0.0, "max": 0.5}], "calibration": {}},
            {"id": "s5", "type": "nitrate","enabled": True,  "name": "Nitrate NO3",   "pin": "i2c:95",  "interface": "ezo",  "readings": [{"key": "no3", "label": "Nitrate", "unit": "ppm", "min": 0.0, "max": 20.0}], "calibration": {}},
            {"id": "s6", "type": "tds",    "enabled": True,  "name": "TDS",           "pin": "i2c:100", "interface": "ezo",  "readings": [{"key": "tds", "label": "TDS", "unit": "ppm", "min": 50.0, "max": 300.0}], "calibration": {}},
            {"id": "s7", "type": "water_level", "enabled": True, "name": "Reservoir", "pin": "24",      "interface": "gpio", "readings": [{"key": "level", "label": "Water level", "unit": "%", "min": 25.0, "max": 100.0}], "calibration": {}},
        ],
    },
    "tropical_reptile": {
        "label": "Tropical reptile",
        "relay_labels": {"ch1": "Basking lamp", "ch2": "UVB lamp", "ch3": "Misting pump", "ch4": "Circulation fan"},
        "relay_icons":  {"ch1": "🔆", "ch2": "☀️", "ch3": "💧", "ch4": "🌀"},
        "sensors": [
            {"id": "s1", "type": "dht11", "enabled": True,  "name": "Ambient",      "pin": "4",  "interface": "gpio", "readings": [{"key": "temp_f", "label": "Ambient temp", "unit": "°F", "min": 75.0, "max": 85.0}, {"key": "humidity", "label": "Humidity", "unit": "%", "min": 40.0, "max": 60.0}], "calibration": {}},
            {"id": "s2", "type": "dht22", "enabled": True,  "name": "Basking zone", "pin": "17", "interface": "gpio", "readings": [{"key": "temp_f", "label": "Basking temp", "unit": "°F", "min": 95.0, "max": 110.0}, {"key": "humidity", "label": "Humidity", "unit": "%", "min": 30.0, "max": 50.0}], "calibration": {}},
            {"id": "s3", "type": "uv",    "enabled": True,  "name": "UV Index",     "pin": "i2c:16", "interface": "i2c", "readings": [{"key": "uvi", "label": "UV index", "unit": "UVI", "min": 2.0, "max": 6.0}], "calibration": {}},
        ],
    },
    "arboreal_reptile": {
        "label": "Arboreal reptile (chameleon / tree frog)",
        "relay_labels": {"ch1": "Basking lamp", "ch2": "UVB lamp", "ch3": "Drip / misting", "ch4": "Exhaust fan"},
        "relay_icons":  {"ch1": "🔆", "ch2": "☀️", "ch3": "🌧️", "ch4": "💨"},
        "sensors": [
            {"id": "s1", "type": "dht22", "enabled": True, "name": "Mid canopy", "pin": "4",  "interface": "gpio", "readings": [{"key": "temp_f", "label": "Temperature", "unit": "°F", "min": 72.0, "max": 80.0}, {"key": "humidity", "label": "Humidity", "unit": "%", "min": 60.0, "max": 80.0}], "calibration": {}},
            {"id": "s2", "type": "dht22", "enabled": True, "name": "Canopy top", "pin": "17", "interface": "gpio", "readings": [{"key": "temp_f", "label": "Temperature", "unit": "°F", "min": 75.0, "max": 85.0}, {"key": "humidity", "label": "Humidity", "unit": "%", "min": 50.0, "max": 70.0}], "calibration": {}},
            {"id": "s3", "type": "uv",   "enabled": True, "name": "UV Index",   "pin": "i2c:16", "interface": "i2c", "readings": [{"key": "uvi", "label": "UV index", "unit": "UVI", "min": 2.0, "max": 5.0}], "calibration": {}},
        ],
    },
    "tortoise": {
        "label": "Tortoise / arid reptile",
        "relay_labels": {"ch1": "Basking lamp", "ch2": "UVB lamp", "ch3": "Ambient heat", "ch4": "Circulation fan"},
        "relay_icons":  {"ch1": "🔆", "ch2": "☀️", "ch3": "♨️", "ch4": "🌀"},
        "sensors": [
            {"id": "s1", "type": "dht11", "enabled": True, "name": "Ambient",      "pin": "4",      "interface": "gpio", "readings": [{"key": "temp_f", "label": "Ambient temp", "unit": "°F", "min": 75.0, "max": 85.0}, {"key": "humidity", "label": "Humidity", "unit": "%", "min": 20.0, "max": 40.0}], "calibration": {}},
            {"id": "s2", "type": "dht22", "enabled": True, "name": "Basking zone", "pin": "17",     "interface": "gpio", "readings": [{"key": "temp_f", "label": "Basking temp", "unit": "°F", "min": 95.0, "max": 105.0}, {"key": "humidity", "label": "Humidity", "unit": "%", "min": 10.0, "max": 30.0}], "calibration": {}},
            {"id": "s3", "type": "uv",   "enabled": True, "name": "UV Index",     "pin": "i2c:16", "interface": "i2c",  "readings": [{"key": "uvi", "label": "UV index", "unit": "UVI", "min": 3.0, "max": 8.0}], "calibration": {}},
        ],
    },
    "freshwater_fish": {
        "label": "Freshwater fish / planted tank",
        "relay_labels": {"ch1": "Tank light", "ch2": "Heater", "ch3": "CO2 solenoid", "ch4": "Filter pump"},
        "relay_icons":  {"ch1": "💡", "ch2": "🌡️", "ch3": "💨", "ch4": "🔄"},
        "sensors": [
            {"id": "s1", "type": "ph",        "enabled": True,  "name": "Water pH",       "pin": "i2c:99",  "interface": "ezo",  "readings": [{"key": "ph",  "label": "pH",              "unit": "pH",  "min": 6.5, "max": 7.5}],  "calibration": {}},
            {"id": "s2", "type": "ammonia",   "enabled": True,  "name": "Ammonia NH3",    "pin": "i2c:97",  "interface": "ezo",  "readings": [{"key": "nh3", "label": "Ammonia",          "unit": "ppm", "min": 0.0, "max": 0.25}], "calibration": {}},
            {"id": "s3", "type": "nitrite",   "enabled": True,  "name": "Nitrite NO2",    "pin": "i2c:96",  "interface": "ezo",  "readings": [{"key": "no2", "label": "Nitrite",          "unit": "ppm", "min": 0.0, "max": 0.5}],  "calibration": {}},
            {"id": "s4", "type": "nitrate",   "enabled": True,  "name": "Nitrate NO3",    "pin": "i2c:95",  "interface": "ezo",  "readings": [{"key": "no3", "label": "Nitrate",          "unit": "ppm", "min": 0.0, "max": 20.0}], "calibration": {}},
            {"id": "s5", "type": "chlorine",  "enabled": True,  "name": "Chlorine",       "pin": "i2c:98",  "interface": "ezo",  "readings": [{"key": "cl",  "label": "Chlorine",         "unit": "ppm", "min": 0.0, "max": 0.01}], "calibration": {}},
            {"id": "s6", "type": "tds",       "enabled": True,  "name": "TDS",            "pin": "i2c:100", "interface": "ezo",  "readings": [{"key": "tds", "label": "TDS",              "unit": "ppm", "min": 50.0,"max": 300.0}], "calibration": {}},
            {"id": "s7", "type": "hardness",  "enabled": True,  "name": "Water hardness", "pin": "i2c:101", "interface": "ezo",  "readings": [{"key": "gh",  "label": "General hardness", "unit": "dGH", "min": 4.0, "max": 12.0}], "calibration": {}},
            {"id": "s8", "type": "carbonate", "enabled": True,  "name": "Carbonate KH",   "pin": "i2c:102", "interface": "ezo",  "readings": [{"key": "kh",  "label": "Carbonate hardness","unit": "dKH", "min": 3.0, "max": 8.0}],  "calibration": {}},
            {"id": "s9", "type": "co2",       "enabled": False, "name": "CO2",            "pin": "uart:0",  "interface": "uart", "readings": [{"key": "co2", "label": "CO₂",              "unit": "ppm", "min": 20.0,"max": 30.0}],  "calibration": {}},
        ],
    },
    "custom": {
        "label": "Custom / blank profile",
        "relay_labels": {"ch1": "Channel 1", "ch2": "Channel 2", "ch3": "Channel 3", "ch4": "Channel 4"},
        "relay_icons":  {"ch1": "⚡", "ch2": "⚡", "ch3": "⚡", "ch4": "⚡"},
        "sensors": [],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# SENSOR SIMULATION VALUES  (used when not on Pi)
# ─────────────────────────────────────────────────────────────────────────────

SIM_DEFAULTS = {
    "temp_f":   {"base": 78.0,  "drift": 0.15, "lo": 70.0, "hi": 92.0},
    "humidity": {"base": 72.0,  "drift": 0.25, "lo": 45.0, "hi": 93.0},
    "ph":       {"base": 7.0,   "drift": 0.02, "lo": 5.0,  "hi": 9.0},
    "nh3":      {"base": 0.1,   "drift": 0.01, "lo": 0.0,  "hi": 2.0},
    "no2":      {"base": 0.2,   "drift": 0.01, "lo": 0.0,  "hi": 5.0},
    "no3":      {"base": 10.0,  "drift": 0.2,  "lo": 0.0,  "hi": 100.0},
    "cl":       {"base": 0.0,   "drift": 0.001,"lo": 0.0,  "hi": 5.0},
    "tds":      {"base": 150.0, "drift": 1.0,  "lo": 0.0,  "hi": 500.0},
    "gh":       {"base": 8.0,   "drift": 0.05, "lo": 0.0,  "hi": 30.0},
    "kh":       {"base": 5.0,   "drift": 0.05, "lo": 0.0,  "hi": 20.0},
    "co2":      {"base": 650.0, "drift": 5.0,  "lo": 400.0,"hi": 2000.0},
    "aqi":      {"base": 15.0,  "drift": 0.5,  "lo": 0.0,  "hi": 300.0},
    "uvi":      {"base": 2.0,   "drift": 0.05, "lo": 0.0,  "hi": 11.0},
    "moisture": {"base": 55.0,  "drift": 0.3,  "lo": 0.0,  "hi": 100.0},
    "level":    {"base": 75.0,  "drift": 0.1,  "lo": 0.0,  "hi": 100.0},
    "value":    {"base": 50.0,  "drift": 0.5,  "lo": 0.0,  "hi": 100.0},
}

# Per-sensor simulation state (drifting values)
_sim_values = {}


def sim_read(sensor_id, key):
    """Return a smoothly drifting simulated value for a given sensor+key."""
    sk = f"{sensor_id}:{key}"
    d = SIM_DEFAULTS.get(key, SIM_DEFAULTS["value"])
    if sk not in _sim_values:
        _sim_values[sk] = d["base"]
    v = _sim_values[sk] + random.uniform(-d["drift"], d["drift"])
    v = round(max(d["lo"], min(d["hi"], v)), 3)
    _sim_values[sk] = v
    return v


# ─────────────────────────────────────────────────────────────────────────────
# SENSOR DRIVER BASE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class SensorDriver:
    """Base class for all sensor drivers."""

    def __init__(self, sensor_cfg):
        self.cfg    = sensor_cfg
        self.id     = sensor_cfg["id"]
        self.pin    = sensor_cfg.get("pin", "")
        self.calib  = sensor_cfg.get("calibration", {})

    def read(self):
        """Return dict {reading_key: value} or None on failure."""
        raise NotImplementedError

    def apply_calibration(self, key, value):
        """Apply offset calibration if configured."""
        offset = self.calib.get(key + "_offset", 0.0)
        return round(value + offset, 3)


# ─────────────────────────────────────────────────────────────────────────────
# SENSOR DRIVERS
# ─────────────────────────────────────────────────────────────────────────────

class DHT11Driver(SensorDriver):
    def read(self):
        if ON_PI and HAS_DHT:
            try:
                pin = int(self.pin)
                humidity, temp_c = Adafruit_DHT.read_retry(Adafruit_DHT.DHT11, pin)
                if humidity is not None and temp_c is not None:
                    temp_f = round(temp_c * 9 / 5 + 32, 1)
                    return {
                        "temp_f":   self.apply_calibration("temp_f",   temp_f),
                        "humidity": self.apply_calibration("humidity",  round(humidity, 1)),
                    }
            except Exception as e:
                print(f"[SENSOR:{self.id}] DHT11 read error: {e}")
            return None
        return {
            "temp_f":   self.apply_calibration("temp_f",   sim_read(self.id, "temp_f")),
            "humidity": self.apply_calibration("humidity",  sim_read(self.id, "humidity")),
        }


class DHT22Driver(SensorDriver):
    def read(self):
        if ON_PI and HAS_DHT:
            try:
                pin = int(self.pin)
                humidity, temp_c = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, pin)
                if humidity is not None and temp_c is not None:
                    temp_f = round(temp_c * 9 / 5 + 32, 1)
                    return {
                        "temp_f":   self.apply_calibration("temp_f",   temp_f),
                        "humidity": self.apply_calibration("humidity",  round(humidity, 1)),
                    }
            except Exception as e:
                print(f"[SENSOR:{self.id}] DHT22 read error: {e}")
            return None
        return {
            "temp_f":   self.apply_calibration("temp_f",   sim_read(self.id, "temp_f")),
            "humidity": self.apply_calibration("humidity",  sim_read(self.id, "humidity")),
        }


class EZODriver(SensorDriver):
    """
    Atlas Scientific EZO probe driver via I2C.
    Handles pH, NH3, NO2, NO3, Cl, TDS, GH, KH probes.
    EZO I2C address is embedded in pin field as 'i2c:<decimal_addr>'.
    """
    EZO_KEYS = {
        "ph":       "ph",
        "ammonia":  "nh3",
        "nitrite":  "no2",
        "nitrate":  "no3",
        "chlorine": "cl",
        "tds":      "tds",
        "hardness": "gh",
        "carbonate":"kh",
    }

    def _get_addr(self):
        try:
            return int(self.pin.split(":")[1])
        except Exception:
            return 99

    def read(self):
        key = self.EZO_KEYS.get(self.cfg["type"], "value")
        if ON_PI and HAS_I2C:
            try:
                bus  = smbus.SMBus(1)
                addr = self._get_addr()
                bus.write_i2c_block_data(addr, 0, list(b"R\00"))
                time.sleep(0.9)
                data = bus.read_i2c_block_data(addr, 0, 31)
                # EZO response: first byte is status, rest is ASCII float
                if data[0] == 1:
                    raw = bytes(data[1:]).rstrip(b"\x00").decode("ascii").strip()
                    value = float(raw)
                    return {key: self.apply_calibration(key, value)}
            except Exception as e:
                print(f"[SENSOR:{self.id}] EZO read error: {e}")
            return None
        return {key: self.apply_calibration(key, sim_read(self.id, key))}


class AnalogADCDriver(SensorDriver):
    """
    Analog sensor via MCP3008 8-channel ADC over SPI.
    Pin field: 'spi:<channel>' (0–7).
    Subclass must implement voltage_to_value().
    """
    def _read_channel(self, channel):
        if ON_PI and HAS_SPI:
            try:
                spi = spidev.SpiDev()
                spi.open(0, 0)
                spi.max_speed_hz = 1350000
                r = spi.xfer2([1, (8 + channel) << 4, 0])
                spi.close()
                return ((r[1] & 3) << 8) + r[2]   # 0–1023
            except Exception as e:
                print(f"[SENSOR:{self.id}] SPI read error: {e}")
        return random.randint(300, 700)  # sim raw ADC

    def _get_channel(self):
        try:
            return int(self.pin.split(":")[1])
        except Exception:
            return 0

    def voltage_to_value(self, raw):
        """Override in subclass. raw is 0–1023."""
        return round(raw / 1023 * 100, 1)


class SoilMoistureDriver(AnalogADCDriver):
    def read(self):
        raw = self._read_channel(self._get_channel())
        # Typical capacitive sensor: dry ~800, wet ~300
        pct = round(max(0, min(100, (800 - raw) / 5)), 1)
        return {"moisture": self.apply_calibration("moisture", pct)}


class WaterLevelDriver(SensorDriver):
    """GPIO-based float switch. HIGH = full, LOW = low."""
    def read(self):
        if ON_PI:
            try:
                pin = int(self.pin)
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                state_val = GPIO.input(pin)
                return {"level": 100.0 if state_val else 20.0}
            except Exception as e:
                print(f"[SENSOR:{self.id}] Water level read error: {e}")
        return {"level": self.apply_calibration("level", sim_read(self.id, "level"))}


class CO2Driver(SensorDriver):
    """MH-Z19 CO2 sensor via UART."""
    CMD_READ = bytes([0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79])

    def read(self):
        if ON_PI and HAS_SERIAL:
            try:
                port = self.pin.replace("uart:", "/dev/ttyS")
                ser  = serial.Serial(port, 9600, timeout=1)
                ser.write(self.CMD_READ)
                response = ser.read(9)
                ser.close()
                if len(response) == 9 and response[0] == 0xFF:
                    co2 = response[2] * 256 + response[3]
                    return {"co2": self.apply_calibration("co2", float(co2))}
            except Exception as e:
                print(f"[SENSOR:{self.id}] CO2 read error: {e}")
            return None
        return {
            "co2": self.apply_calibration("co2", sim_read(self.id, "co2")),
            "aqi": self.apply_calibration("aqi", sim_read(self.id, "aqi")),
        }


class UVDriver(SensorDriver):
    """VEML6075 UV sensor via I2C (address 0x10)."""
    ADDR    = 0x10
    REG_UVA = 0x07
    REG_UVB = 0x09

    def read(self):
        if ON_PI and HAS_I2C:
            try:
                bus = smbus.SMBus(1)
                uva = bus.read_word_data(self.ADDR, self.REG_UVA)
                uvb = bus.read_word_data(self.ADDR, self.REG_UVB)
                uvi = round((uva + uvb) / 2 / 100, 1)
                return {"uvi": self.apply_calibration("uvi", uvi)}
            except Exception as e:
                print(f"[SENSOR:{self.id}] UV read error: {e}")
            return None
        return {"uvi": self.apply_calibration("uvi", sim_read(self.id, "uvi"))}


class GenericDriver(SensorDriver):
    """Placeholder for any unlisted sensor type — always simulates."""
    def read(self):
        readings = self.cfg.get("readings", [])
        result = {}
        for r in readings:
            result[r["key"]] = self.apply_calibration(r["key"], sim_read(self.id, r["key"]))
        return result if result else None


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER REGISTRY  —  maps type string → driver class
# ─────────────────────────────────────────────────────────────────────────────

DRIVER_MAP = {
    "dht11":     DHT11Driver,
    "dht22":     DHT22Driver,
    "ph":        EZODriver,
    "ammonia":   EZODriver,
    "nitrite":   EZODriver,
    "nitrate":   EZODriver,
    "chlorine":  EZODriver,
    "tds":       EZODriver,
    "hardness":  EZODriver,
    "carbonate": EZODriver,
    "co2":       CO2Driver,
    "uv":        UVDriver,
    "soil":      SoilMoistureDriver,
    "water_level": WaterLevelDriver,
    "generic":   GenericDriver,
}


def make_driver(sensor_cfg):
    """Instantiate the correct driver for a sensor config entry."""
    cls = DRIVER_MAP.get(sensor_cfg["type"], GenericDriver)
    return cls(sensor_cfg)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG  (load / save / defaults)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "name":           "Pixie frog enclosure",
    "subtitle":       "African pixie frog · Enclosure 1",
    "topbar_color":   "",
    "logo_mode":      "emoji",
    "logo_emoji":     "🐸",
    "logo_image":     "",
    "boot_layout":    "full",
    "profile":        "tropical_frog",
    "relay_labels": PROFILES["tropical_frog"]["relay_labels"],
    "relay_icons":  PROFILES["tropical_frog"]["relay_icons"],
    "sensors":      PROFILES["tropical_frog"]["sensors"],
    "theme":        "green",
    "custom_theme": {},
    "theme_rotation": {
        "enabled": True,
        "fade_enabled": True,
        "fade_days": 7,
        "rules": [
            {"id": 1, "theme": "newyear",    "from": "01-01", "to": "01-07"},
            {"id": 2, "theme": "valentines", "from": "02-01", "to": "02-14"},
            {"id": 3, "theme": "stpatricks", "from": "03-10", "to": "03-17"},
            {"id": 4, "theme": "spring",     "from": "03-20", "to": "06-20"},
            {"id": 5, "theme": "easter",     "from": "04-01", "to": "04-20"},
            {"id": 6, "theme": "summer",     "from": "06-21", "to": "09-22"},
            {"id": 7, "theme": "autumn",     "from": "09-23", "to": "12-14"},
            {"id": 8, "theme": "halloween",  "from": "10-15", "to": "10-31"},
            {"id": 9, "theme": "christmas",  "from": "12-01", "to": "12-31"},
        ]
    },
    "spk_style":    "line",
    "spk_thresh_color": True,
    "spk_sensor_colors": {
        "dht11":      "#4ade80",
        "dht22":      "#4ade80",
        "co2":        "#67e8f9",
        "uv":         "#fbbf24",
        "soil":       "#34d399",
        "water_level":"#67e8f9",
        "ph":         "#fbbf24",
        "ammonia":    "#c084fc",
        "nitrite":    "#f87171",
        "nitrate":    "#fb923c",
        "chlorine":   "#a78bfa",
        "tds":        "#86efac",
        "hardness":   "#67e8f9",
        "carbonate":  "#34d399",
        "generic":    "#4ade80",
    },
    "layout":       "left",
    "card_size":    "normal",
    "idle_bg":      "gif",
    "idle_color":   "#0a1a0c",
    "boot_accent":  "green",
    "boot_sound":   "forest",
    "warn_sound":   "soft_ping",
    "crit_sound":   "triple_blip",
    "clock_format": "24",
    "night_dim":    True,
    "night_from":   "22:00",
    "night_to":     "07:00",
    "night_theme":  "",
    "day_night_auto": True,
    "day_night_mode": "day",
    "idle_reading_1": "",
    "idle_reading_2": "",
    "time_format":  "24",
    "timezone":     "UTC",
    "relay_schedules": [],
    "reminders":    [],
}


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            saved = json.load(f)
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(saved)
        # Ensure sensors list exists
        if "sensors" not in cfg or not cfg["sensors"]:
            cfg["sensors"] = DEFAULT_CONFIG["sensors"]
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[CONFIG] Saved to {CONFIG_PATH}")


config = load_config()


# ─────────────────────────────────────────────────────────────────────────────
# GPIO / RELAY SETUP
# ─────────────────────────────────────────────────────────────────────────────

def setup_gpio():
    if not ON_PI:
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in RELAY_PINS.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)   # active-low: HIGH = OFF


def cleanup_gpio():
    if ON_PI:
        GPIO.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# SHARED STATE
# ─────────────────────────────────────────────────────────────────────────────

state_lock = threading.Lock()

state = {
    "sensors":    {},   # {sensor_id: {values: {key: val}, averages: {key: val}, ok: bool, last_read: str}}
    "relays":     {"ch1": False, "ch2": False, "ch3": False, "ch4": False},
    "last_read":  None,
    "any_alert":  False,
}

# Rolling average buffers  {sensor_id: {reading_key: deque}}
_avg_bufs = {}


def get_or_create_buf(sensor_id, key):
    if sensor_id not in _avg_bufs:
        _avg_bufs[sensor_id] = {}
    if key not in _avg_bufs[sensor_id]:
        _avg_bufs[sensor_id][key] = deque(maxlen=AVG_WINDOW)
    return _avg_bufs[sensor_id][key]


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE  (dynamic schema — stores sensor readings as JSON)
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            sensor_id   TEXT NOT NULL,
            sensor_name TEXT,
            readings    TEXT NOT NULL,
            relay_ch1   INTEGER,
            relay_ch2   INTEGER,
            relay_ch3   INTEGER,
            relay_ch4   INTEGER
        )
    """)
    conn.commit()
    conn.close()
    print(f"[DB] Database ready at {DB_PATH}")


def log_all_readings():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        ts  = datetime.now().isoformat()
        with state_lock:
            relays = dict(state["relays"])
            sensors_snap = {sid: dict(sv) for sid, sv in state["sensors"].items()}

        for sid, sv in sensors_snap.items():
            if not sv.get("ok"):
                continue
            # Find sensor name from config
            s_cfg = next((s for s in config.get("sensors", []) if s["id"] == sid), {})
            name  = s_cfg.get("name", sid)
            c.execute("""
                INSERT INTO readings
                    (timestamp, sensor_id, sensor_name, readings,
                     relay_ch1, relay_ch2, relay_ch3, relay_ch4)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts, sid, name,
                json.dumps(sv.get("values", {})),
                int(relays.get("ch1", False)),
                int(relays.get("ch2", False)),
                int(relays.get("ch3", False)),
                int(relays.get("ch4", False)),
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Log error: {e}")


def get_recent_readings(hours=24):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM readings
            WHERE timestamp >= datetime('now', ?)
            ORDER BY timestamp DESC
            LIMIT 2000
        """, (f"-{hours} hours",))
        rows = []
        for r in c.fetchall():
            row = dict(r)
            try:
                row["readings"] = json.loads(row["readings"])
            except Exception:
                pass
            rows.append(row)
        conn.close()
        return rows
    except Exception as e:
        print(f"[DB] Read error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SENSOR LOOP
# ─────────────────────────────────────────────────────────────────────────────

def check_alerts(sensor_id, values):
    """Return True if any reading is outside its threshold."""
    s_cfg = next((s for s in config.get("sensors", []) if s["id"] == sensor_id), None)
    if not s_cfg:
        return False
    for r in s_cfg.get("readings", []):
        v = values.get(r["key"])
        if v is None:
            continue
        if v < r.get("min", float("-inf")) or v > r.get("max", float("inf")):
            return True
    return False


def sensor_loop():
    last_log_time = 0
    drivers = {}

    while True:
        # Rebuild drivers if sensor config has changed
        sensor_cfgs = config.get("sensors", [])
        current_ids = {s["id"] for s in sensor_cfgs if s.get("enabled")}
        driver_ids  = set(drivers.keys())

        for sid in driver_ids - current_ids:
            del drivers[sid]
        for s_cfg in sensor_cfgs:
            if s_cfg.get("enabled") and s_cfg["id"] not in drivers:
                drivers[s_cfg["id"]] = make_driver(s_cfg)

        # Read all active sensors
        any_alert = False
        for sid, driver in drivers.items():
            try:
                values = driver.read()
            except Exception as e:
                print(f"[SENSOR:{sid}] Unexpected error: {e}")
                values = None

            if values is None:
                with state_lock:
                    if sid not in state["sensors"]:
                        state["sensors"][sid] = {}
                    state["sensors"][sid]["ok"] = False
                continue

            # Update rolling averages
            averages = {}
            for key, val in values.items():
                buf = get_or_create_buf(sid, key)
                buf.append(val)
                averages[key] = round(sum(buf) / len(buf), 3)

            ts = datetime.now().isoformat()
            with state_lock:
                state["sensors"][sid] = {
                    "values":    values,
                    "averages":  averages,
                    "ok":        True,
                    "last_read": ts,
                }

            if check_alerts(sid, averages):
                any_alert = True

            # Print summary
            summary = "  ".join(f"{k}={v}" for k, v in values.items())
            print(f"[SENSOR:{sid}] {summary}")

        with state_lock:
            state["any_alert"]  = any_alert
            state["last_read"]  = datetime.now().isoformat()

        # Enforce relay schedules
        _enforce_relay_schedules()

        # Log to SQLite on interval
        now = time.time()
        if now - last_log_time >= LOG_INTERVAL_SECONDS:
            log_all_readings()
            print("[DB] Logged reading")
            last_log_time = now

        time.sleep(READ_INTERVAL_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# RELAY SCHEDULE ENFORCEMENT
# ─────────────────────────────────────────────────────────────────────────────

_DOW_MAP = {"sun":6,"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5}

def _enforce_relay_schedules():
    """Called every sensor loop — turns relays on/off per schedule."""
    global config
    schedules = config.get("relay_schedules", [])
    if not schedules:
        return
    now = datetime.now()
    dow = now.weekday()          # 0=Mon … 6=Sun
    hhmm = now.strftime("%H:%M")

    for sched in schedules:
        if not sched.get("enabled", False):
            continue
        ch = sched.get("channel")
        if not ch:
            continue
        days = sched.get("days", [])  # list of "mon","tue",…
        if dow not in [_DOW_MAP.get(d, -1) for d in days]:
            continue
        # Check each on/off window
        desired = None
        for window in sched.get("windows", []):
            on_t  = window.get("on",  "")
            off_t = window.get("off", "")
            if not on_t or not off_t:
                continue
            if on_t <= off_t:
                if on_t <= hhmm < off_t:
                    desired = True
                elif hhmm >= off_t and desired is None:
                    desired = False
            else:  # overnight window
                if hhmm >= on_t or hhmm < off_t:
                    desired = True

        if desired is None:
            desired = False

        current = state.get("relays", {}).get(ch, False)
        if desired != current:
            with state_lock:
                state["relays"][ch] = desired
            _set_relay_hw(ch, desired)
            print(f"[SCHED] Relay {ch} → {'ON' if desired else 'OFF'} by schedule")


def _set_relay_hw(channel, on: bool):
    """Drive the GPIO pin for a relay channel."""
    if not ON_PI:
        return
    pin_map = {"ch1": RELAY_PINS.get("ch1"), "ch2": RELAY_PINS.get("ch2"),
               "ch3": RELAY_PINS.get("ch3"), "ch4": RELAY_PINS.get("ch4")}
    pin = pin_map.get(channel)
    if pin:
        GPIO.output(pin, GPIO.LOW if on else GPIO.HIGH)


# ─────────────────────────────────────────────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static")


@app.route("/history")
def history():
    cfg = config
    return render_template("history.html",
                           name=cfg.get("name", DEFAULT_CONFIG["name"]),
                           version=HABITATOS_VERSION,
                           codename=HABITATOS_CODENAME,
                           topbar_color=cfg.get("topbar_color", DEFAULT_CONFIG["topbar_color"]),
                           sensors=cfg.get("sensors", DEFAULT_CONFIG["sensors"]))


@app.route("/boot")
def boot():
    cfg = config
    return render_template("boot.html",
                           name=cfg.get("name",           DEFAULT_CONFIG["name"]),
                           subtitle=cfg.get("subtitle",   DEFAULT_CONFIG["subtitle"]),
                           logo_mode=cfg.get("logo_mode", DEFAULT_CONFIG["logo_mode"]),
                           logo_emoji=cfg.get("logo_emoji", DEFAULT_CONFIG["logo_emoji"]),
                           boot_layout=cfg.get("boot_layout", DEFAULT_CONFIG["boot_layout"]),
                           boot_accent=cfg.get("boot_accent", DEFAULT_CONFIG.get("boot_accent","green")),
                           boot_sound=cfg.get("boot_sound",   DEFAULT_CONFIG["boot_sound"]),
                           active_profile=cfg.get("profile",  DEFAULT_CONFIG["profile"]),
                           sensors=cfg.get("sensors",         DEFAULT_CONFIG["sensors"]),
                           version=HABITATOS_VERSION,
                           codename=HABITATOS_CODENAME)


@app.route("/console")
def console():
    return render_template("console.html")


@app.route("/")
def index():
    cfg = config
    return render_template("index.html",
                           name=cfg.get("name",           DEFAULT_CONFIG["name"]),
                           subtitle=cfg.get("subtitle",   DEFAULT_CONFIG["subtitle"]),
                           topbar_color=cfg.get("topbar_color", DEFAULT_CONFIG["topbar_color"]),
                           logo_mode=cfg.get("logo_mode", DEFAULT_CONFIG["logo_mode"]),
                           logo_emoji=cfg.get("logo_emoji", DEFAULT_CONFIG["logo_emoji"]),
                           logo_image=cfg.get("logo_image", DEFAULT_CONFIG["logo_image"]),
                           boot_layout=cfg.get("boot_layout", DEFAULT_CONFIG["boot_layout"]),
                           idle_timeout=IDLE_TIMEOUT_SECONDS,
                           theme=cfg.get("theme",         DEFAULT_CONFIG["theme"]),
                           custom_theme=cfg.get("custom_theme", DEFAULT_CONFIG["custom_theme"]),
                           theme_rotation=cfg.get("theme_rotation", DEFAULT_CONFIG["theme_rotation"]),
                           version=HABITATOS_VERSION,
                           codename=HABITATOS_CODENAME,
                           spk_style=cfg.get("spk_style", DEFAULT_CONFIG["spk_style"]),
                           spk_thresh_color=cfg.get("spk_thresh_color", DEFAULT_CONFIG["spk_thresh_color"]),
                           spk_sensor_colors=cfg.get("spk_sensor_colors", DEFAULT_CONFIG["spk_sensor_colors"]),
                           layout=cfg.get("layout",       DEFAULT_CONFIG["layout"]),
                           card_size=cfg.get("card_size", DEFAULT_CONFIG["card_size"]),
                           idle_bg=cfg.get("idle_bg",     DEFAULT_CONFIG["idle_bg"]),
                           idle_color=cfg.get("idle_color",DEFAULT_CONFIG["idle_color"]),
                           idle_reading_1=cfg.get("idle_reading_1", ""),
                           idle_reading_2=cfg.get("idle_reading_2", ""),
                           time_format=cfg.get("time_format", "24"),
                           timezone=cfg.get("timezone", "UTC"),
                           night_dim=cfg.get("night_dim",   DEFAULT_CONFIG["night_dim"]),
                           night_from=cfg.get("night_from", DEFAULT_CONFIG["night_from"]),
                           night_to=cfg.get("night_to",     DEFAULT_CONFIG["night_to"]),
                           night_theme=cfg.get("night_theme", ""),
                           day_night_auto=cfg.get("day_night_auto", True),
                           day_night_mode=cfg.get("day_night_mode", "day"),
                           relay_labels=cfg.get("relay_labels", DEFAULT_CONFIG["relay_labels"]),
                           relay_icons=cfg.get("relay_icons",   DEFAULT_CONFIG["relay_icons"]),
                           sensors=cfg.get("sensors",     DEFAULT_CONFIG["sensors"]),
                           active_profile=cfg.get("profile", DEFAULT_CONFIG["profile"]),
                           warn_sound=cfg.get("warn_sound", DEFAULT_CONFIG["warn_sound"]),
                           crit_sound=cfg.get("crit_sound", DEFAULT_CONFIG["crit_sound"]),
                           relay_schedules=cfg.get("relay_schedules", []),
                           reminders=cfg.get("reminders", []))


# ── Sensor API ────────────────────────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    """Current readings, averages, and relay states."""
    with state_lock:
        return jsonify(state)


@app.route("/api/sensors", methods=["GET"])
def api_sensors_get():
    """Return sensor config list."""
    return jsonify(config.get("sensors", []))


@app.route("/api/sensors", methods=["POST"])
def api_sensors_post():
    """Replace full sensor config list."""
    global config
    data = request.get_json(silent=True)
    if not isinstance(data, list):
        return jsonify({"error": "Expected a JSON array of sensor configs"}), 400
    config["sensors"] = data
    save_config(config)
    print(f"[CONFIG] Sensor config updated — {len(data)} sensors")
    return jsonify({"ok": True, "count": len(data)})


@app.route("/api/sensors/<sensor_id>", methods=["PATCH"])
def api_sensor_patch(sensor_id):
    """Update a single sensor's config by id."""
    global config
    data  = request.get_json(silent=True) or {}
    found = False
    for s in config.get("sensors", []):
        if s["id"] == sensor_id:
            s.update(data)
            found = True
            break
    if not found:
        return jsonify({"error": f"Sensor {sensor_id} not found"}), 404
    save_config(config)
    return jsonify({"ok": True})


@app.route("/api/sensors/<sensor_id>", methods=["DELETE"])
def api_sensor_delete(sensor_id):
    """Remove a sensor from config."""
    global config
    before = len(config.get("sensors", []))
    config["sensors"] = [s for s in config.get("sensors", []) if s["id"] != sensor_id]
    if len(config["sensors"]) == before:
        return jsonify({"error": f"Sensor {sensor_id} not found"}), 404
    save_config(config)
    # Clean up state
    with state_lock:
        state["sensors"].pop(sensor_id, None)
    return jsonify({"ok": True})


@app.route("/api/sensors/<sensor_id>/calibrate", methods=["POST"])
def api_sensor_calibrate(sensor_id):
    """Save calibration offsets for a sensor.  Body: {key_offset: float, ...}"""
    global config
    data = request.get_json(silent=True) or {}
    for s in config.get("sensors", []):
        if s["id"] == sensor_id:
            if "calibration" not in s:
                s["calibration"] = {}
            s["calibration"].update(data)
            save_config(config)
            print(f"[CALIB] {sensor_id}: {data}")
            return jsonify({"ok": True, "calibration": s["calibration"]})
    return jsonify({"error": f"Sensor {sensor_id} not found"}), 404


# ── Profile API ───────────────────────────────────────────────────────────────

@app.route("/api/version")
def api_version():
    return jsonify({
        "version":  HABITATOS_VERSION,
        "codename": HABITATOS_CODENAME,
        "full":     f"HabitatOS v{HABITATOS_VERSION} · {HABITATOS_CODENAME}",
    })


@app.route("/api/profiles", methods=["GET"])
def api_profiles():
    """Return available profile names and labels."""
    return jsonify([{"id": k, "label": v["label"]} for k, v in PROFILES.items()])


@app.route("/api/profiles/<profile_id>/apply", methods=["POST"])
def api_profile_apply(profile_id):
    """Apply a profile — sets sensors, relay labels/icons.
    Optional body: {"keep_sensors": true} to merge rather than replace sensors."""
    global config
    if profile_id not in PROFILES:
        return jsonify({"error": f"Unknown profile: {profile_id}"}), 404
    p    = PROFILES[profile_id]
    data = request.get_json(silent=True) or {}
    config["profile"]      = profile_id
    config["relay_labels"] = p["relay_labels"]
    config["relay_icons"]  = p["relay_icons"]
    if not data.get("keep_sensors"):
        config["sensors"] = p["sensors"]
    save_config(config)
    print(f"[PROFILE] Applied: {profile_id}")
    return jsonify({"ok": True, "profile": profile_id})


# ── Relay API ─────────────────────────────────────────────────────────────────

@app.route("/api/relay/<channel>", methods=["POST"])
def api_relay(channel):
    """Toggle or set a relay channel (ch1–ch4).
    POST body: {"on": true} or {"on": false} or empty to toggle."""
    if channel not in RELAY_PINS:
        return jsonify({"error": f"Unknown channel: {channel}"}), 400
    data = request.get_json(silent=True) or {}
    with state_lock:
        if "on" in data:
            new_state = bool(data["on"])
        else:
            new_state = not state["relays"].get(channel, False)
        state["relays"][channel] = new_state
    if ON_PI:
        GPIO.output(RELAY_PINS[channel], GPIO.LOW if new_state else GPIO.HIGH)
    print(f"[RELAY] {channel} → {'ON' if new_state else 'OFF'}")
    return jsonify({"channel": channel, "on": new_state})


# ── Config API ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(config)


@app.route("/api/config", methods=["POST"])
def api_config_post():
    global config
    data = request.get_json(silent=True) or {}
    config.update(data)
    save_config(config)
    print(f"[CONFIG] Updated: {list(data.keys())}")
    return jsonify({"ok": True, "config": config})


# ── History API ───────────────────────────────────────────────────────────────

@app.route("/api/history")
def api_history():
    hours = int(request.args.get("hours", 24))
    return jsonify(get_recent_readings(hours))


@app.route("/api/datetime", methods=["GET"])
def api_datetime_get():
    """Return current system date/time and config time settings."""
    global config
    now = datetime.now()
    return jsonify({
        "year":  now.year,
        "month": now.month,
        "day":   now.day,
        "hour":  now.hour,
        "minute": now.minute,
        "second": now.second,
        "iso":    now.isoformat(),
        "time_format": config.get("time_format", "24"),
        "timezone":    config.get("timezone", "UTC"),
    })


@app.route("/api/datetime", methods=["POST"])
def api_datetime_set():
    """Set system date/time and persist time format/timezone to config."""
    global config
    data = request.get_json(silent=True) or {}

    # Persist display preferences
    if "time_format" in data:
        config["time_format"] = data["time_format"]
    if "timezone" in data:
        config["timezone"] = data["timezone"]
    save_config(config)

    # Set system clock on Pi (silently skipped on Windows/non-Pi)
    if ON_PI and all(k in data for k in ("year","month","day","hour","minute")):
        try:
            import subprocess
            dt_str = f"{data['year']}-{str(data['month']).zfill(2)}-{str(data['day']).zfill(2)} {str(data['hour']).zfill(2)}:{str(data['minute']).zfill(2)}:00"
            subprocess.run(["sudo","date","-s", dt_str], check=True, capture_output=True)
            print(f"[DATETIME] Clock set to {dt_str}")
        except Exception as e:
            print(f"[DATETIME] Failed to set clock: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})


@app.route("/api/export-csv")
def api_export_csv():
    """Export all readings as a CSV file download."""
    hours = int(request.args.get("hours", 24))
    rows  = get_recent_readings(hours)

    # Collect all unique reading keys across all rows
    all_keys = []
    seen = set()
    for row in rows:
        for k in (row.get("readings") or {}).keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    header = ["timestamp","sensor_id","sensor_name"] + all_keys + ["relay_ch1","relay_ch2","relay_ch3","relay_ch4"]
    lines  = [",".join(header)]
    for row in rows:
        vals = [
            row.get("timestamp",""),
            row.get("sensor_id",""),
            row.get("sensor_name",""),
        ] + [str((row.get("readings") or {}).get(k,"")) for k in all_keys] + [
            str(row.get("relay_ch1","")),
            str(row.get("relay_ch2","")),
            str(row.get("relay_ch3","")),
            str(row.get("relay_ch4","")),
        ]
        lines.append(",".join(vals))

    csv_text = "\n".join(lines)
    from flask import Response
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=enclosure_log.csv"}
    )


# ── Relay Schedules API ───────────────────────────────────────────────────────

@app.route("/api/relay-schedules", methods=["GET"])
def api_relay_schedules_get():
    return jsonify(config.get("relay_schedules", []))

@app.route("/api/relay-schedules", methods=["POST"])
def api_relay_schedules_set():
    global config
    data = request.get_json(silent=True) or {}
    config["relay_schedules"] = data.get("schedules", [])
    save_config(config)
    return jsonify({"ok": True})


# ── Reminders API ─────────────────────────────────────────────────────────────

@app.route("/api/reminders", methods=["GET"])
def api_reminders_get():
    return jsonify(config.get("reminders", []))

@app.route("/api/reminders", methods=["POST"])
def api_reminders_set():
    global config
    data = request.get_json(silent=True) or {}
    config["reminders"] = data.get("reminders", [])
    save_config(config)
    return jsonify({"ok": True})

@app.route("/api/reminders/<int:rid>/done", methods=["POST"])
def api_reminder_done(rid):
    """Mark a specific reminder occurrence as done."""
    global config
    data = request.get_json(silent=True) or {}
    time_key = data.get("time_key", "")  # e.g. "08:00"
    reminders = config.get("reminders", [])
    for r in reminders:
        if r.get("id") == rid:
            if "last_done" not in r:
                r["last_done"] = {}
            r["last_done"][time_key] = datetime.now().isoformat()
            break
    config["reminders"] = reminders
    save_config(config)
    return jsonify({"ok": True})


# ── Upload API ────────────────────────────────────────────────────────────────

@app.route("/api/upload-idle-bg", methods=["POST"])
def upload_idle_bg():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    ext  = os.path.splitext(f.filename)[1].lower() or ".jpg"
    dest = os.path.join("static", "idle_bg" + ext)
    f.save(dest)
    print(f"[UPLOAD] Idle background saved to {dest}")
    return jsonify({"ok": True, "path": "/" + dest})


# ── System API ────────────────────────────────────────────────────────────────

@app.route("/api/system")
def api_system():
    """Pi system stats — CPU temp, memory, uptime, WiFi."""
    import subprocess, re
    info = {}
    # CPU temp
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            info["cpu_temp_c"] = round(int(f.read()) / 1000, 1)
    except Exception:
        info["cpu_temp_c"] = round(random.uniform(48, 58), 1)
    # Memory
    try:
        out = subprocess.check_output(["free", "-m"], text=True)
        m   = re.search(r"Mem:\s+(\d+)\s+(\d+)", out)
        if m:
            total = int(m.group(1)); used = int(m.group(2))
            info["memory_used_mb"]  = used
            info["memory_total_mb"] = total
            info["memory_pct"]      = round(used / total * 100, 1) if total else 0
    except Exception:
        info["memory_used_mb"]  = random.randint(800, 1400)
        info["memory_total_mb"] = 7900
        info["memory_pct"]      = round(info["memory_used_mb"] / info["memory_total_mb"] * 100, 1)
    # Uptime
    try:
        out = subprocess.check_output(["cat", "/proc/uptime"], text=True)
        secs = int(float(out.split()[0]))
        h, m2 = divmod(secs, 3600); m2, s = divmod(m2, 60)
        info["uptime"] = f"{h}h {m2}m {s}s"
    except Exception:
        info["uptime"] = "2h 3m"
    # IP
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True)
        info["ip"] = out.strip().split()[0]
    except Exception:
        info["ip"] = "192.168.1.42"
    # WiFi
    try:
        ssid = subprocess.check_output(["iwgetid", "-r"], text=True).strip()
        out2 = subprocess.check_output(["iwconfig", "wlan0"], text=True)
        m2   = re.search(r"Signal level=(-\d+)", out2)
        info["wifi_signal"] = int(m2.group(1)) if m2 else None
        info["wifi_ssid"]   = ssid
    except Exception:
        info["wifi_signal"] = -52
        info["wifi_ssid"]   = "FrogLAN"
    info["version"]  = HABITATOS_VERSION
    info["codename"] = HABITATOS_CODENAME
    return jsonify(info)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sensor_count = len([s for s in config.get("sensors", []) if s.get("enabled")])
    print("=" * 52)
    print("  Pixie Frog Enclosure Monitor v1.0")
    print(f"  Profile:        {config.get('profile', 'custom')}")
    print(f"  Active sensors: {sensor_count}")
    print(f"  Running on Pi:  {ON_PI}")
    print(f"  Log interval:   {LOG_INTERVAL_SECONDS}s")
    print(f"  Idle timeout:   {IDLE_TIMEOUT_SECONDS}s")
    print("=" * 52)

    setup_gpio()
    init_db()

    sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
    sensor_thread.start()
    print("[SENSOR] Sensor loop started")

    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    finally:
        cleanup_gpio()
        print("[GPIO] Cleaned up. Goodbye.")
