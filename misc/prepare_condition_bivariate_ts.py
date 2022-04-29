#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 23 21:54:59 2022

@author: guime
"""


from src.preprocessing_lib import EcogReader, Epocher
from src.input_config import args
from pathlib import Path
from scipy.io import savemat

import numpy as np
#%%

conditions = ['Rest', 'Face', 'Place', 'baseline']
# Original sampling rate
sfreq = 500
ts = dict.fromkeys(conditions, [])
subject = 'DiAs'
visual_chans = [ 'LGRD60-LGRD61', 'LTo1-LTo2']
for condition in conditions:
        # Read continuous HFA
        reader = EcogReader(args.data_path, subject=subject, stage='preprocessed',
                         preprocessed_suffix='_hfb_continuous_raw.fif', preload=True, 
                         epoch=False)
        hfb = reader.read_ecog()
        df_visual = reader.read_channels_info(fname='visual_channels.csv')
        hfb = hfb.pick_channels(visual_chans)
        # Epoch HFA
        if condition == 'baseline':
            # Return prestimulus baseline
            epocher = Epocher(condition='Stim', t_prestim=args.t_prestim, t_postim = args.t_postim, 
                         baseline=None, preload=True, tmin_baseline=args.tmin_baseline, 
                         tmax_baseline=args.tmax_baseline, mode=args.mode)
            epoch = epocher.log_epoch(hfb)
             # Downsample by factor of 2 and check decimation
            epoch = epoch.copy().crop(tmin = -0.5, tmax=0)
            epoch = epoch.copy().decimate(args.decim)
        else:
            # Return condition specific epochs
            epocher = Epocher(condition=condition, t_prestim=args.t_prestim, t_postim = args.t_postim, 
                             baseline=None, preload=True, tmin_baseline=args.tmin_baseline, 
                             tmax_baseline=args.tmax_baseline, mode=args.mode)
            epoch = epocher.log_epoch(hfb)
            epoch = epoch.copy().crop(tmin = args.tmin_crop, tmax=args.tmax_crop)
             # Downsample by factor of 2 and check decimation
            epoch = epoch.copy().decimate(args.decim)
            time = epoch.times
    
        # Prerpare time series for MVGC
        X = epoch.copy().get_data()
        (N, n, m) = X.shape
        X = np.transpose(X, (1,2,0))
        ts[condition] = X
# Add time
ts['time'] = time

# Add subject
ts['subject'] = subject

# Add sampling frequency
ts['sfreq'] = sfreq/args.decim

# Save condition ts as mat file
result_path = Path('../results')
fname = subject + '_condition_bivariate_ts.mat'
fpath = result_path.joinpath(fname)
savemat(fpath, ts)