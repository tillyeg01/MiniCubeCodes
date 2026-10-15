import larpix
import larpix.io
import argparse
# from base import utility_base
import larpix.format.rawhdf5format as rhdf5
import time
import larpix.format.pacman_msg_format as pacman_msg_fmt
import network_5x5
import pickle
from util import data, save_controller, load_controller


_default_periodic_trigger_cycles=150000 ## 100000
_default_periodic_reset_cycles=4 ## 512
_default_vref_dac=185 ###cold 220 ### warm 185
_default_duration=200
# _default_ref_current_trim=0
# _default_tx_diff=7
# _default_tx_slice=1
# _default_r_term=7
# _default_i_rx=3



def unmask(c, keys):
    for i in range(10):
        for key in reversed(keys):

            c[key].config.csa_enable= [1]*64
            c[key].config.channel_mask= [1]*64
            c[key].config.periodic_trigger_mask=[0]*64
            c.write_configuration(key, 'periodic_trigger_mask')
            c.write_configuration(key, 'csa_enable')
            c.write_configuration(key, 'channel_mask')


def enable_pedestal(c, key, 
                    periodic_trigger_cycles, \
                    periodic_reset_cycles, \
                    vref_dac, #\
                   ):
    #print(f"in enable_pedestal() key = [{key}]")
    c[key].config.enable_external_sync=1
    c.write_configuration(key, 'enable_external_sync')
    c[key].config.mark_first_packet = 0
    c.write_configuration(key, 'mark_first_packet')
    c[key].config.enable_periodic_trigger=1
    c[key].config.enable_rolling_periodic_trigger=1
    c[key].config.enable_periodic_reset=1
    c[key].config.enable_rolling_periodic_reset=0
    c[key].config.enable_hit_veto=1
    c[key].config.enable_periodic_trigger_veto=0

    c[key].config.threshold_global = 255
    c[key].config.periodic_trigger_cycles = periodic_trigger_cycles
    c[key].config.periodic_reset_cycles = periodic_reset_cycles

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
    
    c.write_configuration(key, 'periodic_reset_cycles')

    ok, diff = c.enforce_configuration(key, n=3, n_verify=3, timeout=0.1)
    print(key, ' pedestal enabled:', ok)
    if not ok: print(diff)
    #c[key].config.chip_id=11
    #c.write_configuration(key, 'chip_id')

def main(periodic_trigger_cycles=_default_periodic_trigger_cycles, \
         periodic_reset_cycles=_default_periodic_reset_cycles, \
         vref_dac=_default_vref_dac, \
         duration_seconds = _default_duration, \
         # ref_current_trim=_default_ref_current_trim, \
         # tx_diff=_default_tx_diff, \
         # tx_slice=_default_tx_slice, \
         # r_term=_default_r_term, \
         # i_rx=_default_i_rx, \
         **kwargs):
    
    #load controller
    c=load_controller()
    print("controller: c = ")
    print(c)
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
   
    c.io.reset_larpix(length=16)
    all_keys = c.chips.keys()
    print("all_keys = ")
    print(all_keys)
    for key in all_keys:
        #print(f"pre enable_pedestal key = [{key}]")
        enable_pedestal(c, key, \
                       periodic_trigger_cycles=periodic_trigger_cycles, \
                       periodic_reset_cycles=periodic_reset_cycles, \
                       vref_dac=vref_dac,)
    unmask(c, all_keys)

    c.io.reset_larpix(length=16)
    c.io.reset_larpix(length=16)

    # duration_seconds = 200
    data(c, duration_seconds, tag='pedestal')


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
    # parser.add_argument('--ref_current_trim', \
    #                     default=_default_ref_current_trim, \
	   #                  type=int, \
    #                     help='''Trim DAC for primary reference current''')
    # parser.add_argument('--tx_diff', \
    #                     default=_default_tx_diff, \
    #                     type=int, \
    #                     help='''Differential per-slice loop current DAC''')
    # parser.add_argument('--tx_slice', \
    #                     default=_default_tx_slice, \
    #                     type=int, \
    #                     help='''Slices enabled per transmitter DAC''')
    # parser.add_argument('--r_term', \
    #                     default=_default_r_term, \
    #                     type=int, \
    #                     help='''Receiver termination DAC''')
    # parser.add_argument('--i_rx', \
    #                     default=_default_i_rx, \
    #                     type=int, \
    #                     help='''Receiver bias current DAC''')

    args=parser.parse_args()
    main(periodic_trigger_cycles=args.periodic_trigger_cycles, \
            periodic_reset_cycles=args.periodic_reset_cycles, \
            vref_dac=args.vref_dac, \
            duration_seconds = args.run_duration
        )        
