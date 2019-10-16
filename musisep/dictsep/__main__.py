#!python3

"""
Wrapper for the dictionary learning algorithm.  When invoked, the audio
sources in the supplied audio file are separated.
"""

from __future__ import absolute_import, division, print_function

import numpy as np
import sys
import os.path
import pickle
import matplotlib
matplotlib.use('Agg')
#import matplotlib.pyplot as plt
import matplotlib.cm as cm

from ..audio import spect
from ..audio import wav
from ..audio import performance
from . import dictlearn

def main(mixed_soundfile, orig_soundfiles, out_name, inst_num, tone_num,
         pexp, qexp, har, sigmas, sampdist, spectheight, logspectheight,
         minfreq, maxfreq, runs, lifetime, num_dicts, mask, color, plot_range):
    """
    Wrapper function for the dictionary learning algorithm.

    Parameters
    ----------
    mixed_soundfile : string
        Name of the mixed input file
    orig_soundfiles : list of string or NoneType
        Names of the files with the isolated instrument tracks or None
    out_name : string
        Prefix for the file names
    inst_num : int
        Number of instruments
    tone_num : int
        Maximum number of simultaneous tones for each instrument
    pexp : float
        Exponent for the addition of sinusoids
    qexp : float
        Exponent to be applied on the spectrum
    har : int
        Number of harmonics
    sigmas : float
        Number of standard deviations after which to cut the window/kernel
    sampdist : int
        Time intervals to sample the spectrogram
    spectheight : int
        Height of the linear-frequency spectrogram
    logspectheight : int
        Height of the log-frequency spectrogram
    minfreq : float
        Minimum frequency in Hz to be represented (included)
    maxfreq : float
        Maximum frequency in Hz to be represented (excluded)
    runs : int
        Number of training iterations to perform
    lifetime : int
        Number of steps after which to renew the dictionary
    num_dicts : int
        Number of different dictionaries to generate and train
    mask : bool
        Whether to apply spectral masking
    color : bool or string
        Whether color should be used, or specification of the color scheme
    plot_range : slice or NoneType
        part of the spectrogram to plot
    """

    signal, samprate = wav.read(mixed_soundfile)

    plotlen = signal.size

    #matplotlib.rcParams['agg.path.chunksize'] = 10000

    orig_spectrum = spect.spectrogram(
        signal, spectheight, sigmas, sampdist)[:spectheight, :]

    if plot_range is not None:
        spect.spectwrite('output/{}-orig.png'.format(out_name),
                         orig_spectrum[:spectheight, plot_range],
                         color)

    if orig_soundfiles is None:
        orig_signals = None
    else:
        orig_signals = np.asarray([wav.read(f)[0] for f in orig_soundfiles])
        orig_spectrums = [spect.spectrogram(
            os, spectheight, sigmas, sampdist)[:spectheight, :]
            for os in orig_signals]

    fsigma = sigmas/np.pi

    if (os.path.exists('output/{}-lin.npy'.format(out_name))
        and os.path.exists('output/{}-log.npy'.format(out_name))):
        linspect = np.load('output/{}-lin.npy'.format(out_name))
        logspect = np.load('output/{}-log.npy'.format(out_name))
    else:
        logspect, linspect = spect.logspect_pursuit(signal, spectheight,
                                                    sigmas, sampdist, None,
                                                    minfreq/samprate,
                                                    maxfreq/samprate,
                                                    logspectheight, fsigma)
        np.save('output/{}-lin.npy'.format(out_name), linspect)
        np.save('output/{}-log.npy'.format(out_name), logspect)

    if plot_range is not None:
        spect.spectwrite('output/{}-lin.png'.format(out_name),
                         linspect[:, plot_range], color)
        spect.spectwrite('output/{}-log.png'.format(out_name),
                         logspect[:, plot_range], color)

    audio_measures = []

    for r in range(0, num_dicts):
        print("seed: {}".format(r))
        out_name_run = out_name + '-{}'.format(r)
        np.random.seed(r)

        if os.path.exists('output/{}-dict.npy'.format(out_name_run)):
            inst_dict = np.load('output/{}-dict.npy'.format(out_name_run))
        else:
            inst_dict = dictlearn.learn_spect_dict(
                logspect, fsigma, tone_num, inst_num*2, pexp, qexp,
                har, logspectheight, minfreq, maxfreq, runs, lifetime)
            np.save('output/{}-dict.npy'.format(out_name_run), inst_dict)

        print(inst_dict)

        if os.path.exists('output/{}-spect.pkl'.format(out_name_run)):
            [dict_spectrum, inst_spectrums,
             dict_spectrum_lin, inst_spectrums_lin] = \
                pickle.load(open('output/{}-spect.pkl'.format(out_name_run),
                                 'rb'))
        else:
            (dict_spectrum, inst_spectrums,
             dict_spectrum_lin, inst_spectrums_lin) = \
                dictlearn.synth_spect(
                    logspect, tone_num, inst_dict, fsigma,
                    spectheight, pexp, qexp,
                    minfreq/samprate, maxfreq/samprate)
            pickle.dump([dict_spectrum, inst_spectrums,
                         dict_spectrum_lin, inst_spectrums_lin],
                        open('output/{}-spect.pkl'.format(out_name_run), 'wb'))

        if mask:
            inst_spectrums_lin, mask_spect = dictlearn.mask_spectrums(
                inst_spectrums_lin, orig_spectrum)
            dict_spectrum_lin = dict_spectrum_lin * mask_spect
            mask_str = "mask"
        else:
            mask_str = "nomask"

        if plot_range is not None:
            spect.spectwrite('output/{}-synth-{}.png'
                             .format(out_name_run, mask_str),
                             dict_spectrum[:, plot_range], color)
            spect.spectwrite('output/{}-synth-lin-{}.png'
                             .format(out_name_run, mask_str),
                             dict_spectrum_lin[:, plot_range], color)
            for i in range(len(inst_spectrums)):
                spect.spectwrite(
                    'output/{}-synth{}-{}.png'
                    .format(out_name_run, i, mask_str),
                    inst_spectrums[i][:, plot_range], color)
                spect.spectwrite(
                    'output/{}-synth{}-lin-{}.png'
                    .format(out_name_run, i, mask_str),
                    inst_spectrums_lin[i][:, plot_range], color)

        siglen = signal.size
        synth_signals = np.zeros((inst_num, siglen))
        audio, _ = spect.synth_audio(dict_spectrum_lin, siglen,
                                     sigmas, sampdist, 1, signal)
        wav.write('output/{}-synth-{}.wav'.format(out_name_run, mask_str),
                  audio, samprate)
        for i in range(len(inst_spectrums_lin)):
            audio, _ = spect.synth_audio(inst_spectrums_lin[i],
                                         siglen, sigmas, sampdist, 1,
                                         signal)
            synth_signals[i, :] = audio
            wav.write('output/{}-synth{}-{}.wav'
                      .format(out_name_run, i, mask_str),
                      audio, samprate)

        if orig_signals is not None:
            perm, perf = performance.select_perm(*performance.measures(
                synth_signals, orig_signals))
            audio_measures.append(perf)
            print("Permutation:")
            print(perm)
            print("Performance:")
            print(perf)

    if orig_signals is not None:
        audio_measures = np.asarray(audio_measures)
        print("Global measures mean:")
        print(np.mean(audio_measures, axis=0))
        print("Global measures stdev:")
        print(np.std(audio_measures, axis=0, ddof=1))
        bestidx = np.argmax(np.sum(audio_measures, axis=2)[:, 0])
        print("Global measures best index: {}".format(bestidx))
        print("Global measures best:")
        print(audio_measures[bestidx, :, :])

