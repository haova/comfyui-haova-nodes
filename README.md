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

It reads the checkpoint, diffusion model, LoRA and **Load LoRAs** loaders upstream through `ckpt_name`, `unet_name` and `lora_name`. Loaders with other input names are not detected. Bypassed nodes, inputs fed by links and LoRAs with strength 0 are skipped.

### Load LoRAs (`HaoVA | Model`)

Applies any number of LoRAs in order to a `MODEL` and/or `CLIP`; either input can be left unconnected. Use **+ Add LoRA** at the bottom to add a row with a searchable LoRA list and a strength used for both model and CLIP, and **Remove** under a row to delete it. Each LoRA has its own `trigger words`, and the `trigger_words` output joins them with commas so it can be connected to a prompt. The `preset_name` output is the name of the selected preset, or empty if none is selected. When the `preset` select is promoted out of a subgraph (or linked), the editing widgets are hidden and the LoRAs are taken directly from the selected preset. Entries left on `None` are skipped.

**Save preset** stores the current list under a name inside the node, so it is saved with the workflow, and the `preset` select loads a saved list into the node. Choosing `None` or pressing **Remove all** removes every LoRA from the node. **Delete preset** removes the selected preset. Saving with an existing name overwrites it.

### Model Names (`HaoVA | Model`)

Lists the file names in a model folder.

### Model Info (`HaoVA | Model`)

Outputs the Civitai info of the models in `model_path` as a markdown table. Models that are not cached yet are looked up first.

### Sampler Select / Scheduler Select (`HaoVA | Sampling`)

Pick a sampler or scheduler once and connect it to every `sampler_name` / `scheduler` input, such as the ones on **Save Image with Metadata** and KSampler.

### Load Image Metadata (`HaoVA | Image`)

Reads the `parameters` metadata of an image and outputs the positive and negative prompt, steps, sampler, scheduler, CFG and seed. Works with images saved by **Save Image with Metadata** and other A1111-style PNGs.

### Image Info (`HaoVA | Image`)

Reads the `parameters` metadata of an image and outputs it as markdown: prompt, negative prompt, a settings table, the hashes, and the Civitai resources as links. Works with images saved by **Save Image with Metadata** and other A1111-style PNGs.

### Captioned Images (`HaoVA | Image`)

Joins every connected image side by side into one image (each is scaled to the height of the first) and writes a white caption on a black background centered below each one. A new `image` input appears whenever the last one is connected. Type the captions in `captions`, one line per image in order. `font_size` sets the caption size and `gap` the black space between images and around the border. Only the first image of each batch is used.
