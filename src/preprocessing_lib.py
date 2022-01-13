#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jun 29 11:09:57 2020
This script contains functions and classes to read, preprocess data.
@author: guime
"""


import mne 
import numpy as np
import re
import scipy.stats as spstats
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from statsmodels.stats.multitest import fdrcorrection
from scipy import stats

#%% Create Ecog class to read data
#TODO : decompose read_ecog in 2 function: one for source and another for 
# derivatives (it is confusing to have parameters run and condition when
# reading derivatives data)
class EcogReader:
    """
    Reader class to read source, preprocessed ecog time series and anatomical
    data.
    """
    def __init__(self, path, subject='DiAs', stage='preprocessed',
                 preprocessed_suffix='_BP_montage_HFB_raw.fif', preload=True, 
                 epoch=False):
        """
        Parameters:
            -path: path to data folder (specified by user in input_config.py file)
            -subject: Id of subject
            -stage: 'raw_signal', 'bipolar_montage', 'preprocessing',
                    'preprocessing' is the repository containing data at some 
                    preprocessed stage
            -preprocessed_suffix: suffix of filename corresponding to preprocessing
            stage  
                Filename suffixes: 
                    '_bad_chans_removed_raw.fif': Bad channels removed and 
                        concatenated 
                    '_hfb_extracted_raw.fif' : extracted hfb
                    '_hfb_db_epo.fif' epoched and db transformed hfb
            -preload: True, False
                        Preloading data with MNE
            -epoch: True, False
                    Read epoched file with read_epochs function
        """
        self.path = path
        self.subject = subject
        self.stage = stage
        self.preprocessed_suffix = preprocessed_suffix
        self.preload = preload
        self.epoch = epoch

    def read_ecog(self, run=1, condition='stimuli'):
        """
        Reads ECoG dataset of interest. 
        If reads raw or bipolar montage dataset
        then call mne function to read .set eeglab format. 
        If reads at some preprocessing stage 
        then call mne function to read .fif fromat. 
        -------
        Inputs:
        -------
        - condition: 'stimuli', 'rest_baseline', 'sleep' 
        - run : 1, 2
        """
        # Check that the variable run is an integer
        assert isinstance(run, int)
        # If reading preprocessed ecog then read in derivatives folder with 
        # filename suffix corresponding to a specific preprocessing step
        if self.stage == 'preprocessed':
            fname = self.subject + self.preprocessed_suffix
            fpath = self.path.joinpath('derivatives', self.subject, 'ieeg', fname)
            # Read continuous data
            if self.epoch==False:
                raw = mne.io.read_raw_fif(fpath, preload=self.preload)
            # Read epoched data
            else:
                raw = mne.read_epochs(fpath, preload=self.preload)
        # Write file path and name for raw or bipolar rereferenced. 
        else:
            fpath = self.path.joinpath('source_data','iEEG_10', 'subjects', 
                                       self.subject, 'EEGLAB_datasets')
            fname = [self.subject, "freerecall", condition, str(run), 'preprocessed']
            fname = '_'.join(fname)
            # filepath and filename for bipolar rereferenced data
            if self.stage == 'bipolar_montage':
                fpath = fpath.joinpath('bipolar_montage')
                sfx = '_BP_montage'
                fname = fname + sfx
            # file path for raw data
            else:
                fpath = fpath.joinpath('raw_signal')
            # Read ecog source data
            fname = fname + '.set'
            fpath = fpath.joinpath(fname)
            raw = mne.io.read_raw_eeglab(fpath, preload=self.preload)
        return raw

    def read_channels_info(self, fname='electrodes_info.csv'):
        """
        Read subject-specific channels information into a dataframe. 
        ------
        Input
        ------
        fname: file name of the channels
        fname= 'electrodes_info.csv', 'visual_channels.csv', 'BP_channels'
        """
        # Write path to info about anatomical details of subject in derivatives
        brain_path = self.path.joinpath('derivatives',self.subject, 'brain')
        channel_path = brain_path.joinpath(fname)
        # Read channel info in a csv file
        channel_info = pd.read_csv(channel_path)
        return channel_info
    
    def concatenate_condition(self):
        """
        Concatenate resting state and stimuli presentation ECoG datasets
        """
        raw = self.concatenate_run(condition='rest_baseline')
        raw_stimuli = self.concatenate_run(condition='stimuli')
        # Concatenante all conditions
        raw.append([raw_stimuli])
        return raw
    
    def concatenate_run(self,  condition='stimuli'):
        """
        Concatenate ECoG datasets by runs
        """
        raw = self.read_ecog(run=1, condition=condition)
        raw_2 = self.read_ecog(run=2, condition=condition)
        # Concatenate both run
        raw.append([raw_2])
        return raw

#%% Bad channel removal

def drop_bad_chans(raw, q=99, voltage_threshold=500e-6, n_std=5):
    """
    Automatic bad channel removal from standard deviation, percentile
    voltage values and removing physiological channels that are not
    bipolar referenced
    """
    # Mark physiological channels
    raw = mark_physio_chan(raw)
    # Mark channels above 5 std deviation
    raw = mark_high_std_outliers(raw, n_std=n_std)
    # Pick channels in 99th percentile
    outliers_chans = pick_99_percentile_chans(raw, q=q,
                                           voltage_threshold=voltage_threshold)
    raw.info['bads'].extend(outliers_chans)
    bads = raw.info['bads']
    print(f'List of all bad chans: {bads}')
    # Drop bad channels
    raw = raw.copy().drop_channels(bads)
    return raw, bads


def pick_99_percentile_chans(raw, q=99, voltage_threshold=500e-6):
    """
     Return outliers channels. Outliers are channels whose average value
     in the 99th percentile are above a voltage_threshold chosen at 500 muV
     Choice of threshold follows Itzik Norman study (see preprocessing methods
     in Neuronal baseline shifts underlying boundary setting during free recall). 
    """
    X = raw.copy().get_data()
    (nchan, nobs) = X.shape
    obs_ax = 1
    # Compute 99 percentile value of each channel
    top_percentile = np.percentile(X, q=q, axis=obs_ax)
    count = np.zeros_like(top_percentile)
    average_value_in_top_percentile = np.zeros_like(top_percentile)
    # Compute average value of each channel in top percentile
    for i in range(nchan):
        for j in range(nobs):
            if X[i,j] >= top_percentile[i]:
                average_value_in_top_percentile[i] += X[i,j]
                count[i] += 1
            else:
                continue
        average_value_in_top_percentile[i] = average_value_in_top_percentile[i]/count[i]
    # Return channels whose average value in the top percentile is above voltage
    # threshold
    outliers_indices = np.where(average_value_in_top_percentile>=voltage_threshold)[0].tolist()
    ch_names = raw.info['ch_names']
    outliers_chans = []
    for i in outliers_indices:
        outliers_chans.append(ch_names[i])
    print(f'List of outliers channels: {outliers_chans}')
    return outliers_chans

def mark_high_std_outliers(raw, n_std=5):
    """
    Detect channels having standard deviation n_std times larger or
    smaller than standard deviation of all joint channels. Methods inspired by
    J. Schrouff. 
    """
    X = raw.copy().get_data()
    std = np.std(X)
    std_chan = np.std(X, axis=1).tolist()
    outlier_idx = []
    outlier_chan = []
    nchans = X.shape[0]
    chan_names = raw.info['ch_names']
    for i in range(nchans):
        if std_chan[i]>=n_std*std or std_chan[i]<=std/n_std:
            outlier_idx.append(i)
        else: 
            continue

    for i in outlier_idx:
        outlier_chan.append(chan_names[i])
        
    raw.info['bads'].extend(outlier_chan)
    return raw

def mark_physio_chan(raw):
    """
    Append physiological channels to bad channels. Phisiological channels 
    are not bipolar rereferenced
    """
    ch_names = raw.info['ch_names']
    for chan in ch_names:
        # Keep bipolar channels
        if '-' in chan:
            continue
        # Remove physiological channels (those are non bipolar channels)
        else:
            raw.info['bads'].append(chan)
    bads = raw.info['bads']
    print(f'List of bad channels: {bads}')
    return raw

# %% Extract hfb envelope

class HfbExtractor():
    """
    Class for HFB envelope extraction
    """
    def __init__(self, l_freq=60.0, nband=6, band_size=20.0, l_trans_bandwidth= 10.0,
                h_trans_bandwidth= 10.0, filter_length='auto', phase='minimum',
                fir_window='blackman'):
        """
        States
        ----------
        raw: MNE raw object
            the LFP data to be filtered (in MNE python raw structure)
        l_freq: float, optional
                lowest frequency in Hz
        nband: int, optional
               Number of frequency bands
        band_size: float, optional
                    size of frequency band in Hz
        See mne.io.Raw.filter documentation for additional optional parameters
        """
        self.l_freq = l_freq
        self.nband = nband
        self.band_size = band_size
        self.l_trans_bandwidth = l_trans_bandwidth
        self.h_trans_bandwidth = h_trans_bandwidth
        self.filter_length = filter_length
        self.phase = phase
        self.fir_window = fir_window

    def extract_hfb(self, raw):
        """
        Extract the high frequency broadband (hfb) from LFP iEEG signal.
        Methods of extraction follows Itzik norman Neuronal baseline shifts 
        underlying boundary setting during free recall, see methods section
        -------
        Returns
        -------
        hfb: MNE raw object 
            The high frequency broadband
        """
        nobs = len(raw.times)
        nchan = len(raw.info['ch_names'])
        bands = self.freq_bands()
        hfb = np.zeros(shape=(nchan, nobs))
        mean_amplitude = np.zeros(shape=(nchan,))
        
        for band in bands:
            # extract narrow band envelope
            envelope = self.extract_envelope(raw)
            # Rescale narrow band envelope by its mean amplitude 
            env_norm = self.mean_normalise(envelope)
            # hfb is weighted average of narrow bands envelope over high gamma band
            hfb += env_norm
            # Compute mean amplitude over broad band to convert in volts
            mean_amplitude += np.mean(envelope, axis=1)
        hfb = hfb/self.nband
        mean_amplitude = mean_amplitude/self.nband
        # Convert hfb in volts
        hfb = hfb * mean_amplitude[:,np.newaxis]
        # Convert NaN to 0
        hfb = np.nan_to_num(hfb) 
        # Create Raw object for further MNE processing
        hfb = mne.io.RawArray(hfb, raw.info)
        # Conserve annotations from raw to hfb
        hfb.set_annotations(raw.annotations)
        return hfb

    def freq_bands(self):
        """
        Create a list of 20Hz spaced frequencies from [60, 160]Hz (high gamma)
        These frequencies will be used to banpass the iEEG signal for 
        high frequency envelope extraction
        
        Parameters
        ----------
        l_freq: float, optional
                lowest frequency in Hz
        nband: int, optional
               Number of frequency bands
        band_size: int, optional
                    size of frequency band in Hz
        
        Returns
        -------
        bands: list
                List of frequency bands
                
        """
        bands = [self.l_freq + i * self.band_size for i in range(0, self.nband)]
        return bands

    def extract_envelope(self, raw):
        """
        Extract the envelope of a bandpass signal. The filter is constructed 
        using MNE python filter function. Hilbert transform is computed from MNE
        apply_hilbert() function. Filter and Hilber function themselves rely mostly
        on scipy signal filtering and hilbert funtions.
        ----------
        Parameters
        ----------
        raw: MNE raw object
            the LFP data to be filtered (in MNE python raw structure)
        %(l_freq)s
        %(band_size)s
        See mne.io.Raw.filter documentation for additional optional parameters
        
        -------
        Returns
        -------
        envelope: MNE raw object
                 The envelope of the bandpass signal
        """
        raw_band = raw.copy().filter(l_freq=self.l_freq, h_freq=self.l_freq+self.band_size,
                                     phase=self.phase, filter_length=self.filter_length,
                                     l_trans_bandwidth= self.l_trans_bandwidth, 
                                     h_trans_bandwidth= self.h_trans_bandwidth,
                                         fir_window=self.fir_window)
        envelope = raw_band.copy().apply_hilbert(envelope=True).get_data()
        return envelope

    def mean_normalise(self, envelope):
        """
        Divide the narrow band envelope by its mean. Useful for extracting hfb which is a
        weighted average of each envelope accross 20Hz frequency bands.
        ----------
        Parameters
        ----------
        envelope: MNE raw object
                The envelope of the band pass signal
        -------
        Returns
        -------
        envelope_norm: MNE raw object
                        The mean normalised envelope
        """
        envelope_mean = np.mean(envelope, axis=1)
        envelope_norm = np.divide(envelope, envelope_mean[:,np.newaxis])
        return envelope_norm


#%% Epoch HFA or ECoG 

class Epocher():
    """
    Class for HFB epoching and rescaling. Note this concern stimulus hfb (not
    resting state, see later for rest) 
    -----------
    Parameters: 
        condition: Rest, Stim, Face or Place
        t_prestim: prestimulus onset 
        t_postim: end of postimulus baseline
        baseline: Boolean, rescale by baseline with MNE when epoching (cause 
        issues)
        tmin_baseline: prestimulus baseline onset
        tmax_baseline: end of prestimulus baseline
        mode: 'logratio' or simply ratio
        See MNE python epochs object for more information
    -----------
    We apply baseline rescaling for visual channel detection and classification. We
    do not recommand rescaling for GC analysis
    """
    def __init__(self, condition='Face', t_prestim=-0.5, t_postim = 1.75, 
                 baseline=None, preload=True, tmin_baseline=-0.4, tmax_baseline=-0.1, 
                 mode='logratio'):
        super().__init__()
        self.condition = condition
        self.t_prestim = t_prestim
        self.t_postim = t_postim
        self.baseline = baseline
        self.preload = preload
        self.tmin_baseline = tmin_baseline
        self.tmax_baseline = tmax_baseline
        self.mode = mode
    
    def scale_epoch(self, raw):
        """
        Epoch condition specific hfb/Ecog and scale with baseline
        """
        epochs = self.epoch(raw)
        epochs = self.baseline_rescale(epochs)
        return epochs
    
    def log_epoch(self, raw):
        """
        Epoch condition specific hfb/ecog and log transform
        """
        epochs = self.epoch(raw)
        epochs = self.log_transform(epochs)
        return epochs
    
    def epoch(self, raw):
        """
        Epoch condition specific raw object
        Chosing [5 105]s in run 1 and [215 415]s in run 2 resting state 
        epoched into 2s length trials
         """
        # If resting state epoch continuously
        if self.condition == 'Rest':
            # Select resting state time segment of length 200ms onset at 5 and 215s
            # Resting state time segment is taken from concatenated-bad-chan-
            # removed signal
            events_1 = mne.make_fixed_length_events(raw, id=32, start=5, 
                                                    stop=205, duration=2, first_samp=False, overlap=0.0)
            events_2 = mne.make_fixed_length_events(raw, id=32, 
                                                    start=215, stop=415, duration=2, first_samp=False, overlap=0.0)
        
            events = np.concatenate((events_1,events_2))
            # Id of resing state event
            rest_id = {'Rest': 32}
            # epoch resting state events
            epochs= mne.Epochs(raw, events, event_id= rest_id, 
                                tmin=self.t_prestim, tmax=self.t_postim, 
                                baseline= self.baseline, preload=self.preload)
        # If stimulus epochs from stimulus-annotated events     
        elif self.condition == 'Stim':
            # Extract face and place id
            events, events_id = mne.events_from_annotations(raw)
            # Epochs stim hfb/ecog
            epochs= mne.Epochs(raw, events, event_id= events_id, 
                                tmin=self.t_prestim, tmax=self.t_postim, 
                                baseline= self.baseline, preload=self.preload)
        else :
            # Extract face and place id
            events, events_id = mne.events_from_annotations(raw)
            # Extract condition specific events id
            condition_id = self.extract_condition_id(events_id)
            # Epoch condition specific events
            epochs= mne.Epochs(raw, events, event_id= events_id, 
                                tmin=self.t_prestim, tmax=self.t_postim, 
                                baseline= self.baseline, preload=self.preload)
            epochs = epochs[condition_id]
            #events = epochs.events
        return epochs
    
    def extract_condition_id(self, event_id):
        """
        Returns event id of specific condition (Face or Place)
        """
        p = re.compile(self.condition)
        stim_id = []
        for key in event_id.keys():
            if p.match(key):
                stim_id.append(key)
        return stim_id


    def baseline_rescale(self, epochs):
        """
        Scale hfb with pre stimulus baseline and log transform for result in dB
        Allows for cross channel comparison relative to a single scale.
        """
        events = epochs.events
        event_id = epochs.event_id
        # Drop boundary event for compatibility. This does not affect results
        if 'boundary' in event_id:
            del event_id['boundary']
        A = epochs.get_data()
        times = epochs.times
        # Baseline rescaling
        A = 10*mne.baseline.rescale(A, times, baseline=(self.tmin_baseline,self.tmax_baseline),
                                    mode=self.mode)
        # Create epoch object from array
        hfb = mne.EpochsArray(A, epochs.info, events=events, 
                                 event_id=event_id, tmin=self.t_prestim)
        return hfb
    
    def log_transform(self, epochs):
        
        events = epochs.events
        event_id = epochs.event_id
        # Drop boundary event for compatibility. This does not affect results
        if 'boundary' in event_id:
            del event_id['boundary']
        A = epochs.get_data()
        # Log transform
        A = np.log(A)
        # Create epoch object from array
        hfb = mne.EpochsArray(A, epochs.info, events=events, 
                                 event_id=event_id, tmin=self.t_prestim)
        return hfb

    def extract_baseline(self, epochs):
        """
        Extract baseline by averaging prestimulus accross time and trials. Does 
        not differs much to MNE baseline.rescale, use MNE rescaling instead.
        """
        baseline = epochs.copy().crop(tmin=self.tmin_baseline, tmax=self.tmax_baseline) # Extract prestimulus baseline
        baseline = baseline.get_data()
        baseline = np.mean(baseline, axis=(0,2)) # average over time and trials
        return baseline 


#%% Detect visually responsive populations

class VisualDetector:
    """
    Detect visually responsive channels
    """
    def __init__(self, tmin_prestim=-0.4, tmax_prestim=-0.1, tmin_postim=0.1,
               tmax_postim=0.5, alpha=0.05, zero_method='pratt',
               alternative='two-sided'):
        self.tmin_prestim = tmin_prestim
        self.tmax_prestim = tmax_prestim
        self.tmin_postim = tmin_postim
        self.tmax_postim = tmax_postim
        self.alpha = alpha
        self.zero_method = zero_method
        self.alternative = alternative
        
    def detect(self, hfb_db):
        """
        Detect visually responsive channels by testing hypothesis of no difference 
        between prestimulus and postimulus HFB amplitude.
        ----------
        Parameters
        ----------
        hfb_db: MNE raw object
                HFB of iEEG in decibels
        tmin_prestim: float
                    starting time prestimulus amplitude
        tmax_preststim: float
                        stoping time prestimlus amplituds
        tmin_postim: float
                     starting time postimuls amplitude
        tmax_postim: float
                    stopping time postimulus amplitude
        alpha: float
            significance threshold to reject the null
        From scipy.stats.wilcoxon:
        alternative: {“two-sided”, “greater”, “less”}, optional
        zero_method: {“pratt”, “wilcox”, “zsplit”}, optional
        -------
        Returns
        -------
        visual_chan: list.
                    List of visually responsive channels
        effect_size: list
                     visual responsivity effect size
        """
        A_prestim = self.crop_hfb(hfb_db, tmin=self.tmin_prestim, tmax=self.tmax_prestim)
        A_postim = self.crop_hfb(hfb_db, tmin=self.tmin_postim, tmax=self.tmax_postim)
        reject, pval_correct, tstat = self.multiple_wilcoxon_test(A_postim, A_prestim)
        visual_responsivity = self.compute_visual_responsivity(A_postim, A_prestim)
        visual_chan, effect_size = self.visual_chans_stats(reject, visual_responsivity, hfb_db)
        return visual_chan, effect_size
    
    
    def crop_hfb(self, hfb_db, tmin=-0.5, tmax=-0.05):
        """
        crop hfb between over [tmin tmax].
        Input : MNE raw object
        Return: array
        """
        A = hfb_db.copy().crop(tmin=tmin, tmax=tmax).get_data()
        return A
    
    
    def crop_stim_hfb(self, hfb_db, stim_id, tmin=-0.5, tmax=-0.05):
        """
        crop condition specific hfb between [tmin tmax].
        Input : MNE raw object
        Return: array
        """
        A = hfb_db[stim_id].copy().crop(tmin=tmin, tmax=tmax).get_data()
        return A

    def multiple_wilcoxon_test(self, A_postim, A_prestim, alternative='two-sided'):
        """
        Wilcoxon test hypothesis of no difference between prestimulus and postimulus amplitude
        Correct for multilple hypothesis test.
        ----------
        Parameters
        ----------
        A_postim: (...,times) array
                Postimulus amplitude
        A_prestim: (...,times) array
                    Presimulus amplitude
        alpha: float
            significance threshold to reject the null
        From scipy.stats.wilcoxon:
        alternative: {“two-sided”, “greater”, “less”}, optional
        zero_method: {“pratt”, “wilcox”, “zsplit”}, optional
        """
        A_postim = np.mean(A_postim, axis=-1)
        A_prestim = np.mean(A_prestim, axis=-1)
        # Iniitialise inflated p values
        nchans = A_postim.shape[1]
        pval = [0]*nchans
        tstat = [0]*nchans
        # Compute inflated stats given non normal distribution
        for i in range(0,nchans):
            tstat[i], pval[i] = spstats.wilcoxon(A_postim[:,i], A_prestim[:,i],
                                                 zero_method=self.zero_method, 
                                                 alternative=alternative) 
        # Correct for multiple testing    
        reject, pval_correct = fdrcorrection(pval, alpha=self.alpha)
        w_test = reject, pval_correct, tstat
        return w_test

    def cohen_d(self, x, y):
        """
        Compute cohen d effect size between 1D array x and y
        """
        n1 = np.size(x)
        n2 = np.size(y)
        m1 = np.mean(x)
        m2 = np.mean(y)
        s1 = np.std(x)
        s2 = np.std(y)
        
        s = (n1 - 1)*(s1**2) + (n2 - 1)*(s2**2)
        s = s/(n1+n2-2)
        s= np.sqrt(s)
        num = m1 - m2
        
        cohen = num/s
        
        return cohen
    
    def compute_visual_responsivity(self, A_postim, A_prestim):
        """
        Compute visual responsivity of a channel from cohen d.
        """
        nchan = A_postim.shape[1]
        visual_responsivity = [0]*nchan
        
        for i in range(nchan):
            x = np.ndarray.flatten(A_postim[:,i,:])
            y = np.ndarray.flatten(A_prestim[:,i,:])
            visual_responsivity[i] = self.cohen_d(x,y)
            
        return visual_responsivity
    
    
    def visual_chans_stats(self, reject, visual_responsivity, hfb_db):
        """
        Return visual channels with their corresponding responsivity
        """
        idx = np.where(reject==True)
        idx = idx[0]
        visual_chan = []
        effect_size = []
        
        for i in list(idx):
            if visual_responsivity[i]>0:
                visual_chan.append(hfb_db.info['ch_names'][i])
                effect_size.append(visual_responsivity[i])
            else:
                continue
        return visual_chan, effect_size

#%% Compute visual channels latency response
        
    def compute_latency(self, visual_hfb, image_id, visual_channels):
        """
        Compute latency response of visual channels"
        """
        sfreq = visual_hfb.info['sfreq']
        A_postim = self.crop_stim_hfb(visual_hfb, image_id, tmin=0, tmax=1.5)
        A_prestim = self.crop_stim_hfb(visual_hfb, image_id, tmin=-0.4, tmax=0)
        A_baseline = np.mean(A_prestim, axis=-1) #No
        
        pval = [0]*A_postim.shape[2]
        tstat = [0]*A_postim.shape[2]
        latency_response = [0]*len(visual_channels)
        
        for i in range(len(visual_channels)):
            for t in range(np.size(A_postim,2)):
                tstat[t] = spstats.wilcoxon(A_postim[:,i,t], A_baseline[:,i],
                                            zero_method=self.zero_method, 
                                            alternative='greater')
                pval[t] = tstat[t][1]
                
            reject, pval_correct = fdrcorrection(pval, alpha=self.alpha) # correct for multiple hypotheses
            
            for t in range(0,np.size(A_postim,2)):
                # Channel has to be visually responsive for at least 50 ms
                if np.all(reject[t:t+25])==True :
                    latency_response[i]=t/sfreq*1e3
                    break 
                else:
                    continue
        return latency_response

# %% Classify channels into Face, Place and retinotopic channels
    
class VisualClassifier(VisualDetector):
    """
    Classify visual channels into Face, Place and retinotopic channels
    """
    def __init__(self, tmin_prestim=-0.4, tmax_prestim=-0.1, tmin_postim=0.1,
               tmax_postim=0.5, alpha=0.05, zero_method='pratt',
               alternative='two-sided'):
        super().__init__(tmin_prestim, tmax_prestim, tmin_postim,
               tmax_postim, alpha, zero_method, alternative)

    def hfb_to_visual_populations(self, hfb_db, dfelec):
        """
        Create dictionary containing all relevant information on visually responsive channels
        """
        # Extract and normalise hfb
        event_id = hfb_db.event_id
        face_id = self.extract_stim_id(event_id, cat = 'Face')
        place_id = self.extract_stim_id(event_id, cat='Place')
        image_id = face_id+place_id
        
        # Detect visual channels
        visual_chan, visual_responsivity = self.detect(hfb_db)
        visual_hfb = hfb_db.copy().pick_channels(visual_chan)
        
        # Compute latency response
        latency_response = self.compute_latency(visual_hfb, image_id, visual_chan)
        
        # Classify Face and Place populations
        group, category_selectivity = self.face_place(visual_hfb, face_id, place_id, visual_chan)
        
        # Classify retinotopic populations
        group = self.retinotopic(visual_chan, group, latency_response, dfelec)
        
        # Compute peak time
        peak_time = self.compute_peak_time(hfb_db, visual_chan, tmin=0.05, tmax=1.75)
        
        # Create visual_populations dictionary 
        visual_populations = {'chan_name': [], 'group': [], 'latency': [], 
                              'brodman': [], 'DK': [], 'X':[], 'Y':[], 'Z':[]}
        
        visual_populations['chan_name'] = visual_chan
        visual_populations['group'] = group
        visual_populations['latency'] = latency_response
        visual_populations['visual_responsivity'] = visual_responsivity
        visual_populations['category_selectivity'] = category_selectivity
        visual_populations['peak_time'] = peak_time
        for chan in visual_chan: 
            chan_name_split = chan.split('-')[0]
            visual_populations['brodman'].extend(dfelec['Brodman'].loc[dfelec['electrode_name']==chan_name_split])
            visual_populations['DK'].extend(dfelec['ROI_DK'].loc[dfelec['electrode_name']==chan_name_split])
            visual_populations['X'].extend(dfelec['X'].loc[dfelec['electrode_name']==chan_name_split])
            visual_populations['Y'].extend(dfelec['Y'].loc[dfelec['electrode_name']==chan_name_split])
            visual_populations['Z'].extend(dfelec['Z'].loc[dfelec['electrode_name']==chan_name_split])
            
        return visual_populations

    def face_place(self, visual_hfb, face_id, place_id, visual_channels):
        """
        Classify Face selective sites using one sided signed rank wilcoxon
        test. 
        """
        nchan = len(visual_channels)
        # By default, all channles are "others"
        group = ['O']*nchan
        category_selectivity = [0]*len(group)
        A_face = self.crop_stim_hfb(visual_hfb, face_id, tmin=self.tmin_postim, tmax=self.tmax_postim)
        A_place = self.crop_stim_hfb(visual_hfb, place_id, tmin=self.tmax_postim, tmax=self.tmax_postim)
        
        w_test_plus = self.multiple_wilcoxon_test(A_face, A_place, alternative = 'greater')
        reject_plus = w_test_plus[0]    
        
        #w_test_minus = self.multiple_wilcoxon_test(A_face, A_place, alternative = 'less')
        #reject_minus = w_test_minus[0]    
        
        # Significant electrodes located outside of V1 and V2 are Face or Place responsive
        for idx, channel in enumerate(visual_channels):
            A_f = np.ndarray.flatten(A_face[:,idx,:])
            A_p = np.ndarray.flatten(A_place[:,idx,:])
            if reject_plus[idx]==False :
                continue
            else:
                group[idx] = 'F'
                category_selectivity[idx] = self.cohen_d(A_f, A_p)
        return group, category_selectivity
    
    
    def retinotopic(self, visual_channels, group, latency_response, dfelec):
        """
        Return retinotopic site from V1 and V2 given Brodman atlas.
        """
        nchan = len(group)
        bipolar_visual = [visual_channels[i].split('-') for i in range(nchan)]
        for i in range(nchan):
            brodman = (dfelec['Brodman'].loc[dfelec['electrode_name']==bipolar_visual[i][0]].to_string(index=False), 
                       dfelec['Brodman'].loc[dfelec['electrode_name']==bipolar_visual[i][1]].to_string(index=False))
            if latency_response[i] <= 180:            
                if brodman[0] in ('V1, V2') and brodman[1] in  ('V1, V2') :
                    group[i]='R'
        return group
    
#    def extract_stim_id(self, event_id, cat = 'Face'):
#        """
#        Returns event id of specific stimuli category (Face or Place)
#        """
#        p = re.compile(cat)
#        stim_id = []
#        for key in event_id.keys():
#            if p.match(key):
#                stim_id.append(key)
#        return stim_id

    def compute_peak_time(self, hfb, visual_chan, tmin=0.05, tmax=1.75):
        """
        Return time of peak amplitude for each visual channel
        """
        nchan = len(visual_chan)
        peak_time = [0] * nchan
        hfb = hfb.copy().pick_channels(visual_chan)
        hfb = hfb.copy().crop(tmin=tmin, tmax = tmax)
        time = hfb.times
        A = hfb.copy().get_data()
        evok = np.mean(A,axis=0)
        for i in range(nchan):
            peak = np.amax(evok[i,:])
            peak_sample = np.where(evok[i,:]==peak)
            peak_sample = peak_sample[0][0]
            peak_time[i] = time[peak_sample]
        return peak_time

