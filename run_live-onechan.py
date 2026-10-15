import larpix
import larpix.io
import argparse
# from base import utility_base
import larpix.format.rawhdf5format as rhdf5
import time
import larpix.format.pacman_msg_format as pacman_msg_fmt
import network_5x5
import pickle
from util import save_controller, load_controller #, data
import numpy as np
from larpix.packet import PacketCollection
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets
from tqdm import tqdm      
from collections import deque
from larpix.packet.packet_v3 import Packet_v3

_default_periodic_trigger_cycles=150000 ##400000 ## 100000
_default_periodic_reset_cycles=4 #4096 ## 512
_default_vref_dac=185 ###cold 220 ### warm 185
_default_duration=200
_default_data_dir='data/'

cbar_lo = 0
cbar_hi = 1


def now():
    return time.strftime("%Y_%m_%d_%H_%M_%S_%Z")

class OscilloscopeGUI:
    def __init__(self, controller, runtime, data_dir=_default_data_dir, fname=None, tag=None):
        self.c = controller
        self.runtime = runtime
        self.data_dir = data_dir

        if fname is None:
            if tag is not None:
                fname = data_dir + '/{}-packet-'.format(tag) + now() + '.h5'
            else:
                fname = data_dir + '/packet-' + now() + '.h5'

        self.c.logger = larpix.logger.HDF5Logger(filename=fname)
        self.c.reads.clear()
        self.c.io.reset_larpix(length=16)

        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

        self.window = QtWidgets.QWidget()
        self.window.setWindowTitle("LArPix Channel Oscilloscope")
        self.window.resize(1100, 700)

        self.layout = QtWidgets.QVBoxLayout(self.window)

        # -------------------------
        # Controls
        # -------------------------
        controls_layout = QtWidgets.QHBoxLayout()

        self.chip_label = QtWidgets.QLabel("Chip:")
        self.chip_combo = QtWidgets.QComboBox()
        self.chip_keys = list(self.c.chips.keys())
        self.chip_keys.sort(key=str)
        self.chip_combo.addItems([str(key) for key in self.chip_keys])

        self.channel_label = QtWidgets.QLabel("Channel:")
        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.addItems([str(i) for i in range(64)])

        self.high_dac_label = QtWidgets.QLabel("High DAC:")
        self.high_dac_spin = QtWidgets.QSpinBox()
        self.high_dac_spin.setRange(0, 255)
        self.high_dac_spin.setValue(88)
        self.high_dac = self.high_dac_spin.value()

        self.pause_checkbox = QtWidgets.QCheckBox("Pause")
        self.clear_button = QtWidgets.QPushButton("Clear")
        self.testpulse_button = QtWidgets.QPushButton("Fire Testpulse")

        controls_layout.addWidget(self.chip_label)
        controls_layout.addWidget(self.chip_combo)
        controls_layout.addWidget(self.channel_label)
        controls_layout.addWidget(self.channel_combo)
        controls_layout.addWidget(self.high_dac_label)
        controls_layout.addWidget(self.high_dac_spin)
        controls_layout.addWidget(self.pause_checkbox)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.testpulse_button)
        controls_layout.addStretch()

        self.layout.addLayout(controls_layout)

        # -------------------------
        # Plot
        # -------------------------
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Dataword')
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setTitle("Selected Chip/Channel Trace")
        self.ymax = 255
        self.plot_widget.setYRange(0, self.ymax)
        self.layout.addWidget(self.plot_widget)

        self.curve = self.plot_widget.plot(
            pen=pg.mkPen('y', width=2),
            symbol=None
        )

        # -------------------------
        # Status
        # -------------------------
        self.status_label = QtWidgets.QLabel("Waiting for data...")
        self.layout.addWidget(self.status_label)

        self.window.show()

        # -------------------------
        # Data/state
        # -------------------------
        self.window_seconds = 10.0
        self.sample_interval = 0.05
        self.max_points = int(self.window_seconds / self.sample_interval) + 5

        self.time_buffer = deque(maxlen=self.max_points)
        self.value_buffer = deque(maxlen=self.max_points)

        self.start_time = None
        self.pending_value = None
        self.pending_matches = 0

        self.channel_colors = {
            ch: pg.intColor(ch, hues=64) for ch in range(64)
        }

        self.apply_channel_color()

        # -------------------------
        # Signals
        # -------------------------
        self.clear_button.clicked.connect(self.clear_trace)
        self.testpulse_button.clicked.connect(self.fire_selected_testpulse)
        self.channel_combo.currentIndexChanged.connect(self.on_channel_changed)
        self.chip_combo.currentIndexChanged.connect(self.on_chip_changed)
        self.high_dac_spin.valueChanged.connect(self.on_high_dac_changed)

        # Make sure only one monitor is active
        self.set_selected_monitor()

    def update_y_range(self, y):
        if y > self.ymax:
            self.ymax = max(self.ymax, y * 1.2)
            self.plot_widget.setYRange(0, self.ymax)

    def selected_chip(self):
        return self.chip_keys[self.chip_combo.currentIndex()]

    def selected_chip_str(self):
        return str(self.selected_chip())

    def selected_channel(self):
        return int(self.channel_combo.currentText())

    def clear_trace(self):
        self.time_buffer.clear()
        self.value_buffer.clear()
        self.curve.setData([], [])
        self.ymax = 255
        self.plot_widget.setYRange(0, self.ymax)

    def apply_channel_color(self):
        ch = self.selected_channel()
        color = self.channel_colors[ch]
        self.curve.setPen(pg.mkPen(color, width=2))

    def on_high_dac_changed(self, value):
        self.high_dac = int(value)
        print(f"High DAC set to {self.high_dac}")

    def set_selected_monitor(self):
        key = self.selected_chip()
        channel = self.selected_channel()
        print(f"Switching monitor to chip={key}, channel={channel}")
        monitor_off(self.c, self.c.chips.keys())
        monitor_on(self.c, channel=channel, key=key)

    def fire_selected_testpulse(self):
        key = self.selected_chip()
        channel = self.selected_channel()
        print(f"Firing testpulse: chip={key}, channel={channel}, high_dac={self.high_dac}")
        testpulse(self.c, high_dac=self.high_dac, channel=channel, key=key)

    def on_channel_changed(self):
        self.clear_trace()
        self.apply_channel_color()
        self.set_selected_monitor()

    def on_chip_changed(self):
        self.clear_trace()
        self.apply_channel_color()
        self.set_selected_monitor()

    def process_packets(self, read_packets, read_bytestream):
        self.pending_value = None
        self.pending_matches = 0

        if len(read_packets) == 0:
            return

        paks = PacketCollection(read_packets, read_bytestream, message='data')

        try:
            pi = paks.to_dict()
        except UnicodeDecodeError as e:
            print("UnicodeDecodeError while decoding packet collection")
            print("packets:", len(read_packets))
            print("bytestream length:", len(read_bytestream))
            print("bytestream tail:", repr(read_bytestream[-50:]))
            print("error:", e)
            return

        sel_chip_str = self.selected_chip_str()
        sel_channel = self.selected_channel()

        matched = 0
        latest_value = None

        for packet in pi['packets'][1:]:
            chipid = packet.get('chip_key')
            channel = packet.get('channel_id')
            value = packet.get('dataword')

            if chipid is None or channel is None or value is None:
                continue

            if str(chipid) == sel_chip_str and int(channel) == sel_channel:
                latest_value = float(value)
                matched += 1

        self.pending_value = latest_value
        self.pending_matches = matched

        print(f"Read returned {len(pi['packets'])} packets, matched {matched}")

    def update_trace(self):
        if self.start_time is None:
            return

        if self.pause_checkbox.isChecked():
            return

        t = time.time() - self.start_time
        y = 0.0 if self.pending_value is None else self.pending_value

        self.update_y_range(y)

        self.time_buffer.append(t)
        self.value_buffer.append(y)

        self.curve.setData(list(self.time_buffer), list(self.value_buffer))
        self.plot_widget.setXRange(max(0, t - self.window_seconds), t)

        self.status_label.setText(
            f"Chip={self.selected_chip_str()}, "
            f"Channel={self.selected_channel()}, "
            f"High DAC={self.high_dac}, "
            f"last={y}, matches_this_cycle={self.pending_matches}"
        )

    def run(self):
        self.c.start_listening()
        self.start_time = time.time()

        end_time = self.start_time + self.runtime

        try:
            while time.time() < end_time:
                self.app.processEvents()
                time.sleep(self.sample_interval)

                read_packets, read_bytestream = self.c.read()
                self.process_packets(read_packets, read_bytestream)
                self.update_trace()

                self.app.processEvents()

        finally:
            monitor_off(self.c, self.c.chips.keys())
            self.c.stop_listening()
            self.c.logger.disable()
            print("Run Finished")


        
