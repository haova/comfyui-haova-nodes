import os
import json
import logging
import numpy as np
import hashlib
import urllib.error
import urllib.request
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import comfy.samplers
import nodes as comfy_nodes
import folder_paths

def load_model_info(file_path):
    stat = os.stat(file_path)
    info_path = os.path.splitext(file_path)[0] + ".haova.json"
    info = {}
    if os.path.exists(info_path):
        with open(info_path) as f:
            info = json.load(f)
    if info.get("mtime_ns") != stat.st_mtime_ns or info.get("size") != stat.st_size:
        with open(file_path, "rb") as f:
            sha256 = hashlib.file_digest(f, "sha256").hexdigest()
        info = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "sha256": sha256}
    if "civitai" not in info:
        try:
            request = urllib.request.Request(f"https://civitai.com/api/v1/model-versions/by-hash/{info['sha256']}", headers={"User-Agent": "comfyui-haova-nodes"})
            with urllib.request.urlopen(request, timeout=15) as response:
                version = json.load(response)
            info["civitai"] = {
                "modelVersionId": version["id"],
                "modelName": version["model"]["name"],
                "modelVersionName": version["name"],
                "type": version["model"]["type"].lower(),
            }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                info["civitai"] = None
            else:
                logging.warning(f"Civitai lookup failed for {file_path}: {e}")
        except urllib.error.URLError as e:
            logging.warning(f"Civitai lookup failed for {file_path}: {e}")
    with open(info_path, "w") as f:
        json.dump(info, f)

    return info


def resolve_model_path(model_path):
    model_path = model_path.strip()
    model_directory, _, relative_path = model_path.partition("/")
    if not os.path.isfile(model_path) and model_directory in folder_paths.folder_names_and_paths:
        return folder_paths.get_full_path_or_raise(model_directory, relative_path)

    return model_path


CIVITAI_SAMPLERS = {
    "euler": "Euler",
    "euler_ancestral": "Euler a",
    "heun": "Heun",
    "dpm_2": "DPM2",
    "dpm_2_ancestral": "DPM2 a",
    "lms": "LMS",
    "dpm_fast": "DPM fast",
    "dpm_adaptive": "DPM adaptive",
    "dpmpp_2s_ancestral": "DPM++ 2S a",
    "dpmpp_sde": "DPM++ SDE",
    "dpmpp_sde_gpu": "DPM++ SDE",
    "dpmpp_2m": "DPM++ 2M",
    "dpmpp_2m_sde": "DPM++ 2M SDE",
    "dpmpp_2m_sde_gpu": "DPM++ 2M SDE",
    "dpmpp_3m_sde": "DPM++ 3M SDE",
    "dpmpp_3m_sde_gpu": "DPM++ 3M SDE",
    "ddim": "DDIM",
    "uni_pc": "UniPC",
    "uni_pc_bh2": "UniPC",
}


def parse_model_line(line):
    path, _, weight = line.strip().rpartition(":")
    if path and weight.replace(".", "", 1).lstrip("-").isdigit():
        return resolve_model_path(path), float(weight)

    return resolve_model_path(line), 1.0


