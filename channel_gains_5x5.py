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



#Write configuration to multiple io_channels/tiles via broadcast chip ID 255
def multitile_write(c, register, value, keys, disabled_list, channel, verbose=False):
      
    for key in keys:
        
        # if key in list(disabled_list.keys()) and channel in disabled_list[key]:
        #     continue
        # print(
        #         f"Writing {register} to {key} "
        #         f"(io_group={c[key].io_group}, "
        #         f"io_channel={c[key].io_channel})"
        #     )
        setattr(c[key].config, register, value)
        c.write_configuration(key, register)

    
    return


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

def main(io_group, pacman_config, high_dac, disabled, **kwargs):

    c = load_controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
   
  

    enable_pacman_uart_from_io_channel(
            c.io, io_group, list(set([chip.io_channel for chip in c.chips])))
    
    # tiles = io_group_pacman_tile_[io_group]

    keys = c.chips.keys()
    keylist = list(keys)
    disabled_list = {}

    low_dac = 0
    n_iterations = 10

    if high_dac == 0:
        print(f"PROBLEM: YOU MUST SPECIFY A DAC LEVEL IN THE COMMAND TO RUN THIS SCRIPT, ZERO IS NOT AN OPTION")
    
    for channel in range(64):
        # channel = 1
        print(f'Testing channel {channel}')

        # chansel = [0]*64
        # # chansel[1] = 1
        # c[keylist[1]].config.csa_monitor_select = chansel
        # c.write_configuration(keylist[1], 'csa_monitor_select')
    
        #Unmask only the channel under test
        mask_list = [1]*64
        mask_list[channel] = 0
        multitile_write(c, 'channel_mask', mask_list, keys, disabled_list, channel)
        
        for i in range(n_iterations):
    
            #Set test pulse DAC low 
            multitile_write(c, 'csa_testpulse_dac', low_dac, keys, disabled_list, channel)
            # time.sleep(0.05)
            
            
            #Set test pulse DAC high
            multitile_write(c, 'csa_testpulse_dac', high_dac, keys, disabled_list, channel)
            # time.sleep(0.05)
            
            
            #Fire test pulse
            #NOTE: csa_testpulse_enable IS ACTIVE LOW (0)
            multitile_write(c, 'csa_testpulse_enable', mask_list, keys, disabled_list, channel)
            time.sleep(0.05)
            
            
            #Disable test pulse
            #NOTE: csa_testpulse_enable IS INACTIVE HIGH (1)
            multitile_write(c, 'csa_testpulse_enable', [1]*64, keys, disabled_list, channel)
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--io_group',
                        default=1,
                        type=int,
                        help='''IO group''')
    parser.add_argument('--pacman_config',
                        default='io/pacman.json',
                        type=str,
                        help='''PACMAN config file''')
    parser.add_argument('--high_dac',
                        default=0,
                        type=int,
                        help='''High DAC level to test''')    
    parser.add_argument('--disabled', default=None, \
                        type=str, help='''file with disabled channels by chip key''')

    args = parser.parse_args()
    c = main(**vars(args))