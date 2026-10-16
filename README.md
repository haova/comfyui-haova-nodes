# comfyui-haova-nodes

Custom nodes for ComfyUI that save images with A1111/Civitai-style metadata.

## Install

With ComfyUI-Manager: choose *Install via Git URL*, paste `https://github.com/haova/comfyui-haova-nodes` and restart ComfyUI.

Or clone into `ComfyUI/custom_nodes` and restart ComfyUI:

```bash
git clone https://github.com/haova/comfyui-haova-nodes
```

## Nodes

### Save Image with Metadata (`HaoVA | Image`)

Saves PNGs with metadata that can be uploaded to Civitai.

`model_path` can be filled automatically by connecting the output of **Get Path**.

### Get Path (`HaoVA | Model`)

Takes a `MODEL` and returns the paths of every checkpoint and LoRA in its loader chain, one per line, with LoRA strengths appended. Connect it to `model_path`.

It reads the checkpoint, diffusion model and LoRA loaders upstream through `ckpt_name`, `unet_name` and `lora_name`. Loaders with other input names are not detected. Bypassed nodes and inputs fed by links are skipped.

### Model Names (`HaoVA | Model`)

Lists the file names in a model folder.

### Model Info (`HaoVA | Model`)

Outputs the Civitai info of the models in `model_path` as a markdown table. Models that are not cached yet are looked up first.

### Sampler Select / Scheduler Select (`HaoVA | Sampling`)

Pick a sampler or scheduler once and connect it to every `sampler_name` / `scheduler` input, such as the ones on **Save Image with Metadata** and KSampler.