# %% Create category specific time series as input for mvgc toolbox

#def category_ts(hfb, visual_chan, sfreq=250, tmin_crop=0.050, tmax_crop=0.250):
#    """
#    Return time series in all conditions ready for mvgc analysis
#    ----------
#    Parameters
#    ----------
#    visual_chan : list
#                List of visually responsive channels
#    """
#    condition = ['Rest', 'Face', 'Place']
#    ncat = len(condition)
#    ts = [0]*ncat
#    for idx, cat in enumerate(condition):
#        X, time = hfb_to_category_time_series(hfb, visual_chan, sfreq=sfreq, cat=cat, 
#                                        tmin_crop=tmin_crop, tmax_crop=tmax_crop)
#        ts[idx] = X
#
#    ts = np.stack(ts)
#    (ncat, ntrial, nchan, nobs) = ts.shape
#    ts = np.transpose(ts, (2, 3, 1, 0))
#    return ts, time

def category_ts(hfb, visual_chan, sfreq=250, tmin_crop=0.050, tmax_crop=0.250):
    """
    Return time series in all conditions ready for mvgc analysis
    ----------
    Parameters
    ----------
    visual_chan : list
                List of visually responsive channels
    """
    condition = ['Rest', 'Face', 'Place']
    ncdt = len(condition)
    ts = [0]*ncdt
    for idx, cat in enumerate(condition):
        X, time = hfb_to_category_time_series(hfb, visual_chan, sfreq=sfreq, cat=cat, 
                                        tmin_crop=tmin_crop, tmax_crop=tmax_crop)
        (ntrial, nchan, nobs) = X.shape
        X = np.transpose(X,(1,2,0))
        ts[idx] = X
    return ts, time

