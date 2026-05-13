#!/usr/bin/env bash

cd output/
ambf_simulator --launch_file launch_registration.yaml -l 0,1 --registration_config registration_config.yaml  --tf_list tf_config.yaml
