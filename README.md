# MiniCubeCodes
Codes I've written to work with the LArPix 5x5 setup at Wellesley


run_live.py was made to watch the full board in real time. As it is currently uploaded (October 15, 2026), it runs with a pedestal test configuration, meaning that there is a periodic rolling trigger. 

run_live-onechan.py monitors a single channel and turns on the analog monitor for the channel being investigated. It also allows sending a testpulse in. 

test_gain.py is adapted from code in csr_dac to configure and run a gain test. It does not send in test pulses. That must be done externally with channel_gains_5x5.py, which sends in test pulses to each chip, one channel at a time. 

QuickVisBoardStats.py is meant to quickly plot mean, std, kurtosis, and timestamp variation for the full 5x5 board at once as a hasty evaluation of the data. 
