#!/usr/bin/env bash

python create_saint_config.py \
    --saint-root /home/juan95/research/discovery_grant/volumetric_drilling \
    --drill-size 4 \
    --phantom-path /home/juan95/research/discovery_grant/saint_tools/nrrd_to_adf_hisashi/data/output3/phantom_01_05.yaml \
    --marker-namespace /atracsys/drill_marker \
    --output-dir output0/
