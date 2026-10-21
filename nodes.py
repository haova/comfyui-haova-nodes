import os
import re
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


COMFY_SAMPLERS = {}
for comfy_name, civitai_name in CIVITAI_SAMPLERS.items():
    COMFY_SAMPLERS.setdefault(civitai_name, comfy_name)


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
                "positive": ("STRING", {"forceInput": True}),
                "negative": ("STRING", {"forceInput": True}),
                "model_path": ("STRING", {"forceInput": True}),
                "seed_value": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "forceInput": True}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000, "forceInput": True}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"forceInput": True}),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"forceInput": True}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "forceInput": True}),
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
        positive=None,
        negative=None,
        model_path=None,
        seed_value=None,
        steps=None,
        sampler_name=None,
        scheduler=None,
        cfg=None,
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
        for line in (model_path or "").splitlines():
            if line.strip():
                path, weight = parse_model_line(line)
                models.append((os.path.splitext(os.path.basename(path))[0], load_model_info(path), weight))
        hashes = {f"LORA:{name}": info["sha256"][:12].upper() for name, info, _ in models[1:]}
        resources = [{**info["civitai"], **({"weight": weight} if index else {})} for index, (_, info, weight) in enumerate(models) if info.get("civitai")]

        settings = []
        if steps is not None:
            settings.append(f"Steps: {steps}")
        if sampler_name:
            settings.append(f"Sampler: {CIVITAI_SAMPLERS.get(sampler_name, sampler_name)}{' Karras' if scheduler == 'karras' else ''}")
        if scheduler and scheduler not in ("normal", "karras"):
            settings.append(f"Schedule type: {scheduler}")
        if cfg is not None:
            settings.append(f"CFG scale: {cfg}")
        if seed_value is not None:
            settings.append(f"Seed: {seed_value}")
        settings.append(f"Size: {width}x{height}")
        if models:
            settings.append(f"Model hash: {models[0][1]['sha256'][:10]}")
            settings.append(f"Model: {models[0][0]}")
        if hashes:
            settings.append(f"Hashes: {json.dumps(hashes, separators=(',', ':'))}")
        if resources:
            settings.append(f"Civitai resources: {json.dumps(resources, separators=(',', ':'))}")
        settings.append("Version: ComfyUI")

        lines = []
        if positive:
            lines.append(handle_whitespace(positive))
        if negative:
            lines.append(f"Negative prompt: {handle_whitespace(negative)}")
        lines.append(", ".join(settings))
        comment = "\n".join(lines)

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
                    if weight == 0:
                        continue
                    paths.append(f"{directory}/{inputs[name]}" + (f":{weight}" if isinstance(weight, (int, float)) else ""))
            if prompt[node_id]["class_type"] == "Load LoRAs":
                paths.extend(f"loras/{lora['name']}:{lora['strength']}" for lora in selected_loras(inputs["loras"], inputs["preset"], inputs["presets"]) if lora["name"] != "None" and lora["strength"] != 0)

        walk(prompt[unique_id]["inputs"]["model"][0])
        return ("\n".join(paths),)


def escape_markdown(text):
    return re.sub(r"([\\|\[\]])", r"\\\1", text)


class ModelInfo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_path": ("STRING", {"forceInput": True}),
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
                    rows.append(f"| [{escape_markdown(civitai['modelName'])}](https://civitai.com/model-versions/{civitai['modelVersionId']}) | {escape_markdown(civitai['type'])} | {weight if civitai['type'] == 'lora' else ''} |")
                else:
                    rows.append(f"| {escape_markdown(os.path.basename(path))} | not found | |")

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


SETTING_KEY = re.compile(r"\s*([\w ]+):\s*")
SETTING_VALUE = re.compile(r'"(?:\\.|[^\\"])*"|[^,]*')


def list_input_images():
    input_dir = folder_paths.get_input_directory()
    files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]

    return sorted(folder_paths.filter_files_content_types(files, ["image"]))


def parse_settings(line):
    settings = {}
    position = 0
    while match := SETTING_KEY.match(line, position):
        position = match.end()
        if line.startswith(("[", "{"), position):
            value, position = json.JSONDecoder().raw_decode(line, position)
        else:
            value_match = SETTING_VALUE.match(line, position)
            value, position = value_match.group(), value_match.end()
        settings[match.group(1)] = value
        if line.startswith(",", position):
            position += 1

    return settings


