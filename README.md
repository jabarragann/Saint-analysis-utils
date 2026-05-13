
## Saint config generator
```
python nrrd_to_adf.py -n data/sample_data/P01_05_real_seg.seg.nrrd -a ./data/output2/phantom_01_05.yaml -p slices00 -s True --slices_path ./data/output2/slices  -f ./data/sample_data/P01_05_real_pre.mrk.json -v mastoidectomy_volume
```

```
python create_saint_config.py --saint-root /home/juan95/research/discovery_grant/volumetric_drilling --drill-size 4 --phantom-path data/output2/phantom_01_05.yaml --marker-namespace /atracsys/drill_marker --output-dir data/config_output0/ 
```

Note to juan: this script only work with pyenv ros_jazzy in rog pc. `source ~/pyvenv/ros_jazzy/bin/activate`
## Slicer automation
```
slicer  --no-main-window --python-script analysis_automation.py
```
