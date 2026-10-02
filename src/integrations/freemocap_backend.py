"""Version-specific adapter exposing the single-camera depth option explicitly."""


def process_recording(recording_path, run_blender=False, make_jupyter_notebook=False,
                      use_tqdm=False, flatten_single_camera_data=False):
    from freemocap.core_processes.process_motion_capture_videos.process_recording_headless import process_recording_headless
    from freemocap.data_layer.recording_models.post_processing_parameter_models import ProcessingParameterModel

    parameters = ProcessingParameterModel()
    parameters.anipose_triangulate_3d_parameters_model.flatten_single_camera_data = flatten_single_camera_data
    return process_recording_headless(
        recording_path=recording_path, recording_processing_parameter_model=parameters,
        run_blender=run_blender, make_jupyter_notebook=make_jupyter_notebook, use_tqdm=use_tqdm,
    )