def handle_whitespace(text):
    return text.strip().replace("\n", " ").replace("\r", " ").replace("\t", " ")

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
                "positive": ("STRING", {"default": "", "multiline": True}),
                "negative": ("STRING", {"default": "", "multiline": True}),
                "model_path": ("STRING", {"default": "", "multiline": True}),
                "seed_value": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1}),
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

    def save_images(
        self,
        images,
        filename_prefix="test",
        positive="",
        negative="",
        model_path="",
        seed_value=0,
        steps=20,
        sampler_name="euler",
        scheduler="normal",
        cfg=8.0,
        prompt=None,
        extra_pnginfo=None,
    ):
        output_path, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
        )
        results = []
        width = images[0].shape[1]
        height = images[0].shape[0]
        models = []
        for line in model_path.splitlines():
            if line.strip():
                path, weight = parse_model_line(line)
                models.append((os.path.splitext(os.path.basename(path))[0], load_model_info(path), weight))
        modelhash = models[0][1]["sha256"][:10] if models else "unknown"
        basemodelname = models[0][0] if models else "unknown"
        hashes = {f"LORA:{name}": info["sha256"][:12].upper() for name, info, _ in models[1:]}
        resources = [{**info["civitai"], **({"weight": weight} if index else {})} for index, (_, info, weight) in enumerate(models) if info.get("civitai")]

        comment = (
            f"{handle_whitespace(positive)}\n"
            f"Negative prompt: {handle_whitespace(negative)}\n"
            f"Steps: {steps}, Sampler: {CIVITAI_SAMPLERS.get(sampler_name, sampler_name)}{' Karras' if scheduler == 'karras' else ''}, "
            f"{f'Schedule type: {scheduler}, ' if scheduler not in ('normal', 'karras') else ''}"
            f"CFG scale: {cfg}, Seed: {seed_value}, Size: {width}x{height}, "
            f"Model hash: {modelhash}, Model: {basemodelname}, "
            f"{f'Hashes: {json.dumps(hashes, separators=(",", ":"))}, ' if hashes else ''}"
            f"{f'Civitai resources: {json.dumps(resources, separators=(",", ":"))}, ' if resources else ''}Version: ComfyUI"
        )

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
    FILE_INPUT_DIRECTORIES = {
        "ckpt_name": "checkpoints",
        "unet_name": "diffusion_models",
        "lora_name": "loras",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
            },
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("paths",)
    FUNCTION = "get_paths"
    CATEGORY = "HaoVA | Model"

    def resolve(self, prompt, value):
        if not isinstance(value, list):
            return value
        node = prompt[value[0]]
        inputs = node["inputs"]
        if node["class_type"] in ("PrimitiveString", "PrimitiveBoolean"):
            return self.resolve(prompt, inputs["value"])
        if node["class_type"] == "CustomCombo" and value[1] == 0:
            return self.resolve(prompt, inputs["choice"])
        if node["class_type"] == "StringCompare":
            a = self.resolve(prompt, inputs["string_a"])
            b = self.resolve(prompt, inputs["string_b"])
            if a is None or b is None:
                return None
            if not self.resolve(prompt, inputs["case_sensitive"]):
                a, b = a.lower(), b.lower()
            mode = self.resolve(prompt, inputs["mode"])
            return a.startswith(b) if mode == "Starts With" else a.endswith(b) if mode == "Ends With" else a == b

    def get_paths(self, model, prompt, unique_id):
        paths = []
        visited = set()

        def walk(node_id):
            if node_id in visited:
                return
            visited.add(node_id)
            inputs = prompt[node_id]["inputs"]
            if prompt[node_id]["class_type"] == "ComfySwitchNode":
                switch = self.resolve(prompt, inputs["switch"])
                model_inputs = ["on_true"] if switch is True else ["on_false"] if switch is False else ["on_true", "on_false"]
            else:
                input_types = comfy_nodes.NODE_CLASS_MAPPINGS[prompt[node_id]["class_type"]].INPUT_TYPES()
                model_inputs = [name for section in ("required", "optional") for name, spec in input_types.get(section, {}).items() if spec[0] == "MODEL"]
            for name in model_inputs:
                if isinstance(inputs.get(name), list):
                    walk(inputs[name][0])
            for name, directory in self.FILE_INPUT_DIRECTORIES.items():
                if isinstance(inputs.get(name), str):
                    weight = inputs.get("strength_model") if name == "lora_name" else None
                    paths.append(f"{directory}/{inputs[name]}" + (f":{weight}" if isinstance(weight, (int, float)) else ""))

        walk(prompt[unique_id]["inputs"]["model"][0])
        return ("\n".join(paths),)


class ModelInfo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_path": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("markdown",)
    FUNCTION = "get_info"
    CATEGORY = "HaoVA | Model"

    def get_info(self, model_path):
        rows = ["| Model | Type | Weight |", "|---|---|---|"]
        for line in model_path.splitlines():
            if line.strip():
                path, weight = parse_model_line(line)
                if weight == 0:
                    continue
                civitai = load_model_info(path).get("civitai")
                if civitai:
                    rows.append(f"| [{civitai['modelName']}](https://civitai.com/model-versions/{civitai['modelVersionId']}) | {civitai['type']} | {weight if civitai['type'] == 'lora' else ''} |")
                else:
                    rows.append(f"| {os.path.basename(path)} | not found | |")

        return ("\n".join(rows),)


class SamplerSelect:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
            },
        }

    RETURN_TYPES = (comfy.samplers.KSampler.SAMPLERS,)
    RETURN_NAMES = ("sampler_name",)
    FUNCTION = "select"
    CATEGORY = "HaoVA | Sampling"

    def select(self, sampler_name):
        return (sampler_name,)


class SchedulerSelect:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
            },
        }

    RETURN_TYPES = (comfy.samplers.KSampler.SCHEDULERS,)
    RETURN_NAMES = ("scheduler",)
    FUNCTION = "select"
    CATEGORY = "HaoVA | Sampling"

    def select(self, scheduler):
        return (scheduler,)


NODE_CLASS_MAPPINGS = {
    "Save Image with Metadata": ImageSaveWithMetadata,
    "Model Names": ModelNames,
    "Get Path": GetPath,
    "Model Info": ModelInfo,
    "Sampler Select": SamplerSelect,
    "Scheduler Select": SchedulerSelect,
}
