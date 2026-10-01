import os
import json
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import folder_paths

class ImageSaveWithMetadata:
    def __init__(self):
        self.output_dir = folder_paths.output_directory

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", ),
                "filename_prefix": ("STRING", {"default": "test"}),
            },
            "optional": {
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "HaoVA | Image"

    def save_images(self, images, filename_prefix="test", prompt=None, extra_pnginfo=None):
        output_path, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
        )
        results = []
        comment = f"Version: ComfyUI"

        for batch_number, image in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            metadata = PngInfo()
            metadata.add_text("parameters", comment)
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for key, value in extra_pnginfo.items():
                    metadata.add_text(key, json.dumps(value))

            filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))
            file = f"{filename_with_batch_num}_{counter:05}_.png"
            img.save(os.path.join(output_path, file), pnginfo=metadata, compress_level=4)
            results.append({
                "filename": file,
                "subfolder": subfolder,
                "type": "output",
            })
            counter += 1

        return {
            "ui": {
                "images": results
            }
        }


class ModelNames:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_directory": (sorted(folder_paths.folder_names_and_paths),),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("model_names",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "get_model_names"
    CATEGORY = "HaoVA | Model"

    def get_model_names(self, model_directory):
        return (folder_paths.get_filename_list(model_directory),)


class GetPath:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("path",)
    FUNCTION = "get_path"
    CATEGORY = "HaoVA | Model"

    def get_path(self, model):
        source_path = model.cached_patcher_init[1][0]
        for model_directory, (paths, _) in folder_paths.folder_names_and_paths.items():
            for path in paths:
                if folder_paths.is_within_directory(path, source_path):
                    return (os.path.join(model_directory, os.path.relpath(source_path, path)),)

        return ("",)


NODE_CLASS_MAPPINGS = {
    "Save Image with Metadata": ImageSaveWithMetadata,
    "Model Names": ModelNames,
    "Get Path": GetPath,
}