def category_lfp(lfp, visual_chan, tmin_crop=-0.5, tmax_crop =1.75, sfreq=200):
    """
    Return ieeg time series in all conditions ready for mvgc analysis
    ----------
    Parameters
    ----------
    visual_chan : list
                List of visually responsive channels
    """
    condition = ['Rest', 'Face', 'Place']
    ncat = len(condition)
    ts = [0]*ncat
    lfp = lfp.pick(visual_chan)
    for idx, cat in enumerate(condition):
        epochs, events = epoch_condition(lfp, cat=cat, tmin=tmin_crop, tmax=tmax_crop)
        epochs = epochs.resample(sfreq=sfreq)
        time = epochs.times
        sorted_indices = sort_indices(epochs, visual_chan)
        X = sort_visual_chan(sorted_indices, epochs)
        (ntrial, nchan, nobs) = X.shape
        X = np.transpose(X,(1,2,0))
        ts[idx] = X
    return ts, time

def hfb_to_category_time_series(hfb, visual_chan, sfreq=250, cat='Rest', tmin_crop = 0.5, tmax_crop=1.5):
    """
    Return resampled category visual time series cropped in a time interval [tmin_crop tmax_crop]
    of interest     
    """
    hfb = category_hfb(hfb, visual_chan, cat=cat, tmin_crop = tmin_crop, tmax_crop=tmax_crop)
    hfb = hfb.resample(sfreq=sfreq)
    time = hfb.times
    sorted_indices = sort_indices(hfb, visual_chan)
    X = sort_visual_chan(sorted_indices, hfb)
    return X, time