def parse_parameters(parameters):
    lines = parameters.split("\n")
    settings_index = max(i for i, line in enumerate(lines) if line.startswith("Steps: "))
    text = "\n".join(lines[:settings_index])
    positive, _, negative = text.partition("\nNegative prompt: ")
    if positive.startswith("Negative prompt: "):
        positive, negative = "", positive[len("Negative prompt: "):]

    return positive, negative, parse_settings(lines[settings_index])


def read_parameters(path):
    with Image.open(path) as img:
        parameters = img.info.get("parameters")
    if parameters is None:
        raise ValueError(f"{path} has no 'parameters' metadata")

    return parse_parameters(parameters)


class LoadImageMetadata:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": (list_input_images(), {"image_upload": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS, "FLOAT", "INT")
    RETURN_NAMES = ("positive", "negative", "steps", "sampler_name", "scheduler", "cfg", "seed")
    FUNCTION = "load_metadata"
    CATEGORY = "HaoVA | Image"

    @classmethod
    def IS_CHANGED(cls, image):
        return os.path.getmtime(folder_paths.get_annotated_filepath(image))

    def load_metadata(self, image):
        positive, negative, settings = read_parameters(folder_paths.get_annotated_filepath(image))
        sampler_name = settings.get("Sampler", "Euler")
        scheduler = settings.get("Schedule type", "normal").lower()
        if sampler_name.endswith(" Karras"):
            sampler_name, scheduler = sampler_name[:-len(" Karras")], "karras"
        sampler_name = COMFY_SAMPLERS.get(sampler_name, sampler_name)

        return (positive, negative, int(settings.get("Steps", 20)), sampler_name, scheduler, float(settings.get("CFG scale", 8.0)), int(settings.get("Seed", 0)))


class ImageInfo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": (list_input_images(), {"image_upload": True}),
            },
            "optional": {
                "path": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("markdown",)
    FUNCTION = "get_info"
    CATEGORY = "HaoVA | Image"

    @classmethod
    def IS_CHANGED(cls, image, path=None):
        return os.path.getmtime(path or folder_paths.get_annotated_filepath(image))

    def get_info(self, image, path=None):
        positive, negative, settings = read_parameters(path or folder_paths.get_annotated_filepath(image))
        resources = settings.pop("Civitai resources", [])
        hashes = settings.pop("Hashes", {})
        rows = ["| Setting | Value |", "|---|---|"]
        for key, value in settings.items():
            rows.append(f"| {key} | {value.replace('|', '&#124;')} |")
        rows += [f"| {name} hash | {digest} |" for name, digest in hashes.items()]
        parts = ["### Prompt", f"```\n{positive}\n```", "### Negative prompt", f"```\n{negative}\n```", "### Settings", "\n".join(rows)]
        if resources:
            rows = ["| Model | Type | Weight |", "|---|---|---|"]
            rows += [f"| [{resource['modelName']}](https://civitai.com/model-versions/{resource['modelVersionId']}) | {resource['type']} | {resource.get('weight', '')} |" for resource in resources]
            parts += ["### Resources", "\n".join(rows)]

        return ("\n\n".join(parts),)


def selected_loras(loras, preset, presets):
    presets = json.loads(presets)
    return presets[preset] if preset in presets else json.loads(loras)


class LoadLoras:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"loras": ("STRING", {"default": "[]"}), "preset": (["None"],), "presets": ("STRING", {"default": "{}"})}, "optional": {"model": ("MODEL",), "clip": ("CLIP",)}}

    @classmethod
    def VALIDATE_INPUTS(cls, preset):
        return True

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING")
    RETURN_NAMES = ("model", "clip", "trigger_words", "preset_name")
    FUNCTION = "load_loras"
    CATEGORY = "HaoVA | Model"

    def load_loras(self, loras, preset, presets, model=None, clip=None):
        loader = comfy_nodes.LoraLoader()
        trigger_words = []
        for lora in selected_loras(loras, preset, presets):
            if lora["name"] != "None":
                model, clip = loader.load_lora(model, clip, lora["name"], lora["strength"], lora["strength"])
                if lora["trigger_words"].strip():
                    trigger_words.append(lora["trigger_words"].strip())

        return (model, clip, ", ".join(trigger_words), "" if preset == "None" else preset)


NODE_CLASS_MAPPINGS = {
    "Save Image with Metadata": ImageSaveWithMetadata,
    "Model Names": ModelNames,
    "Get Path": GetPath,
    "Model Info": ModelInfo,
    "Load LoRAs": LoadLoras,
    "Load Image Metadata": LoadImageMetadata,
    "Image Info": ImageInfo,
    "Sampler Select": SamplerSelect,
    "Scheduler Select": SchedulerSelect,
}
