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

from larpix.packet.packet_v3 import Packet_v3

_default_periodic_trigger_cycles=150000 ##400000 ## 100000
_default_periodic_reset_cycles=4 #4096 ## 512
_default_vref_dac=185 ###cold 220 ### warm 185
_default_duration=200
_default_data_dir='data/'

# cbar_lo = 0
# cbar_hi = 1
cbar_lo = 200
cbar_hi = 500


def now():
    return time.strftime("%Y_%m_%d_%H_%M_%S_%Z")

def data(c, runtime, data_dir=_default_data_dir, fname=None, tag=None):  
    if True:
        if fname is None: 
            if not tag is None:
                fname=data_dir+'/{}-packet-'.format(tag)+now()+'.h5'
            else:
    
                fname=data_dir+'/packet-'+now()+'.h5'
        
        c.logger = larpix.logger.HDF5Logger(filename=fname)
        # print('filename: ',c.logger.filename)
        c.reads.clear() 
        c.io.reset_larpix(length=16)
        
        display_data = np.zeros((40, 40))
    
        app = QtWidgets.QApplication([])
        
        window = pg.GraphicsLayoutWidget()
        window.resize(900, 900)
        
        plot = window.addPlot(row=0, col=0)
        plot.setAspectLocked(True)
        
        image = pg.ImageItem(display_data)
        image.setColorMap(pg.colormap.getFromMatplotlib('jet'))
        image.setLevels((cbar_lo, cbar_hi))
        
        colorbar = pg.ColorBarItem(
            values=(cbar_lo, cbar_hi),
            colorMap=pg.colormap.getFromMatplotlib('jet'))
        
        window.addItem(colorbar, row=0, col=1)
        colorbar.setImageItem(image)
        # colorbar.setParentItem(plot)
        
        plot.addItem(image)

        # Chip boundaries
        for x in range(8, 40, 8):
            line = pg.InfiniteLine(
                pos=x,
                angle=90,
                pen=pg.mkPen('k', width=2)
            )
            plot.addItem(line)
        
        for y in range(8, 40, 8):
            line = pg.InfiniteLine(
                pos=y,
                angle=0,
                pen=pg.mkPen('k', width=2)
            )
            plot.addItem(line)
            
        for row in range(5):
            for col in range(5):
        
                chip_id = f"{row + 1}{col + 1}"
        
                text = pg.TextItem(
                    text=chip_id,
                    color='k',
                    anchor=(0.5, 0.5)
                )
        
                text.setPos(
                    col * 8 + 4,
                    row * 8 + 4
                )
        
                plot.addItem(text)
                
        plot.invertY(True)
        window.show()
        
        
        sleeptime = min(0.1, runtime)
        c.start_listening()
        start_time = time.time()
        timelast = time.time()

        
        while time.time() - start_time < runtime:
            app.processEvents()
            time.sleep(sleeptime)
            read_packets, read_bytestream = c.read()
            if len(read_packets) > 0:
            
                paks = PacketCollection(
                    read_packets,
                    read_bytestream,
                    message='data'
                )
            
                try:
                    pi = paks.to_dict()
                    # print(pi['packets'][1].keys())
                except UnicodeDecodeError as e:
                    print("UnicodeDecodeError while decoding packet collection")
                    print("packets:", len(read_packets))
                    print("bytestream length:", len(read_bytestream))
                    print("bytestream tail:", repr(read_bytestream[-50:]))
                    print("error:", e)
                    continue       
                
               
                for packet in pi['packets'][1:]:

                    chipid = packet.get('chip_key')
                    channel = packet.get('channel_id')
                    value = packet.get('dataword')
                
                    if chipid is None or channel is None or value is None:
                        continue
                
                    row = int(chipid[4]) - 1
                    col = int(chipid[5]) - 1
                    channel = int(channel)
                
                    r_i = channel // 8
                    c_i = channel % 8
                
                    display_data[
                        row * 8 + r_i,
                        col * 8 + c_i
                    ] = float(value)
                    
                
                image.setImage(display_data, autoLevels=False,
                              levels = (cbar_lo, cbar_hi))
        
            app.processEvents()
                
            
        c.stop_listening()
        # c.logger.flush()
        c.logger.disable()
        print('Run Finished')
        


def unmask(c, keys):
    for i in range(10):
        for key in reversed(keys):

            c[key].config.csa_enable= [1]*64
            c[key].config.channel_mask= [1]*64
            c[key].config.periodic_trigger_mask=[0]*64
            c.write_configuration(key, 'periodic_trigger_mask')
            c.write_configuration(key, 'csa_enable')
            c.write_configuration(key, 'channel_mask')


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
    c[key].config.enable_periodic_trigger= 1 #1 #0 ## changed
    c[key].config.enable_rolling_periodic_trigger= 1 # 1 #0 ## changed
    c[key].config.enable_periodic_reset=1
    c[key].config.enable_rolling_periodic_reset= 0 # 0# 1 ## changed
    c[key].config.enable_hit_veto=1
    c[key].config.enable_periodic_trigger_veto=0

    c[key].config.threshold_global = 225 # 225# 25 ## changed
    c[key].config.periodic_trigger_cycles = periodic_trigger_cycles
    c[key].config.periodic_reset_cycles = periodic_reset_cycles

    # c[key].config.dropped_packets = 15 ## added

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
    # c.write_configuration(key, 'dropped_packets') ## added

    c.write_configuration(key, 'periodic_reset_cycles')

    ok, diff = c.enforce_configuration(key, n=3, n_verify=3, timeout=0.1)
    # print(key, ' configuration:', ok)
    if not ok: 
        print(f'{key}: {diff}')

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
    data(c, duration_seconds, tag='gain')


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
