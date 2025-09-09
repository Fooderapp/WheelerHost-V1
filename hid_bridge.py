# hid_bridge.py
"""
Custom HID gamepad bridge for Windows.
Implements a virtual HID device for gamepad emulation, as an alternative to ViGEm.
"""


import logging
import pywinusb.hid as hid

class HIDBridge:
    def __init__(self):
        self.available = False
        self.device = None
        self.report = None
        self._init_device()

    def _init_device(self):
        try:
            # Find a custom Wheeler virtual gamepad device (by VID/PID or usage)
            all_devices = hid.HidDeviceFilter().get_devices()
            for dev in all_devices:
                # Replace with your custom VID/PID or usage_page/usage
                if dev.vendor_id == 0x1234 and dev.product_id == 0x5678:
                    self.device = dev
                    break
            if self.device:
                self.device.open()
                self.report = self.device.find_output_reports()[0]
                self.available = True
            else:
                logging.warning("No Wheeler HID gamepad device found.")
        except Exception as e:
            logging.warning(f"⚠️ HID device unavailable: {e}")
            self.available = False

    def send_state(self, lx, ly, rt, lt, buttons):
        if not self.available or not self.report:
            return
        try:
            # Example: Pack state into HID report (update with your descriptor)
            # This assumes a simple report: [lx, ly, rt, lt, buttons]
            data = [int(lx * 127), int(ly * 127), int(rt), int(lt), int(buttons & 0xFF)]
            self.report.set_raw_data(data)
            self.report.send()
        except Exception as e:
            logging.warning(f"⚠️ HID send_state error: {e}")

    def set_feedback_callback(self, cb):
        # TODO: Implement force feedback callback if supported
        pass

    def close(self):
        try:
            if self.device:
                self.device.close()
        except Exception:
            pass
