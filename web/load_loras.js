import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const info = await (await api.fetchApi("/object_info/LoraLoader")).json();
const names = ["None", ...info.LoraLoader.input.required.lora_name[0]];

app.registerExtension({
    name: "haova.LoadLoras",
    nodeCreated(node) {
        if (node.comfyClass !== "Load LoRAs") {
            return;
        }
        const data = node.widgets.find((widget) => widget.name === "loras");
        data.hidden = true;
        data.computeSize = () => [0, -4];
        const presetsData = node.widgets.find((widget) => widget.name === "presets");
        presetsData.hidden = true;
        presetsData.computeSize = () => [0, -4];
        const presetWidget = node.widgets.find((widget) => widget.name === "preset");
        const slots = [];

        const entries = () => slots.map((slot) => ({ name: slot.name.value, strength: slot.strength.value, trigger_words: slot.trigger.value }));

        const save = () => {
            node.properties.loras = entries();
            data.value = JSON.stringify(node.properties.loras);
        };

        const resize = () => {
            node.setSize([node.size[0], node.computeSize()[1]]);
            node.setDirtyCanvas(true, true);
        };

        const presets = () => (node.properties.presets ??= {});

        const refreshPresets = () => {
            presetWidget.options.values = ["None", ...Object.keys(presets())];
        };

        const setHidden = (widget, hidden) => {
            widget.hidden = hidden;
            if (hidden) {
                widget.computeSize = () => [0, -4];
            } else {
                delete widget.computeSize;
            }
        };

        const showDelete = () => {
            const linked = node.inputs.find((input) => input.name === "preset").link != null;
            presetsData.value = linked ? JSON.stringify(presets()) : "{}";
            for (const widget of [saveButton, addButton, removeAllButton, ...slots.flatMap((slot) => [slot.name, slot.strength, slot.trigger, slot.remove])]) {
                setHidden(widget, linked);
            }
            setHidden(deleteButton, linked || presetWidget.value === "None");
            resize();
        };

        const removeSlot = (slot) => {
            slots.splice(slots.indexOf(slot), 1);
            for (const widget of [slot.name, slot.strength, slot.trigger, slot.remove]) {
                node.removeWidget(widget);
            }
        };

        const load = (name) => {
            for (const slot of [...slots]) {
                removeSlot(slot);
            }
            for (const entry of presets()[name] ?? []) {
                add(entry);
            }
            save();
            showDelete();
        };

        presetWidget.callback = load;

        const saveButton = node.addWidget("button", "Save preset", null, () => {
            const name = window.prompt("Preset name", presetWidget.value === "None" ? "" : presetWidget.value);
            if (!name) return;
            presets()[name] = entries();
            refreshPresets();
            presetWidget.value = name;
            showDelete();
        });

        const deleteButton = node.addWidget("button", "Delete preset", null, () => {
            delete presets()[presetWidget.value];
            refreshPresets();
            presetWidget.value = "None";
            showDelete();
        });

        const addButton = node.addWidget("button", "+ Add LoRA", null, () => {
            add({ name: "None", strength: 1, trigger_words: "" });
            save();
            resize();
        });

        const removeAllButton = node.addWidget("button", "Remove all", null, () => {
            presetWidget.value = "None";
            load("None");
        });

        let uid = 0;

        const create = (type, label, value, callback, options) => {
            const widget = node.addWidget(type, `${label}_${++uid}`, value, callback, { ...options, serialize: false });
            widget.label = label;
            widget.serialize = false;
            node.widgets.splice(node.widgets.indexOf(widget), 1);
            node.widgets.splice(node.widgets.indexOf(addButton), 0, widget);
            return widget;
        };

        const add = (entry) => {
            const slot = {
                name: create("combo", "lora", entry.name, save, { values: names }),
                strength: create("number", "strength", entry.strength, save, { min: -100, max: 100, step: 1, precision: 2 }),
                trigger: create("text", "trigger", entry.trigger_words ?? "", save),
            };
            slot.remove = create("button", "🗑 Remove", null, () => {
                removeSlot(slot);
                save();
                resize();
            });
            slots.push(slot);
        };

        const connectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function () {
            connectionsChange?.apply(this, arguments);
            showDelete();
        };

        const configure = node.onConfigure;
        node.onConfigure = function () {
            configure?.apply(this, arguments);
            for (const entry of this.properties.loras ?? []) {
                add(entry);
            }
            refreshPresets();
            if (!(presetWidget.value in presets())) {
                presetWidget.value = "None";
            }
            save();
            showDelete();
        };
    },
});