def oscilloscope_data(c, runtime, data_dir=_default_data_dir, fname=None, tag=None):
    gui = OscilloscopeGUI(c, runtime, data_dir=data_dir, fname=fname, tag=tag)
    gui.run()


def unmask(c, keys):
    for i in range(10):
        for key in reversed(keys):

            c[key].config.csa_enable= [1]*64
            c[key].config.channel_mask= [1]*64
            c[key].config.periodic_trigger_mask=[0]*64
            c.write_configuration(key, 'periodic_trigger_mask')
            c.write_configuration(key, 'csa_enable')
            c.write_configuration(key, 'channel_mask')
            
def config(c, register, value, key):
    setattr(c[key].config, register, value)
    c.write_configuration(key, register)

def convert_io_channel_to_uart(io_channel):
    io_channel_to_uart = {1:1, 2:2, 3:3, 4:4,
                         5:5, 6:6, 7:7, 8:8,
                         9:9, 10:10, 11:11, 12:None,
                         13:12, 14:13, 15:14, 16:None,
                         17:15, 18:16, 19:17, 20:None,
                         21:18, 22:19, 23:20, 24:None,
                         25:21, 26:22, 27:23, 28:None,
                         29:24, 30:25, 31:26, 32:None,
                         33:27, 34:28, 35:29, 36:None,
                         37:30, 38:31, 39:32, 40:None
                         }
    return io_channel_to_uart[io_channel]