def separate_two(mixed_soundfile, orig_soundfiles, out_name, inst_num=2,
                 tone_num=1, pexp=1, qexp=0.5, har=25, sigmas=6, sampdist=256,
                 spectheight=6*1024, logspectheight=1024, minfreq=20,
                 maxfreq=20480, runs=10000, lifetime=500, num_dicts=10,
                 mask=True, color=False, plot_range=None):
    """
    Separation of a sample with two instruments with sensible default
    parameters.

    Parameters
    ----------
    mixed_soundfile : string
        Name of the mixed input file
    orig_soundfiles : list of string or NoneType
        Names of the files with the isolated instrument tracks or None
    out_name : string
        Prefix for the file names
    inst_num : int
        Number of instruments
    tone_num : int
        Maximum number of simultaneous tones for each instrument
    pexp : float
        Exponent for the addition of sinusoids
    qexp : float
        Exponent to be applied on the spectrum
    har : int
        Number of harmonics
    sigmas : float
        Number of standard deviations after which to cut the window/kernel
    sampdist : int
        Time intervals to sample the spectrogram
    spectheight : int
        Height of the linear-frequency spectrogram
    logspectheight : int
        Height of the log-frequency spectrogram
    minfreq : float
        Minimum frequency in Hz to be represented (included)
    maxfreq : float
        Maximum frequency in Hz to be represented (excluded)
    runs : int
        Number of training iterations to perform
    lifetime : int
        Number of steps after which to renew the dictionary
    num_dicts : int
        Number of different dictionaries to generate and train
    mask : bool
        Whether to apply spectral masking
    color : bool or string
        Whether color should be used, or specification of the color scheme
    plot_range : slice or NoneType
        part of the spectrogram to plot
    """

    main(mixed_soundfile, orig_soundfiles, out_name, inst_num, tone_num,
         pexp, qexp, har, sigmas, sampdist, spectheight, logspectheight,
         minfreq, maxfreq, runs, lifetime, num_dicts, mask, color, plot_range)

def separate_mozart_recorder_violin():
    "Separation of recorder and violin on the piece by Mozart"

    separate_two(mixed_soundfile='input/mozart/mix.wav',
                 orig_soundfiles=['input/mozart/recorder.wav',
                                  'input/mozart/violin.wav'],
                 out_name='mozart/mozart',
                 runs=100000,
                 mask=False,
                 plot_range=slice(0, 1580))
    separate_two(mixed_soundfile='input/mozart/mix.wav',
                 orig_soundfiles=['input/mozart/recorder.wav',
                                  'input/mozart/violin.wav'],
                 out_name='mozart/mozart',
                 runs=100000,
                 mask=True,
                 plot_range=slice(0, 1580))

def separate_mozart_clarinet_piano():
    "Separation of clarinet and piano on the piece by Mozart"

    separate_two(mixed_soundfile='input/mozart-cl/mix-cl-piano.wav',
                 orig_soundfiles=['input/mozart-cl/clarinet-high.wav',
                                  'input/mozart-cl/piano-low.wav'],
                 out_name='mozart-cl-p1-lin/mozart')

def separate_jaiswal(number):
    """
    Separation of the data by Jaiswal et al.

    Parameters
    ----------
    number : int
        Number of the sample to be considered.
    """

    separate_two(mixed_soundfile='input/jaiswal/test{}.wav'.format(number),
                 orig_soundfiles=['input/jaiswal/test{}-01.wav'.format(number),
                                  'input/jaiswal/test{}-02.wav'.format(number)],
                 out_name='jaiswal/jaiswal{}'.format(number))

if __name__ == '__main__':
    separate_mozart_recorder_violin()
    separate_mozart_clarinet_piano()

    # The number of the sample is given via command line.
    # Unfortunately, we cannot distribute the data.
    #separate_jaiswal(int(sys.argv[1]))