def category_hfb(hfb, visual_chan, cat='Rest', tmin_crop = -0.5, tmax_crop=1.5) :
    """
    Return category visual time hfb_db cropped in a time interval [tmin_crop tmax_crop]
    of interest
    """
    hfb_db = Hfb_db()
    # Extract visual HFB
    hfb = hfb.pick(visual_chan)
    # Epoch condition specific HFB
    hfb, events = epoch_condition(hfb, cat=cat, tmin=-0.5, 
                                    tmax=1.75)
    #hfb = hfb_db.db_transform(hfb) 
    hfb = hfb_db.log_transform(hfb)
    hfb = hfb.crop(tmin=tmin_crop, tmax=tmax_crop)
    return hfb

#def epoch_condition(raw, cat='Rest', tmin=-0.5, tmax=1.75):
#    """
#    Epoch condition specific raw object (raw can be hfb or lfp)
#    Can chose [100 156]s in run 1 and [300 356]s in run 2 epoched into 2s for
#    56 trials
#    Can also chose [5 205]s and [215 415]s for largest resting state data
#     """
#    condition = VisualClassifier()
#    if cat == 'Rest':
#        events_1 = mne.make_fixed_length_events(raw, id=32, start=5, 
#                                                stop=205, duration=2, first_samp=False, overlap=0.0)
#        events_2 = mne.make_fixed_length_events(raw, id=32, 
#                                                start=215, stop=415, duration=2, first_samp=False, overlap=0.0)
#        
#        events = np.concatenate((events_1,events_2))
#        rest_id = {'Rest': 32}
#        # epoch
#        epochs= mne.Epochs(raw, events, event_id= rest_id, 
#                            tmin=tmin, tmax=tmax, baseline= None, preload=True)
#    else:
#        stim_events, stim_events_id = mne.events_from_annotations(raw)
#        condition_id = condition.extract_stim_id(stim_events_id, cat = cat)
#        epochs= mne.Epochs(raw, stim_events, event_id= stim_events_id, 
#                            tmin=tmin, tmax=tmax, baseline= None, preload=True)
#        epochs = epochs[condition_id]
#        events = epochs.events
#    return epochs, events