def enable_pacman_uart_from_io_channel(io, io_group, io_channel):
    bits=list('11111111111111111111111111111111')

    uart=None
    if type(io_channel) is int: 
        uart = [convert_io_channel_to_uart(io_channel)]      
    elif type(io_channel) is list: 
        uart = [convert_io_channel_to_uart(io_ch) for io_ch in io_channel]
    
    if uart is None:
        return

    for u in uart:
        if u is None: continue
        bits[-1*u]='0'
    io.set_reg(0x201c, int("".join(bits),2), io_group=io_group)
    return

def testpulse(c, high_dac, channel, key):
    '''Sends a testpulse to the channel of choice'''
    #Unmask only the channel under test
    enable_pacman_uart_from_io_channel(
            c.io, 1, list(set([chip.io_channel for chip in c.chips])))
    
    low_dac = 0
    mask_list = [1]*64
    mask_list[channel] = 0


    
    config(c = c, register = 'channel_mask', value = mask_list, key = key)
    
    #Set test pulse DAC low 
    config(c, 'csa_testpulse_dac', low_dac, key)
    # time.sleep(0.05)
    
    
    #Set test pulse DAC high
    config(c, 'csa_testpulse_dac', high_dac, key)
    # time.sleep(0.05)
    
    
    #Fire test pulse
    #NOTE: csa_testpulse_enable IS ACTIVE LOW (0)
    config(c, 'csa_testpulse_enable', mask_list, key)
    # time.sleep(1)
    
    
    #Disable test pulse
    #NOTE: csa_testpulse_enable IS INACTIVE HIGH (1)
    config(c, 'csa_testpulse_enable', [1]*64, key)


def monitor_on(c, channel, key):
    '''Selects a channel to monitor through ADC Test Output'''
    #Unmask only the channel under test
    enable_pacman_uart_from_io_channel(
            c.io, 1, list(set([chip.io_channel for chip in c.chips])))
    
    mask_list = [0]*64 ## in this case, Active is high
    mask_list[channel] = 1

    # Tell the ASIC to enable the analog monitor
    config(c = c, register = 'en_analog_monitor', value = 1, key = key)

    # Start monitoring on a single channel
    config(c = c, register = 'csa_monitor_select', value = mask_list, key = key)

    '''Make sure to turn off monitoring before changing channels so as not to short things!'''

def monitor_off(c, keys):
    '''Turns off monitoring'''
    enable_pacman_uart_from_io_channel(
            c.io, 1, list(set([chip.io_channel for chip in c.chips])))
    
    mask_list = [0]*64 ## in this case, Active is high

    for key in keys:
        # Turn off all channel monitors
        config(c = c, register = 'csa_monitor_select', value = mask_list, key = key)
        
        # Tell the ASIC to disnable the analog monitor
        config(c = c, register = 'en_analog_monitor', value = 0, key = key)

    

