import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const info = await (await api.fetchApi("/object_info/LoraLoader")).json();
const names = ["None", ...info.LoraLoader.input.required.lora_name[0]];

const WIDGET = "h-6 rounded-md border-none bg-component-node-background text-xs text-component-node-foreground";
const BUTTON = "h-6 rounded-md border-none bg-component-node-widget-background text-xs";
const HOVER = "hover:bg-component-node-widget-background-hovered";
const CARD_HEIGHT = 60;
const CARD_GAP = 8;
const TOOLBAR_HEIGHT = 24;

const element = (tag, className, text) => {
    const el = document.createElement(tag);
    el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
};

const icon = (name, className) => element("i", `icon-[lucide--${name}] ${className}`);

const search = (event, items, onPick) => {
    const panel = element("div", "fixed z-3000 w-80 overflow-hidden rounded-lg border border-solid border-border-default bg-base-background p-0 text-base-foreground shadow-md");
    panel.style.left = `${Math.min(event.clientX, window.innerWidth - 330)}px`;
    panel.style.top = `${Math.min(event.clientY, window.innerHeight - 320)}px`;
    const box = element("div", "m-1 flex items-center gap-2 rounded-md border border-solid border-border-default px-2 py-1.5 transition-colors focus-within:border-primary-background");
    const input = element("input", "w-full border-none bg-transparent text-xs outline-none");
    input.placeholder = "Search";
    box.append(icon("search", "shrink-0 text-sm text-muted-foreground"), input);
    const list = element("div", "max-h-56 min-w-full overflow-y-auto p-1 text-xs");
    panel.append(box, list);

    let shown = [];
    let active = 0;
    const close = () => {
        document.removeEventListener("pointerdown", outside, true);
        panel.remove();
    };
    const outside = (e) => {
        if (!panel.contains(e.target)) close();
    };
    const pick = (name) => {
        close();
        onPick(name);
    };
    const render = () => {
        const query = input.value.trim().toLowerCase();
        shown = items.filter((name) => name.toLowerCase().includes(query));
        active = Math.min(active, Math.max(shown.length - 1, 0));
        list.replaceChildren(...shown.map((name, index) => {
            const row = element("div", `flex h-8 w-full cursor-pointer items-center justify-between gap-3 rounded-sm p-2 outline-none select-none hover:bg-secondary-background${index === active ? " bg-secondary-background" : ""}`);
            row.append(element("span", "truncate", name));
            row.title = name;
            row.onclick = () => pick(name);
            return row;
        }));
        if (!shown.length) list.append(element("div", "p-2 text-xs text-muted-foreground", "No results found"));
        list.children[active]?.scrollIntoView({ block: "nearest" });
    };
    input.oninput = () => {
        active = 0;
        render();
    };
    input.onkeydown = (e) => {
        if (e.key === "Escape") {
            close();
        } else if (e.key === "Enter" && shown.length) {
            pick(shown[active]);
        } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            active = Math.max(0, Math.min(shown.length - 1, active + (e.key === "ArrowDown" ? 1 : -1)));
            render();
            e.preventDefault();
        }
    };
    document.body.append(panel);
    document.addEventListener("pointerdown", outside, true);
    render();
    input.focus();
};

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
        let rows = [];

        const save = () => {
            node.properties.loras = rows.map((row) => ({ ...row }));
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

        const showDelete = () => {
            const linked = node.inputs.find((input) => input.name === "preset").link != null;
            presetsData.value = linked ? JSON.stringify(presets()) : "{}";
            panel.style.display = linked ? "none" : "";
            panelWidget.hidden = linked;
            deleteButton.style.display = presetWidget.value === "None" ? "none" : "";
            resize();
        };

        const load = (name) => {
            rows = (presets()[name] ?? []).map((entry) => ({ enabled: true, ...entry }));
            render();
            save();
            showDelete();
        };


        presetWidget.callback = load;

        const toolbarButton = (iconName, label, onClick) => {
            const button = element("button", `flex shrink-0 cursor-pointer items-center justify-center gap-1 px-2 text-base-foreground ${BUTTON} ${HOVER}`);
            button.append(icon(iconName, "size-4"), element("span", "truncate", label));
            button.onclick = onClick;
            return button;
        };

        const saveButton = toolbarButton("save", "Save preset", () => {
            const name = window.prompt("Preset name", presetWidget.value === "None" ? "" : presetWidget.value);
            if (!name) return;
            presets()[name] = rows.map((row) => ({ ...row }));
            refreshPresets();
            presetWidget.value = name;
            showDelete();
        });

        const deleteButton = toolbarButton("trash-2", "Delete preset", () => {
            delete presets()[presetWidget.value];
            refreshPresets();
            presetWidget.value = "None";
            showDelete();
        });

        const removeAllButton = toolbarButton("list-x", "Clear", () => {
            presetWidget.value = "None";
            load("None");
        });

        const addButton = toolbarButton("plus", "Add LoRA", () => {
            rows.push({ enabled: true, name: "None", strength: 1, trigger_words: "" });
            render();
            save();
        });

        const toolbar = element("div", "flex gap-1");
        saveButton.classList.add("flex-1");
        deleteButton.classList.add("flex-1");
        toolbar.append(saveButton, deleteButton);

        const actions = element("div", "flex gap-1");
        addButton.classList.add("flex-1");
        removeAllButton.classList.add("flex-1");
        actions.append(removeAllButton, addButton);

        const card = (row) => {
            const el = element("div", "flex flex-col gap-1 rounded-lg bg-component-node-widget-background p-1");

            const select = element("div", `flex min-w-0 flex-1 items-center overflow-hidden ${WIDGET} ${HOVER}`);
            const trigger = element("button", "flex min-w-0 flex-1 cursor-pointer items-center overflow-hidden border-none bg-transparent p-0 outline-none");
            trigger.title = row.name;
            trigger.append(element("span", `min-w-[4ch] flex-1 truncate pr-1 pl-2 text-left text-xs ${row.name === "None" ? "text-muted-foreground" : ""}`, row.name === "None" ? "Select LoRA" : row.name));
            trigger.onclick = (event) => search(event, names, (picked) => {
                row.name = picked;
                render();
                save();
            });
            const chevron = element("button", "flex h-full w-6 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent outline-none");
            chevron.append(icon("chevron-down", "size-4 bg-muted-foreground"));
            chevron.onclick = trigger.onclick;
            select.append(trigger, chevron);

            const remove = element("button", `flex aspect-square shrink-0 cursor-pointer items-center justify-center p-0 ${WIDGET} ${HOVER}`);
            remove.append(icon("x", "size-4 bg-muted-foreground"));
            remove.title = "Remove";
            remove.onclick = () => {
                rows.splice(rows.indexOf(row), 1);
                render();
                save();
            };

            const top = element("div", "flex gap-1");
            const state = row.enabled ? "checked" : "unchecked";
            const toggle = element("button", "group inline-flex h-6 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full border-0 bg-transparent p-0 outline-none focus-visible:ring-1 focus-visible:ring-border-default");
            toggle.setAttribute("role", "switch");
            toggle.setAttribute("aria-checked", row.enabled);
            toggle.dataset.state = state;
            const track = element("span", "pointer-events-none inline-flex h-5 w-9 items-center rounded-full border border-transparent bg-border-default px-0.5 transition-colors group-data-[state=checked]:bg-primary-background");
            const thumb = element("span", "pointer-events-none block size-4 rounded-full bg-base-background shadow-sm transition-transform data-[state=checked]:translate-x-3.5 data-[state=unchecked]:translate-x-0");
            thumb.dataset.state = state;
            track.append(thumb);
            toggle.append(track);
            toggle.onclick = () => {
                row.enabled = !row.enabled;
                render();
                save();
            };

            top.append(toggle, select, remove);

            const input = element("input", "min-w-[4ch] flex-1 truncate border-0 bg-transparent p-1 text-center text-xs focus:outline-0");
            input.value = row.strength.toFixed(2);
            input.onchange = () => {
                row.strength = Number(input.value) || 0;
                render();
                save();
            };
            const step = (name, delta) => {
                const button = element("button", "flex aspect-square h-full cursor-pointer items-center justify-center rounded-none border-none bg-transparent p-0 hover:bg-component-node-widget-background-hovered");
                button.append(icon(name, "size-4 bg-muted-foreground"));
                button.onclick = () => {
                    row.strength = Math.round((row.strength + delta) * 100) / 100;
                    render();
                    save();
                };
                return button;
            };
            const stepper = element("div", `flex w-28 shrink-0 overflow-hidden ${WIDGET}`);
            stepper.append(step("minus", -0.05), input, step("plus", 0.05));

            const words = element("input", `flex w-full min-w-0 appearance-none px-4 placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-border-default focus-visible:outline-none ${WIDGET} ${HOVER}`);
            words.placeholder = "Trigger words";
            words.value = row.trigger_words ?? "";
            words.oninput = () => {
                row.trigger_words = words.value;
                save();
            };

            const bottom = element("div", "flex gap-1");
            bottom.append(stepper, words);

            if (!row.enabled) {
                select.classList.add("opacity-50");
                stepper.classList.add("opacity-50");
                words.classList.add("opacity-50");
            }

            el.append(top, bottom);
            return el;
        };

        const list = element("div", "flex w-full flex-col gap-2");
        const panel = element("div", "flex w-full flex-col gap-2");
        panel.append(toolbar, list, actions);

        const panelWidget = node.addDOMWidget("lora_list", "lora_list", panel, {
            serialize: false,
            getMinHeight: () => (panelWidget.hidden ? 0 : TOOLBAR_HEIGHT * 2 + CARD_GAP + rows.length * (CARD_HEIGHT + CARD_GAP)),
        });
        panelWidget.serialize = false;

        const render = () => {
            list.replaceChildren(...rows.map(card));
            list.style.display = rows.length ? "" : "none";
            resize();
        };

        const connectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function () {
            connectionsChange?.apply(this, arguments);
            showDelete();
        };

        const configure = node.onConfigure;
        node.onConfigure = function () {
            configure?.apply(this, arguments);
            rows = (this.properties.loras ?? []).map((entry) => ({ enabled: true, ...entry }));
            render();
            refreshPresets();
            if (!(presetWidget.value in presets())) {
                presetWidget.value = "None";
            }
            save();
            showDelete();
        };
    },
});
