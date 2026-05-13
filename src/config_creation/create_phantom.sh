#!/usr/bin/env bash

python nrrd_to_adf.py --nrrd_file data/sample_data/P01_05_real_seg.seg.nrrd \
                      --adf_filepath ./data/output4/phantom_01_05.yaml \ 
                      -p slices00 -s True \ 
                      --slices_path ./data/output4/slices \ 
                      --fiducial_filepath ./data/sample_data/P01_05_pre.mrk.json \
                      -v mastoidectomy_volume