def configuration(c, key, 
                    periodic_trigger_cycles, \
                    periodic_reset_cycles, \
                    vref_dac, \
                   ):
    #print(f"in enable_pedestal() key = [{key}]")
    c[key].config.enable_external_sync=1
    c.write_configuration(key, 'enable_external_sync')
    c[key].config.mark_first_packet = 0
    c.write_configuration(key, 'mark_first_packet')
    c[key].config.enable_periodic_trigger= 0 #1 #0 ## changed
    c[key].config.enable_rolling_periodic_trigger= 0 # 1 #0 ## changed
    c[key].config.enable_periodic_reset=1
    c[key].config.enable_rolling_periodic_reset= 1 # 0# 1 ## changed
    c[key].config.enable_hit_veto=1
    c[key].config.enable_periodic_trigger_veto=0

    c[key].config.threshold_global = 25 # 225# 25 ## changed
    c[key].config.periodic_trigger_cycles = periodic_trigger_cycles
    c[key].config.periodic_reset_cycles = periodic_reset_cycles

    c[key].config.dropped_packets = 15 ## added

    c[key].config.cds_mode=0
    c[key].config.enable_data_stats=0
    c[key].config.vref_dac= vref_dac

    c[key].config.ibias_vcm_buffer = 15
    c.write_configuration(key, 'ibias_vcm_buffer')

    c[key].config.adc_comp_trim = 2
    c.write_configuration(key, 'adc_comp_trim')

    #c[key].config.adc_ibias_delay = 15
    c[key].config.adc_ibias_delay = 7
    c.write_configuration(key, 'adc_ibias_delay')
    

    c.write_configuration(key, 'vref_dac')

    c.write_configuration(key, 'enable_data_stats')
    c.write_configuration(key, 'enable_periodic_trigger')
    c.write_configuration(key, 'cds_mode')
    c.write_configuration(key, 'enable_rolling_periodic_trigger')
    c.write_configuration(key, 'enable_periodic_reset')
    c.write_configuration(key, 'enable_rolling_periodic_reset')
    c.write_configuration(key, 'enable_hit_veto')
    c.write_configuration(key, 'enable_periodic_trigger_veto')
    c.write_configuration(key, 'threshold_global')
    c.write_configuration(key, 'periodic_trigger_cycles')
    c.write_configuration(key, 'dropped_packets') ## added

    c.write_configuration(key, 'periodic_reset_cycles')

    ok, diff = c.enforce_configuration(key, n=3, n_verify=3, timeout=0.1)
    # print(key, ' configuration:', ok)
    # if not ok: 
    #     print(f'{key}: {diff}')

    return ok
    

    
def main(periodic_trigger_cycles=_default_periodic_trigger_cycles, \
         periodic_reset_cycles=_default_periodic_reset_cycles, \
         vref_dac=_default_vref_dac, \
         duration_seconds = _default_duration, \
         **kwargs):
    
    #load controller
    c=load_controller()
    # print("controller: c = ")
    # print(c)
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
   
    c.io.reset_larpix(length=16)
    all_keys = c.chips.keys()
    # print("all_keys = ")
    # print(all_keys)
    print('Configuring')
    oks = np.zeros(len(all_keys))
    for i,key in enumerate(tqdm(all_keys, total = 25)):
        #print(f"pre enable_pedestal key = [{key}]")
        ok = configuration(c, key, \
                           periodic_trigger_cycles = periodic_trigger_cycles, \
                           periodic_reset_cycles = periodic_reset_cycles, \
                           vref_dac= vref_dac,
                          )
        oks[i] = ok

    goods = np.nonzero(oks)[0]
    print(f'{len(goods)} out of {len(oks)} configured')
    unmask(c, all_keys)

    c.io.reset_larpix(length=16)
    c.io.reset_larpix(length=16)

    # duration_seconds = 200
    print('Collecting Data')
    # data(c, duration_seconds, tag='gain')

    oscilloscope_data(c, duration_seconds, tag=None)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--periodic_trigger_cycles', \
                        default=_default_periodic_trigger_cycles, type=int, \
                        help='''Periodic trigger cycles [MCLK]''')
    parser.add_argument('--periodic_reset_cycles', \
                        default=_default_periodic_reset_cycles, type=int, \
                        help='''Periodic reset cycles [MCLK]''')
    parser.add_argument('--vref_dac', default=_default_vref_dac, type=int, \
                        help='''Vref DAC''')
    parser.add_argument('--run_duration', default=_default_duration, type=int, \
                        help='''Run Duration''')
    

    args=parser.parse_args()
    main(periodic_trigger_cycles=args.periodic_trigger_cycles, \
            periodic_reset_cycles=args.periodic_reset_cycles, \
            vref_dac=args.vref_dac, \
            duration_seconds = args.run_duration
        )        