def sort_visual_chan(sorted_indices, hfb):
    """
    Order visual hfb channels indices along visual herarchy (Y coordinate)
    """
    X = hfb.get_data()
    X_ordered = np.zeros_like(X)
    for idx, i in enumerate(sorted_indices):
            X_ordered[:,idx,:] = X[:,i,:]
    X = X_ordered
    return X


def sort_indices(hfb, visual_chan):
    """
    Order channel indices along visual hierarchy
    """
    unsorted_chan = hfb.info['ch_names']
    
    sorted_indices = [0]*len(visual_chan)
    for idx, chan in enumerate(unsorted_chan):
        sorted_indices[idx] = visual_chan.index(chan)
    return sorted_indices

def parcellation_to_indices(visual_population, parcellation='group', matlab=False):
    """
    Return indices of channels from a given population
    parcellation: group (default, functional), DK (anatomical)
    """
    group = visual_population[parcellation].unique().tolist()
    group_indices = dict.fromkeys(group)
    for key in group:
       group_indices[key] = visual_population.loc[visual_population[parcellation]== key].index.to_list()
    if matlab == True: # adapt indexing for matlab
        print("Adapt indexing to matlab format")
        for key in group:
            for i in range(len(group_indices[key])):
                group_indices[key][i] = group_indices[key][i] + 1
    return group_indices

