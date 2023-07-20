# ASL Pipeline for the Human Connectome Project
This repository contains the ASL processing pipeline scripts for the Human Connectome Project.

## Contents
- [Prerequisites](#prerequisites)
- [Installation](#installation)

## Prerequisites
The HCP list some prerequisites for their pipelines: https://github.com/Washington-University/HCPpipelines/wiki/Installation-and-Usage-Instructions.

The prerequisites specific to this pipeline, along with links to their installation pages, are listed below:
- [FSL](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation) (version >= 6.0.5.1)
- [Workbench](https://www.humanconnectome.org/software/get-connectome-workbench) (version >= 1.5.0)
- [HCP Pipelines](https://github.com/Washington-University/HCPpipelines)
- [HCP's gradunwarp](https://github.com/Washington-University/gradunwarp)
- [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall)

FSL version 6.0.5.1 is required to use new features in `fabber` and `oxford_asl_roi_stats.py`, which were added for this pipeline.

Workbench >= v1.5.0 is required. The `-weighted` option in `wb_command`'s `-volume-to-surface-mapping` introduced in version 1.5.0 is used in projections to the surface. The environment variable `CARET7DIR` should point to directory containing the `wb_command` executable. 

The HCP Pipelines must be installed and the environment variable `HCPPIPEDIR` set in order for the (Sub-)Cortical LUTs to be used in SE-based bias correction.

FreeSurfer must be installed to enable boundary-based registration (BBR). The environment variable `FREESURFER_HOME` must be set. 

## Installation
It is advised that the pipeline is installed in a conda environment, for example following the steps below. The pipeline cannot natively be installed on Mac arm64 processors due to dependency incompatibility, but Rosetta emulation can be used. 

```
conda create -n hcpasl python=3.7 cython numpy
conda activate hcpasl
pip install git+https://github.com/physimals/hcp-asl.git 
```

## Usage
Once installed, the pipeline may be run as a command-line script as follows:

```
hcp_asl --studydir ${StudyDir} --subid ${Subjectid} --mbpcasl ${mbpcasl} --fmap_ap ${SEFM_AP} --fmap_pa ${SEFM_PA} -g ${GradientCoeffs}
```

The filepaths passed to the script may be relative or absolute. A more detailed explanation of the arguments, including optionals, can be found by running:

```
process_hcp_asl --help
```

## Pipeline stages

The pipeline can be run in stages via the `--stages a b c` argument. The stages are numbered 0 to 13 inclusive and perform the following operations. Note, each stage assumes the previous stages have run successfully, and will raise various errors if the outputs of those stages cannot be found. 

0. Split mbPCASL sequence into ASL series and M0 images.
1. Derive gradient and EPI distortion correction 
2. Correct M0 image 
3. Correct ASL image 
4. Label-control subtraction in ASL space 
5. Perfusion estimation in ASL space 
6. Registration and resampling of ASL/M0 into ASL-gridded T1w space 
7. Partial volume estimation in ASL-gridded T1w space 
8. Label-control subtraction in ASL-gridded T1w space 
9. Perfusion estimation in ASL-gridded T1w space 
10. Summary statistics within ROIs 
11. Volume to surface projection 
12. Copy key results into `$outdir/T1w/ASL` and `$outdir/MNINonLinear/ASL` 
13. Create QC report 

## Extended pipeline outputs 

Below is a directory tree within a subject's `{SUBJID}_V1_MR` folder showing the location of final and intermediate pipeline outputs. The default output directory has been used, so outputs are stored within the `{SUBJID}_V1_MR` folder. 

```python
SUBJID_V1_MR
├── ASL
│   ├── Calib # Intermediate calibration image processing 
│   │   ├── Calib0
│   │   │   ├── BiasCorr
│   │   │   │   ├── SEbased
│   │   │   │   │   ├── AllGreyMatter.nii.gz
│   │   │   │   │   └── sebased_bias_dil.nii.gz
│   │   │   │   ├── gdc_dc_calib0_bias.nii.gz
│   │   │   │   └── gdc_dc_calib0_restore.nii.gz
│   │   │   ├── DistCorr
│   │   │   │   ├── asl2orig_mgz_initial_bbr.dat
│   │   │   │   ├── asl2struct.mat
│   │   │   │   ├── asl2struct_reg.log
│   │   │   │   ├── gdc_calib0.nii.gz
│   │   │   │   ├── gdc_dc_calib0.nii.gz
│   │   │   │   └── struct2asl.mat
│   │   │   ├── MTCorr
│   │   │   │   ├── mtcorr_gdc_calib0.nii.gz
│   │   │   │   └── mtcorr_gdc_dc_calib0_restore.nii.gz
│   │   │   ├── aslfs_mask.nii.gz
│   │   │   ├── calib0.nii.gz
│   │   │   └── calib_timing.nii.gz
│   │   ├── Calib1
│   │   │   ├── BiasCorr
│   │   │   │   ├── SEbased
│   │   │   │   │   ├── AllGreyMatter.nii.gz
│   │   │   │   │   └── sebased_bias_dil.nii.gz
│   │   │   │   ├── gdc_dc_calib1_bias.nii.gz
│   │   │   │   └── gdc_dc_calib1_restore.nii.gz
│   │   │   ├── DistCorr
│   │   │   │   ├── asl2orig_mgz_initial_bbr.dat
│   │   │   │   ├── asl2orig_mgz_initial_bbr.log
│   │   │   │   ├── asl2struct.mat
│   │   │   │   ├── asl2struct_reg.log
│   │   │   │   ├── gdc_calib1.nii.gz
│   │   │   │   ├── gdc_dc_calib1.nii.gz
│   │   │   │   └── struct2asl.mat
│   │   │   ├── MTCorr
│   │   │   │   ├── mtcorr_gdc_calib1.nii.gz
│   │   │   │   └── mtcorr_gdc_dc_calib1_restore.nii.gz
│   │   │   ├── aslfs_mask.nii.gz
│   │   │   └── calib1.nii.gz
│   │   └── correct_M0.log
│   ├── OxfordASL # Basic perfusion estimates for BBR registration 
│   │   ├── logfile
│   │   ├── native_space
│   │   │   ├── aCBV.nii.gz
│   │   │   ├── arrival.nii.gz
│   │   │   ├── arrival_var.nii.gz
│   │   │   ├── mask.nii.gz
│   │   │   ├── perfusion.nii.gz
│   │   │   └── perfusion_var.nii.gz
│   │   ├── oxford_asl.log
│   │   └── oxford_asl_inputs
│   │       ├── beta_perf.nii.gz
│   │       └── brain_fov_mask.nii.gz
│   ├── TIs  # Intermediate ASL timeseries processing 
│   │   ├── BiasCorr
│   │   │   ├── tis_biascorr.nii.gz
│   │   │   └── tis_dc_restore.nii.gz
│   │   ├── DistCorr
│   │   │   └── FirstPass
│   │   │       ├── dc_tis.nii.gz
│   │   │       ├── temp_reg_dc_tis.nii.gz
│   │   │       └── tis_gdc.nii.gz
│   │   ├── MTCorr
│   │   │   ├── tis_dc_restore_mtcorr.nii.gz
│   │   │   ├── tis_mtcorr.nii.gz
│   │   │   ├── tis_mtcorr_even.nii.gz
│   │   │   └── tis_mtcorr_odd.nii.gz
│   │   ├── MoCo
│   │   │   ├── asln2m0.mat
│   │   │   │   ├── MAT_0000
│   │   │   │   └── MAT_0085
│   │   │   ├── asln2m0_final.mat
│   │   │   │   ├── MAT_0000
│   │   │   │   └── MAT_0085
│   │   │   ├── final_registration_TIs.nii.gz
│   │   │   ├── final_registration_TIs.nii.gz.par
│   │   │   ├── fov_mask.nii.gz # Final motion-FoV mask 
│   │   │   ├── fov_mask_initial.nii.gz
│   │   │   ├── initial_registration_TIs.nii.gz
│   │   │   ├── initial_registration_TIs.nii.gz.par
│   │   │   ├── reg_dc_tis_biascorr.nii.gz
│   │   │   ├── reg_mt_scaling_factors.nii.gz
│   │   │   ├── temp_reg_dc_tis_mtcorr.nii.gz
│   │   │   ├── temp_reg_dc_tis_mtcorr_even.nii.gz
│   │   │   ├── temp_reg_dc_tis_mtcorr_odd.nii.gz
│   │   │   └── tis_dc_moco.nii.gz
│   │   ├── MotionSubtraction
│   │   │   ├── beta_baseline.nii.gz
│   │   │   ├── beta_perf.nii.gz
│   │   │   ├── combined_mask.nii.gz
│   │   │   └── difference_mask.nii.gz
│   │   ├── STCorr
│   │   │   ├── st_scaling_factors.nii.gz
│   │   │   └── tis_stcorr.nii.gz
│   │   ├── STCorr2
│   │   │   ├── combined_scaling_factors_asln.nii.gz
│   │   │   ├── st_scaling_factors.nii.gz
│   │   │   └── tis_dc_restore_mtcorr_stcorr.nii.gz
│   │   ├── SatRecov
│   │   │   ├── nospatial
│   │   │   │   ├── finalMVN.nii.gz
│   │   │   │   ├── logfile
│   │   │   │   ├── mean_A.nii.gz
│   │   │   │   ├── mean_M0t.nii.gz
│   │   │   │   └── mean_T1t.nii.gz
│   │   │   └── spatial
│   │   │       ├── logfile
│   │   │       ├── mean_A.nii.gz
│   │   │       ├── mean_M0t.nii.gz
│   │   │       ├── mean_T1t.nii.gz
│   │   │       └── mean_T1t_filt.nii.gz
│   │   ├── SatRecov2
│   │   │   ├── nospatial
│   │   │   │   ├── finalMVN.nii.gz
│   │   │   │   ├── logfile
│   │   │   │   ├── mean_A.nii.gz
│   │   │   │   ├── mean_M0t.nii.gz
│   │   │   │   └── mean_T1t.nii.gz
│   │   │   └── spatial
│   │   │       ├── logfile
│   │   │       ├── mean_A.nii.gz
│   │   │       ├── mean_M0t.nii.gz
│   │   │       ├── mean_T1t.nii.gz
│   │   │       ├── mean_T1t_filt.nii.gz
│   │   │       └── mean_T1t_filt_asln.nii.gz
│   │   ├── brain_fov_mask.nii.gz # Combined brain and motion-FoV mask 
│   │   ├── brain_fov_mask_initial.nii.gz
│   │   ├── brain_mask.nii.gz
│   │   ├── combined_scaling_factors.nii.gz
│   │   ├── tis.nii.gz # Raw ASL timeseries 
│   │   ├── tis_dc_moco_restore.nii.gz
│   │   └── tis_dc_moco_restore_bandcorr.nii.gz # Fully corrected timeseries
│   ├── distortion_estimation.log
│   ├── gradient_unwarp
│   │   ├── fullWarp_abs.nii.gz
│   │   └── gdc_corr_vol1.nii.gz
│   ├── single_step_resample_to_asl0.log
│   └── topup
│       ├── Jacobian_01.nii.gz
│       └── topup_params.txt
├── HCD0378150_V1_MR_hcp_asl.log
├── MNINonLinear
│   └── ASL
│       ├── CIFTIPrepare # For preparing CIFTI outputs 
│       │   ├── arrival_Atlas.dscalar.nii
│       │   ├── arrival_AtlasSubcortical_s2.nii.gz
│       │   ├── arrival_MNI.nii.gz
│       │   ├── arrival_var_Atlas.dscalar.nii
│       │   ├── arrival_var_AtlasSubcortical_s2.nii.gz
│       │   ├── arrival_var_MNI.nii.gz
│       │   ├── asl_grid_mni.nii.gz
│       │   ├── perfusion_calib_Atlas.dscalar.nii
│       │   ├── perfusion_calib_AtlasSubcortical_s2.nii.gz
│       │   ├── perfusion_calib_MNI.nii.gz
│       │   ├── perfusion_var_calib_Atlas.dscalar.nii
│       │   ├── perfusion_var_calib_AtlasSubcortical_s2.nii.gz
│       │   ├── perfusion_var_calib_MNI.nii.gz
│       │   └── pvcorr
│       │       ├── arrival_Atlas.dscalar.nii
│       │       ├── arrival_AtlasSubcortical_s2.nii.gz
│       │       ├── arrival_MNI.nii.gz
│       │       ├── arrival_var_Atlas.dscalar.nii
│       │       ├── arrival_var_AtlasSubcortical_s2.nii.gz
│       │       ├── arrival_var_MNI.nii.gz
│       │       ├── asl_grid_mni.nii.gz
│       │       ├── perfusion_calib_Atlas.dscalar.nii
│       │       ├── perfusion_calib_AtlasSubcortical_s2.nii.gz
│       │       ├── perfusion_calib_MNI.nii.gz
│       │       ├── perfusion_var_calib_Atlas.dscalar.nii
│       │       ├── perfusion_var_calib_AtlasSubcortical_s2.nii.gz
│       │       └── perfusion_var_calib_MNI.nii.gz
│       ├── OxfordASL # Oxford ASL raw outputs 
│       │   └── std_space
│       │       ├── arrival.nii.gz
│       │       ├── arrival_var.nii.gz
│       │       ├── perfusion_calib.nii.gz
│       │       ├── perfusion_var_calib.nii.gz
│       │       └── pvcorr
│       │           ├── arrival_gm_masked.nii.gz
│       │           ├── arrival_gm_var_masked.nii.gz
│       │           ├── arrival_wm_masked.nii.gz
│       │           ├── arrival_wm_var_masked.nii.gz
│       │           ├── perfusion_gm_calib_masked.nii.gz
│       │           ├── perfusion_gm_var_calib_masked.nii.gz
│       │           ├── perfusion_wm_calib_masked.nii.gz
│       │           └── perfusion_wm_var_calib_masked.nii.gz
│       ├── arrival.nii.gz # MNI NIFTI, ATT, non-PVEc
│       ├── arrival_Atlas.dscalar.nii # MNI CIFTI, ATT, non-PVEc
│       ├── arrival_cifti_mean_nonzero.txt # ROI calculation 
│       ├── perfusion_calib.nii.gz # MNI NIFTI, perfusion, non-PVEc
│       ├── perfusion_calib_Atlas.dscalar.nii # MNI CIFTI, perfusion, non-PVEc
│       ├── perfusion_calib_cifti_mean_nonzero.txt # ROI calculation 
│       ├── pvcorr_arrival_Atlas.dscalar.nii # MNI CIFTI, ATT, PVEc
│       ├── pvcorr_arrival_cifti_mean_nonzero.txt # ROI calculation 
│       ├── pvcorr_arrival_gm_masked.nii.gz # MNI NIFTI, ATT, PVEc GM
│       ├── pvcorr_arrival_wm_masked.nii.gz # MNI NIFTI, ATT, PVEc WM
│       ├── pvcorr_perfusion_calib_Atlas.dscalar.nii # MNI CIFTI, perfusion, PVEc
│       ├── pvcorr_perfusion_calib_cifti_mean_nonzero.txt # ROI calculation 
│       ├── pvcorr_perfusion_gm_calib_masked.nii.gz # MNI NIFTI, perfusion, PVEc GM
│       └── pvcorr_perfusion_wm_calib_masked.nii.gz # MNI NIFTI, perfusion, PVEc WM
├── T1w
│   └── ASL
│       ├── CIFTIPrepare # For preparing CIFTI outputs 
│       │   ├── arrival.L.badvert_ribbonroi.native.func.gii
│       │   ├── arrival.L.native.func.gii
│       │   ├── arrival.R.badvert_ribbonroi.native.func.gii
│       │   ├── arrival.R.native.func.gii
│       │   ├── arrival_precision.nii.gz
│       │   ├── arrival_s2.atlasroi.L.32k_fs_LR.func.gii
│       │   ├── arrival_s2.atlasroi.R.32k_fs_LR.func.gii
│       │   ├── arrival_var.L.badvert_ribbonroi.native.func.gii
│       │   ├── arrival_var.L.native.func.gii
│       │   ├── arrival_var.R.badvert_ribbonroi.native.func.gii
│       │   ├── arrival_var.R.native.func.gii
│       │   ├── arrival_var_precision.nii.gz
│       │   ├── arrival_var_s2.atlasroi.L.32k_fs_LR.func.gii
│       │   ├── arrival_var_s2.atlasroi.R.32k_fs_LR.func.gii
│       │   ├── perfusion_calib.L.badvert_ribbonroi.native.func.gii
│       │   ├── perfusion_calib.L.native.func.gii
│       │   ├── perfusion_calib.R.badvert_ribbonroi.native.func.gii
│       │   ├── perfusion_calib.R.native.func.gii
│       │   ├── perfusion_calib_precision.nii.gz
│       │   ├── perfusion_calib_s2.atlasroi.L.32k_fs_LR.func.gii
│       │   ├── perfusion_calib_s2.atlasroi.R.32k_fs_LR.func.gii
│       │   ├── perfusion_var_calib.L.badvert_ribbonroi.native.func.gii
│       │   ├── perfusion_var_calib.L.native.func.gii
│       │   ├── perfusion_var_calib.R.badvert_ribbonroi.native.func.gii
│       │   ├── perfusion_var_calib.R.native.func.gii
│       │   ├── perfusion_var_calib_precision.nii.gz
│       │   ├── perfusion_var_calib_s2.atlasroi.L.32k_fs_LR.func.gii
│       │   ├── perfusion_var_calib_s2.atlasroi.R.32k_fs_LR.func.gii
│       │   └── pvcorr
│       │       ├── arrival.L.badvert_ribbonroi.native.func.gii
│       │       ├── arrival.L.native.func.gii
│       │       ├── arrival.R.badvert_ribbonroi.native.func.gii
│       │       ├── arrival.R.native.func.gii
│       │       ├── arrival_precision.nii.gz
│       │       ├── arrival_s2.atlasroi.L.32k_fs_LR.func.gii
│       │       ├── arrival_s2.atlasroi.R.32k_fs_LR.func.gii
│       │       ├── arrival_var.L.badvert_ribbonroi.native.func.gii
│       │       ├── arrival_var.L.native.func.gii
│       │       ├── arrival_var.R.badvert_ribbonroi.native.func.gii
│       │       ├── arrival_var.R.native.func.gii
│       │       ├── arrival_var_precision.nii.gz
│       │       ├── arrival_var_s2.atlasroi.L.32k_fs_LR.func.gii
│       │       ├── arrival_var_s2.atlasroi.R.32k_fs_LR.func.gii
│       │       ├── perfusion_calib.L.badvert_ribbonroi.native.func.gii
│       │       ├── perfusion_calib.L.native.func.gii
│       │       ├── perfusion_calib.R.badvert_ribbonroi.native.func.gii
│       │       ├── perfusion_calib.R.native.func.gii
│       │       ├── perfusion_calib_precision.nii.gz
│       │       ├── perfusion_calib_s2.atlasroi.L.32k_fs_LR.func.gii
│       │       ├── perfusion_calib_s2.atlasroi.R.32k_fs_LR.func.gii
│       │       ├── perfusion_var_calib.L.badvert_ribbonroi.native.func.gii
│       │       ├── perfusion_var_calib.L.native.func.gii
│       │       ├── perfusion_var_calib.R.badvert_ribbonroi.native.func.gii
│       │       ├── perfusion_var_calib.R.native.func.gii
│       │       ├── perfusion_var_calib_precision.nii.gz
│       │       ├── perfusion_var_calib_s2.atlasroi.L.32k_fs_LR.func.gii
│       │       └── perfusion_var_calib_s2.atlasroi.R.32k_fs_LR.func.gii
│       ├── Calib
│       │   └── Calib0
│       │       ├── DistCorr
│       │       │   ├── calib0_dc.nii.gz
│       │       │   └── calib_mt_scaling_factors.nii.gz
│       │       ├── SEbased
│       │       │   ├── AllGreyMatter.nii.gz
│       │       │   └── sebased_bias_dilall.nii.gz
│       │       ├── calib0_corr_aslt1w.nii.gz # Fully corrected M0 for alternative modelling 
│       │       ├── calib_aslt1w_stcorr_factors.nii.gz
│       │       └── calib_aslt1w_timing.nii.gz
│       ├── OxfordASL # Oxford ASL inputs/outputs 
│       │   ├── calib
│       │   │   ├── M0.txt
│       │   │   ├── logfile
│       │   │   └── refmask.nii.gz
│       │   ├── logfile
│       │   ├── native_space
│       │   │   ├── aCBV.nii.gz
│       │   │   ├── aCBV_calib.nii.gz
│       │   │   ├── arrival.nii.gz
│       │   │   ├── arrival_gm_mean.txt
│       │   │   ├── arrival_var.nii.gz
│       │   │   ├── arrival_wm_mean.txt
│       │   │   ├── gm_mask.nii.gz
│       │   │   ├── gm_roi.nii.gz
│       │   │   ├── mask.nii.gz
│       │   │   ├── perfusion.nii.gz
│       │   │   ├── perfusion_calib.nii.gz
│       │   │   ├── perfusion_calib_gm_mean.txt
│       │   │   ├── perfusion_calib_wm_mean.txt
│       │   │   ├── perfusion_gm_mean.txt
│       │   │   ├── perfusion_norm.nii.gz
│       │   │   ├── perfusion_var.nii.gz
│       │   │   ├── perfusion_var_calib.nii.gz
│       │   │   ├── perfusion_var_norm.nii.gz
│       │   │   ├── perfusion_wm_mean.txt
│       │   │   ├── pvcorr
│       │   │   │   ├── aCBV.nii.gz
│       │   │   │   ├── aCBV_calib.nii.gz
│       │   │   │   ├── arrival.nii.gz
│       │   │   │   ├── arrival_gm_mean.txt
│       │   │   │   ├── arrival_masked.nii.gz
│       │   │   │   ├── arrival_var.nii.gz
│       │   │   │   ├── arrival_var_masked.nii.gz
│       │   │   │   ├── arrival_wm.nii.gz
│       │   │   │   ├── arrival_wm_masked.nii.gz
│       │   │   │   ├── arrival_wm_var.nii.gz
│       │   │   │   ├── arrival_wm_var_masked.nii.gz
│       │   │   │   ├── arrival_wm_wm_mean.txt
│       │   │   │   ├── perfusion.nii.gz
│       │   │   │   ├── perfusion_calib.nii.gz
│       │   │   │   ├── perfusion_calib_gm_mean.txt
│       │   │   │   ├── perfusion_calib_masked.nii.gz
│       │   │   │   ├── perfusion_gm_mean.txt
│       │   │   │   ├── perfusion_masked.nii.gz
│       │   │   │   ├── perfusion_norm.nii.gz
│       │   │   │   ├── perfusion_var.nii.gz
│       │   │   │   ├── perfusion_var_calib.nii.gz
│       │   │   │   ├── perfusion_var_calib_masked.nii.gz
│       │   │   │   ├── perfusion_var_norm.nii.gz
│       │   │   │   ├── perfusion_wm.nii.gz
│       │   │   │   ├── perfusion_wm_calib.nii.gz
│       │   │   │   ├── perfusion_wm_calib_masked.nii.gz
│       │   │   │   ├── perfusion_wm_calib_wm_mean.txt
│       │   │   │   ├── perfusion_wm_masked.nii.gz
│       │   │   │   ├── perfusion_wm_norm.nii.gz
│       │   │   │   ├── perfusion_wm_var.nii.gz
│       │   │   │   ├── perfusion_wm_var_calib.nii.gz
│       │   │   │   ├── perfusion_wm_var_calib_masked.nii.gz
│       │   │   │   ├── perfusion_wm_var_norm.nii.gz
│       │   │   │   └── perfusion_wm_wm_mean.txt
│       │   │   ├── pvgm_inasl.nii.gz
│       │   │   ├── pvwm_inasl.nii.gz
│       │   │   ├── wm_mask.nii.gz
│       │   │   └── wm_roi.nii.gz
│       │   ├── oxford_asl_inputs
│       │   │   ├── beta_perf.nii.gz
│       │   │   ├── brain_fov_mask.nii.gz
│       │   │   ├── calib0_corr_aslt1w.nii.gz
│       │   │   ├── pve_GM.nii.gz
│       │   │   ├── pve_WM.nii.gz
│       │   │   ├── timing_img_aslt1w.nii.gz
│       │   │   └── vent_csf_mask.nii.gz
│       │   └── oxford_aslt1w.log
│       ├── PVEs
│       │   ├── pve_GM.nii.gz
│       │   ├── pve_WM.nii.gz
│       │   └── vent_csf_mask.nii.gz
│       ├── TIs 
│       │   ├── DistCorr
│       │   │   └── tis_dc_moco.nii.gz
│       │   ├── MotionSubtraction
│       │   │   ├── beta_baseline.nii.gz
│       │   │   ├── beta_perf.nii.gz # Label-control differences of fully corrected ASL timeseries for altnernative modelling 
│       │   │   ├── combined_mask.nii.gz
│       │   │   └── difference_mask.nii.gz
│       │   ├── asl_corr.nii.gz # Fully corrected ASL timeseries for alternative modelling 
│       │   ├── asl_noncorr.nii.gz # Uncorrected ASL timeseries, for QC comparison 
│       │   ├── combined_scaling_factors.nii.gz
│       │   ├── reg
│       │   │   ├── ASL_grid_T1w_brain_mask.nii.gz
│       │   │   ├── asl2orig_mgz_initial_bbr.dat
│       │   │   ├── asl2struct.mat
│       │   │   ├── asl2struct_reg.log
│       │   │   ├── brain_fov_mask.nii.gz
│       │   │   ├── fmapmag_aslt1w.nii.gz
│       │   │   ├── fov_mask.nii.gz
│       │   │   └── mean_T1t_filt_aslt1w.nii.gz
│       │   ├── single_step_resample_to_aslt1w.log
│       │   └── timing_img_aslt1w.nii.gz
│       ├── aCBV_calib.nii.gz # T1w NIFTI, arterial cerebral blood volume, non-PVEc
│       ├── arrival.nii.gz # T1w NIFTI, ATT, non-PVEc
│       ├── arrival_gm_mean.txt # ROI calculation 
│       ├── arrival_var.nii.gz
│       ├── arrival_wm_mean.txt # ROI calculation 
│       ├── perfusion_calib.nii.gz # T1w NIFTI, perfusion, non-PVEc
│       ├── perfusion_calib_gm_mean.txt # ROI calculation 
│       ├── perfusion_calib_wm_mean.txt # ROI calculation 
│       ├── perfusion_var_calib.nii.gz
│       ├── pvcorr_aCBV_calib.nii.gz # T1w NIFTI, arterial cerebral blood volume, PVEc
│       ├── pvcorr_arrival_gm_masked.nii.gz # T1w NIFTI, ATT, PVEc GM
│       ├── pvcorr_arrival_gm_mean.txt # ROI calculation 
│       ├── pvcorr_arrival_gm_var_masked.nii.gz
│       ├── pvcorr_arrival_wm_masked.nii.gz # T1w NIFTI, ATT, PVEc WM
│       ├── pvcorr_arrival_wm_mean.txt # ROI calculation 
│       ├── pvcorr_arrival_wm_var_masked.nii.gz 
│       ├── pvcorr_perfusion_calib_gm_mean.txt # ROI calculation 
│       ├── pvcorr_perfusion_calib_wm_mean.txt # ROI calculation 
│       ├── pvcorr_perfusion_gm_calib_masked.nii.gz # T1w NIFTI, perfusion, PVEc GM
│       ├── pvcorr_perfusion_gm_var_calib_masked.nii.gz
│       ├── pvcorr_perfusion_wm_calib_masked.nii.gz # T1w NIFTI, perfusion, PVEc WM
│       ├── pvcorr_perfusion_wm_var_calib_masked.nii.gz
│       ├── reg
│       │   ├── ASL_grid_T1w_acpc_dc_restore.nii.gz
│       │   └── wmmask.nii.gz
│       └── roi_stats
│           ├── fsl_identity.txt
│           ├── roi_stats.csv
│           ├── roi_stats.log
│           ├── roi_stats_gm.csv
│           └── roi_stats_wm.csv
└── project.log
```