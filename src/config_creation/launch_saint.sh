#!/usr/bin/env bash

cd output/

ambf_simulator --launch_file launch.yaml -l 6,10,14 --mute true --nt 1 --tf_list tf_config.yaml