#%% Return population specifc hfb

def ts_to_population_hfb(ts, visual_populations, parcellation='group'):
    """
    Return hfb of each population of visual channels for each condition.
    """
    (nchan, nobs, ntrials, ncat) = ts.shape
    populations_indices = parcellation_to_indices(visual_populations,
                                                     parcellation=parcellation)
    populations = populations_indices.keys()
    npop = len(populations)
    population_hfb = np.zeros((npop, nobs, ntrials, ncat))
    for ipop, pop in enumerate(populations):
        pop_indices = populations_indices[pop]
        # population hfb is average of hfb over each population-specific channel
        population_hfb[ipop,...] = np.average(ts[pop_indices,...], axis=0)
    # Return list of populations to keep track of population ordering
    populations = list(populations)
    return population_hfb, populations

#%% Plot functional connectivity

def plot_functional_connectivity(fc, df_visual, sfreq=100,
                                 rotation=90, tau_x=0.5, tau_y=0.8, 
                                 font_scale=1.6):
    """
    This function plot mutual information and transfer entropy matrices 
    as heatmaps
    
    tau_x: translattion parameter for x coordinate of statistical significance
    tau_y: translattion parameter for y coordinate of statistical significance
    rotation: rotation of xticks and yticks labels
    te_max : maximum value for TE scale
    mi_max: maximum value for MI scale
    """
    # Granger causality matrix
    f = fc['F']
    sig_gc = fc['sig_GC']
    # Mutual information matrix
    mi = fc['MI']
    mi_max = np.amax(mi)
    sig_mi = fc['sig_MI']
    # Conditions
    conditions = ['Rest', 'Face', 'Place']
    n_cdt = len(conditions)
    # Convert to transfer entropy
    te = np.zeros_like(f)
    for icat in range(n_cdt):
        te[:,:,icat] = GC_to_TE(f[:,:,icat], sfreq=sfreq)
    te_max = np.amax(te)
    # Plot TE and MI as heatmap
    sns.set(font_scale=1.6)
    fig, ax = plt.subplots(3,2, figsize=(15,15))
    for icat in range(n_cdt):
        populations = df_visual['group']
        g = sns.heatmap(mi[:,:,icat], vmin=0, vmax=mi_max, xticklabels=populations,
                        yticklabels=populations, cmap='YlOrBr', ax=ax[icat,0])
        g.set_yticklabels(g.get_yticklabels(), rotation = rotation)
        # Position xticks on top of heatmap
        ax[icat, 0].xaxis.tick_top()
        ax[0,0].set_title('Mutual information (bit)')
        ax[icat, 0].set_ylabel(conditions[icat])
        g = sns.heatmap(te[:,:,icat], vmin=0, vmax=te_max, xticklabels=populations,
                        yticklabels=populations, cmap='YlOrBr', ax=ax[icat,1])
        g.set_yticklabels(g.get_yticklabels(), rotation = rotation)
        ax[icat, 1].xaxis.tick_top()
        ax[icat, 1].set_ylabel('Target')
        ax[0,1].set_title('Transfer entropy (bit/s)')
        # Plot statistical significant entries
        for y in range(f.shape[0]):
            for x in range(f.shape[1]):
                if sig_mi[y,x,icat] == 1:
                    ax[icat,0].text(x + tau_x, y + tau_y, '*',
                             horizontalalignment='center', verticalalignment='center',
                             color='k')
                else:
                    continue
                if sig_gc[y,x,icat] == 1:
                    ax[icat,1].text(x + tau_x, y + tau_y, '*',
                             horizontalalignment='center', verticalalignment='center',
                             color='k')
                else:
                    continue

