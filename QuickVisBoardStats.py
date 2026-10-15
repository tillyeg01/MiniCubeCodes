import h5py
import matplotlib.pyplot as plt
import yaml
import numpy as np
import sys
import argparse
import json
from scipy.stats import kurtosis

from matplotlib.patches import Rectangle
from matplotlib.collections import PatchCollection
from matplotlib import cm
from matplotlib.colors import Normalize


### Functions stolen from plot_metric.py

def unique_channel_id(d):
    return ((d['io_group'].astype(int)*1000+d['io_channel'].astype(int))*1000 \
            + d['chip_id'].astype(int))*100 + d['channel_id'].astype(int)

def unique_to_channel_id(unique):
    return unique % 100

def unique_to_chip_id(unique):
    return (unique// 100) % 1000

def unique_to_io_channel(unique):
    return(unique//(100*1000)) % 1000

def unique_to_tiles(unique):
    return ( (unique_to_io_channel(unique)-1) // 4) + 1

def unique_to_io_group(unique):
    return(unique // (100*1000*1000)) % 1000


def parse_file(filename):
    d = dict()
    f = h5py.File(filename,'r')
    unixtime=f['packets'][:]['timestamp'][f['packets'][:]['packet_type']==4]
    livetime = np.max(unixtime)-np.min(unixtime)
    data_mask = f['packets'][:]['packet_type']==1
    valid_parity_mask = f['packets'][:]['valid_parity']==1
    mask = np.logical_and(data_mask, valid_parity_mask)
    adc = f['packets']['dataword'][mask]
    unique_id = unique_channel_id(f['packets'][mask])
    unique_id_set = np.unique(unique_id)
    print("number of packets in parsed files =",len(unique_id))
    print("number of unique channels firing =", len(unique_id_set))
    for i in unique_id_set:
        id_mask = unique_id == i
        masked_adc = adc[id_mask]
        masked_adc = masked_adc[masked_adc > 0]
        d[i]=dict(
            mean = np.mean(masked_adc),
            std  = np.std(masked_adc),
            kurtosis = kurtosis(masked_adc),
            rate = len(masked_adc) / (livetime + 1e-9) )
    return d



def plot_xy(d, metric, geometry_yaml, normalization, fig, ax):
    with open(geometry_yaml) as fi: geo = yaml.full_load(fi)
    chip_pix = dict([(chip_id, pix) for chip_id,pix in geo['chips']])
    vertical_lines=np.linspace(-1*(geo['width']/2), geo['width']/2, 11)
    horizontal_lines=np.linspace(-1*(geo['height']/2), geo['height']/2, 11)

    nonrouted_v2a_channels=[] #[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57]
    routed_v2a_channels=[i for i in range(64) if i not in nonrouted_v2a_channels]
    
    io_groups = set(unique_to_io_group( np.array(list(d.keys())) ))
    tiles = set(unique_to_tiles( np.array(list(d.keys())) ))

    for io_group in io_groups:
        for tile in tiles:
            tile_id='{}-{}'.format(io_group, tile)
            mask = unique_to_io_group( np.array(list(d.keys())) ) == io_group
            mask = np.logical_and(mask, unique_to_tiles( np.array(list(d.keys())) )==tile )
            
            if not np.any(mask): continue
            
            print('studying tile {}'.format(tile_id)) 
            d_keys = np.array(list(d.keys()) )[mask]
            print(len(d_keys))

            ax.set_xlabel('X Position [mm]'); ax.set_ylabel('Y Position [mm]')
            ax.set_xticks(vertical_lines); ax.set_yticks(horizontal_lines)
            ax.set_xlim(vertical_lines[0],0)
            ax.set_ylim(0, horizontal_lines[-1])
            for vl in vertical_lines:
                ax.vlines(x=vl, ymin=horizontal_lines[0], ymax=horizontal_lines[-1], colors=['k'], linestyle='dotted')
            for hl in horizontal_lines:
                ax.hlines(y=hl, xmin=vertical_lines[0], xmax=vertical_lines[-1], colors=['k'], linestyle='dotted')
            plt.text(0.95,1.01,'LArPix', ha='center', va='center', transform=ax.transAxes)
            
            vmin = 0
            if metric == 'mean':
                vmin = 200

            chipid_pos = dict()
            for chipid in chip_pix.keys():
                x,y = [[] for i in range(2)]
                
                for channelid in routed_v2a_channels:
                    x.append( geo['pixels'][chip_pix[chipid][channelid]][1] )
                    y.append( geo['pixels'][chip_pix[chipid][channelid]][2] )
                avgX = (max(x)+min(x))/2.
                avgY = (max(y)+min(y))/2.
                chipid_pos[chipid]=dict(minX=min(x), maxX=max(x), avgX=avgX, minY=min(y), maxY=max(y), avgY=avgY)
                ax.annotate(str(chipid), [avgX,avgY], ha='center', va='center')
            for key in d_keys:
                channel_id = unique_to_channel_id(key)
                chip_id = unique_to_chip_id(key)
                if chip_id not in range(11,111): continue
                if channel_id in nonrouted_v2a_channels: continue
                if channel_id not in range(64): continue
                x = geo['pixels'][chip_pix[chip_id][channel_id]][1]
                y = geo['pixels'][chip_pix[chip_id][channel_id]][2]
                weight = (d[key][metric]-vmin)/(normalization-vmin)
                weight = abs(weight)
                if weight>1.0: 
                    weight=1.0
                r = Rectangle( ( x-(pitch/2.), y-(pitch/2.) ), pitch, pitch, color='r', alpha=weight)
                ax.add_patch( r )
            
            colorbar = fig.colorbar(cm.ScalarMappable(norm=Normalize(vmin=vmin, vmax=normalization), cmap='Reds'), ax=ax)

            if metric=='mean':
                ax.set_title('Tile ID '+tile_id+'\nADC Mean')
                colorbar.set_label('[ADC]')
            if metric=='std':
                ax.set_title('Tile ID '+tile_id+'\nADC RMS')
                colorbar.set_label('[ADC]')
            if metric=='rate':
                ax.set_title('Tile ID '+tile_id+'\nTrigger Rate')
                colorbar.set_label('[Hz]')
            if metric=='kurtosis':
                ax.set_title('Tile ID '+tile_id+'\nADC Kurtosis')
                colorbar.set_label('[ADC]')


                
fname = sys.argv[1]
datadir = '/home/qpix/larpix/larpix-5x5-test/data'
f = h5py.File(f'{datadir}/{fname}')
p = f['packets']

# Create a mask to filter data
mask = f['packets']['packet_type'] == 1

# apply the mask
d = p[mask]
geometry_yaml='/home/qpix/larpix/larpix-5x5-test/layout-2.5.1.yaml'
pitch=3.8 # mm



d = parse_file(f'data/{fname}')

meannormalization = 500
stdnormalization = 5
ratenormalization = 10
kurnormalization = 10


fig, axs = plt.subplots(2,2, figsize = (15,15))
plot_xy(d, 'mean',     geometry_yaml, normalization = 300, fig = fig, ax = axs[0,0])
plot_xy(d, 'std',      geometry_yaml, normalization = 5  , fig = fig, ax = axs[0,1])
plot_xy(d, 'kurtosis', geometry_yaml, normalization = 10 , fig = fig, ax = axs[1,0])
plot_xy(d, 'rate',     geometry_yaml, normalization = 10 , fig = fig, ax = axs[1,1])  
fig.suptitle(fname)
plt.show()