def GC_to_TE(f, sfreq=250):
    """
    Convert GC to transfer entropy
    """
    sample_to_bits = 1/np.log(2)
    te = 1/2*sample_to_bits*sfreq*f
    return te

#%% Spectral granger causality

def spcgc_to_smvgc(f, roi_idx):
    """
    Average pairwise conditional spectral GC over ROI
    ---------
    f: array of pairwise conditional spectral GC
    roi_idx: dictionary containing indices of channels belonging to specific
    ROI
    """
    (nchan, nchan, nfreq, n_cdt) = f.shape
    roi = list(roi_idx.keys())
    n_roi = len(roi)
    f_roi = np.zeros((n_roi, n_roi, nfreq, n_cdt))
    for i in range(n_roi):
        for j in range(n_roi):
            source_idx = roi_idx[roi[j]]
            target_idx = roi_idx[roi[i]]
            # Take subarray of source and target indices to compute smvgc
            f_subarray = np.take(f, indices=target_idx, axis=0)
            f_subarray = np.take(f_subarray, indices=source_idx, axis=1)
            f_roi[i, j,:,:] = np.average(f_subarray, axis=(0,1))
    return f_roi


def read_roi(df_visual, roi="functional"):
    """
    Read indices of channels belong to specific 
    anatomical or functional ROI
    """
    functional_idx = parcellation_to_indices(df_visual, 'group', matlab=False)
    anatomical_idx = parcellation_to_indices(df_visual, 'DK', matlab=False)
    if roi=="functional":
        roi_idx = functional_idx
    else:
        roi_idx = anatomical_idx
        roi_idx = {'LO': roi_idx['ctx-lh-lateraloccipital'], 
               'Fus': roi_idx['ctx-lh-fusiform'] }
    return roi_idx

def plot_smvgc(f_roi, roi_idx, sfreq=250, x=40, y=0.01, font_scale=1.5):
    """
    This function plot spectral pairwise conditional GC averaged over ROI
    
    x,y: coordinate of text
    """
    conditions = ['Rest', 'Face', 'Place']
    (n_roi, n_roi, nfreq, n_cdt) = f_roi.shape
    roi = list(roi_idx.keys())
    xticks = [0, 0.1, 1, 10, 100]   
    max_sgc = np.amax(f_roi)
    sns.set(font_scale=font_scale)
    freq_step = sfreq/(2*(nfreq))
    freqs = np.arange(0, sfreq/2, freq_step)
    figure, ax =plt.subplots(n_roi, n_roi, sharex=True, sharey=True, 
                             figsize=(10,8), dpi=80)
    for c in range(n_cdt):
        for i in range(n_roi):
            for j in range(n_roi):
                ax[i,j].plot(freqs, f_roi[i,j,:,c], label = f'{conditions[c]}', 
                             linewidth=2.5)
                ax[i,j].text(x=x, y=y, s=f'{roi[j]} -> {roi[i]}')
                ax[i,j].set_ylim(bottom=0, top=max_sgc)
                ax[i,j].set_xticks(xticks)
                ax[i,j].set_xscale('log')
                ax[-1,j].set_xlabel('Frequency (Hz)')
                ax[i, 0].set_ylabel('Spectral GC')
    # Legend the color-condition correspondance
    handles, labels = plt.gca().get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    plt.legend(by_label.values(), by_label.keys())
    plt.tight_layout()

#%% Create category time series with specific channels

# def chan_specific_category_ts(picks, proc='preproc', stage='_BP_montage_HFB_raw.fif', 
#                      sub_id='DiAs', sfreq=250, tmin_crop=0, tmax_crop=1.75):
#     """
#     Create category time series with specific channels
#     """
#     subject = Subject(sub_id)
#     visual_populations = subject.pick_visual_chan()
#     hfb, visual_chan = subject.load_visual_hfb(proc= proc, 
#                                 stage= stage)
#     hfb = hfb.pick_channels(picks)
    
#     ts, time = category_ts(hfb, picks, sfreq=sfreq, tmin_crop=tmin_crop,
#                               tmax_crop=tmax_crop)
#     return ts, time

# def chan_specific_category_lfp(picks, proc='preproc', stage='_BP_montage_preprocessed_raw.fif', 
#                      sub_id='DiAs', sfreq=250, tmin_crop=0, tmax_crop=1.75):
#     """
#     Create category specific LFP time series with specific channels
#     """
#     subject = Subject(sub_id)
#     visual_populations = subject.pick_visual_chan()
#     lfp, visual_chan = subject.load_visual_hfb(proc= proc, 
#                                 stage= stage)
#     lfp = lfp.pick_channels(picks)
    
#     ts, time = category_lfp(lfp, picks, sfreq=sfreq, tmin_crop=tmin_crop,
#                               tmax_crop=tmax_crop)
#     return ts, time

# %% Substract average event related amplitude

def substract_AERA(ts, axis=2):
    """
    Substract the average event related amplitude for stimuli conditions. 
    This is useful for stationarity
    and gaussianity. Similar to detrending (remove trend due to transient increase)
    upon stimuli presentation.
    Pb: Maybe this remove too much interesting signal?
    """
    ntrials = ts.shape[axis]
    # Remove AERA on Face and Place conditions only 
    cat = [1,2]
    average_event_related_amplitude = np.average(ts, axis=axis)
    for j in cat:
        for i in range(ntrials):
            ts[:,:,i,j] -= average_event_related_amplitude[:,:,j]
    return ts

def plot_trials(ts, time, ichan=1, icat=1, label='raw'):
    """
    Plot all individual trials of a single channel ichan
    """
    sns.set()
    ntrials = ts.shape[2]
    for i in range(ntrials):
        plt.subplot(7,8,i+1)
        plt.plot(time, ts[ichan,:,i,icat], label=label)
        plt.axis('off')

#%% Cross subject functions

def cross_subject_ts(cohort_path, cohort, proc='preproc', 
                     channels = 'visual_channels.csv',
                     stage= '_hfb_extracted_raw.fif', epoch=False,
                     sfreq=250, tmin_crop=-0.5, tmax_crop=1.5):
    """
    Return cross subject time series in each condition
    ----------
    Parameters
    ----------
    
    """
    ts = [0]*len(cohort)
    for s in range(len(cohort)):
        subject = cohort[s]  
        ecog = Ecog(cohort_path, subject=subject, proc=proc, 
                       stage = stage, epoch=epoch)
        hfb = ecog.read_ecog()
        df_visual = ecog.read_channels_info(fname=channels)
        visual_chan = df_visual['chan_name'].to_list()
        ts[s], time = category_ts(hfb, visual_chan, sfreq=sfreq, 
                                  tmin_crop=tmin_crop, tmax_crop=tmax_crop)
        # Beware might raise an error if shape don't match along axis !=0
    cross_ts = np.concatenate(ts, axis=0)
    return cross_ts, time

def chanel_statistics(cross_ts, nbin=30, fontscale=1.6):
    """
    Plot skewness and kurtosis from cross channels time series to estimate
    deviation from gaussianity.
    """
    (n, m, N, c) = cross_ts.shape
    new_shape = (n, m*N, c)
    X = np.reshape(cross_ts, new_shape)
    skewness = np.zeros((n,c))
    kurtosis = np.zeros((n,c))
    for i in range(n):
        for j in range(c):
            a = X[i,:,j]
            skewness[i,j] = stats.skew(a)
            kurtosis[i,j] = stats.kurtosis(a)
    # Plot skewness, kurtosis
    condition = ['Rest', 'Face', 'Place']
    skew_xticks = np.arange(-1,1,0.5)
    kurto_xticks = np.arange(0,5,1)
    sns.set(font_scale=fontscale)
    f, ax = plt.subplots(2,3)
    for i in range(c):
        ax[0,i].hist(skewness[:,i], bins=nbin, density=False)
        ax[0,i].set_xlim(left=-1, right=1)
        ax[0,i].set_ylim(bottom=0, top=35)
        ax[0,i].xaxis.set_ticks(skew_xticks)
        ax[0,i].axvline(x=-0.5, color='k')
        ax[0,i].axvline(x=0.5, color='k')
        ax[0,i].set_xlabel(f'Skewness ({condition[i]})')
        ax[0,i].set_ylabel('Number of channels')
        ax[1,i].hist(kurtosis[:,i], bins=nbin, density=False)
        ax[1,i].set_xlim(left=0, right=5)
        ax[1,i].set_ylim(bottom=0, top=60)
        ax[1,i].axvline(x=1, color='k')
        ax[1,i].xaxis.set_ticks(kurto_xticks)
        ax[1,i].set_xlabel(f'Excess kurtosis ({condition[i]})')
        ax[1,i].set_ylabel('Number of channels')
    return skewness, kurtosis

#%% Sliding window analysis

def sliding_ts(picks, proc='preproc', stage='_BP_montage_HFB_raw.fif', sub_id='DiAs',
               tmin=0, tmax=1.75, win_size=0.2, step = 0.050, detrend=True, sfreq=250):
    """
    Return sliced hfb into win_size time window between tmin and tmax,
    overlap determined by parameter step
    """
    window = list_window(tmin=tmin, tmax=tmax, win_size=win_size, step=step)
    nwin = len(window)
    ts = [0]*nwin
    time = [0]*nwin
    for i in range(nwin):
        tmin_crop=window[i][0]
        tmax_crop=window[i][1]
        ts[i], time[i] = chan_specific_category_ts(picks, sub_id= sub_id, proc= proc, 
                                                      stage= stage, tmin_crop=tmin_crop, 
                                                      tmax_crop=tmax_crop)
        if detrend==True:
            ts[i] = substract_AERA(ts[i], axis=2)
        else:
            continue
    ts = np.stack(ts, axis=3)
    time = np.stack(time, axis=-1)
    return ts, time

def sliding_lfp(picks, proc='preproc', stage='_BP_montage_preprocessed_raw.fif', sub_id='DiAs',
               tmin=0, tmax=1.75, win_size=0.2, step = 0.050, detrend=True, sfreq=250):
    """
    Return sliced lfp into win_size time window between tmin and tmax,
    overlap determined by parameter step
    """
    window = list_window(tmin=tmin, tmax=tmax, win_size=win_size, step=step)
    nwin = len(window)
    ts = [0]*nwin
    time = [0]*nwin
    for i in range(nwin):
        tmin_crop=window[i][0]
        tmax_crop=window[i][1]
        ts[i], time[i] = chan_specific_category_lfp(picks, sub_id= sub_id, proc= proc, 
                                                      stage= stage, tmin_crop=tmin_crop, 
                                                      tmax_crop=tmax_crop)
        if detrend==True:
            ts[i] = substract_AERA(ts[i], axis=2)
        else:
            continue
    ts = np.stack(ts, axis=3)
    time = np.stack(time, axis=-1)
    return ts, time

def list_window(tmin=0, tmax=1.75, win_size=0.2, step=0.050):
    """
    Sliding_ts subroutine. Returns sliced windows.
    """
    nwin = int(np.floor((tmax - win_size)/step))
    win_start = [0]*nwin
    win_stop = [0]*nwin
    window = [0]*nwin
    
    for i in range(nwin):
        win_start[i] = tmin + step*i
        win_stop[i] = win_start[i] + win_size
        window[i] = (win_start[i], win_stop[i])
    return window

#%% Sliding window on continuous data

def category_continous_sliding_ts(hfb, tmin=0, tmax=265, step=1, win_size=10):
    """
    Return category specific sliding ts from continuous hfb or lfp
    """
    # Extract resting state hfb and stimulus hfb
    hfb_rest = hfb.copy().crop(tmin=60, tmax=325)
    hfb_stim = hfb.copy().crop(tmin=425, tmax=690)
    hfb_cat = [hfb_rest, hfb_stim]
    ncat = len(hfb_cat)
    ts = [0]*ncat
    # Return sliding window ts
    for i in range(ncat):
        ts[i], time = make_continuous_sliding_ts(hfb_cat[i], tmin=tmin, tmax=tmax, step=step, 
                                              win_size=win_size)
    ts = np.stack(ts, axis=-1)
    return ts, time

def make_continuous_sliding_ts(hfb, tmin=0, tmax=265, step=1, win_size=10):
    """
    Return sliding window from continuous hfb or lfp
    """
    window = list_window(tmin=tmin, tmax=tmax, win_size=win_size, step=step)
    nwin = len(window)
    ts = [0]*nwin
    time = [0]*nwin
    # List windowed hfb
    for i in range(nwin):
        tmin_crop = window[i][0]
        tmax_crop = window[i][1]
        ts[i] = hfb.copy().crop(tmin=tmin_crop, tmax=tmax_crop).get_data()
        time[i] = hfb.copy().crop(tmin=tmin_crop, tmax=tmax_crop).times
    ts = np.stack(ts, axis=-1)
    time = np.stack(time, axis=-1)
    return ts, time