const container = document.getElementById("gui-fields-container");

if (container) {
  const guiSchemas = JSON.parse(container.dataset.guiSchemas || "{}");
  const existingGuiFields = JSON.parse(container.dataset.guiFields || "{}");
  const subtypePk = container.dataset.subtypePk || null;
  const dropdown = document.getElementById("gui-field-dropdown");

  function getSchema() {
    return subtypePk ? guiSchemas[String(subtypePk)] || {} : {};
  }

  function getAddedKeys() {
    return new Set(
      Array.from(container.querySelectorAll("[data-gui-key]")).map(
        (el) => el.dataset.guiKey
      )
    );
  }

  function updateDropdown() {
    if (!dropdown) return;
    const schema = getSchema();
    const added = getAddedKeys();
    dropdown.innerHTML = '<option value="">— Select field —</option>';
    for (const [key, def] of Object.entries(schema)) {
      if (!added.has(key)) {
        const opt = document.createElement("option");
        opt.value = key;
        opt.textContent = def.label || key;
        dropdown.appendChild(opt);
      }
    }
  }

  function addField(key, value) {
    const schema = getSchema();
    const def = schema[key];
    if (!def) return;

    const row = document.createElement("div");
    row.className = "form-group";
    row.dataset.guiKey = key;

    const label = document.createElement("label");
    label.textContent = def.label || key;
    label.setAttribute("for", `gui-${key}`);

    const input = document.createElement("input");
    input.type = def.type || "text";
    input.name = `gui-${key}`;
    input.id = `gui-${key}`;
    if (value !== undefined && value !== null) input.value = value;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "gui-icon-btn gui-remove-btn";
    removeBtn.textContent = "\u2715";
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", () => {
      row.remove();
      updateDropdown();
    });

    const controls = document.createElement("div");
    controls.className = "form-group-controls";
    controls.appendChild(input);
    controls.appendChild(removeBtn);

    row.appendChild(label);
    row.appendChild(controls);
    container.appendChild(row);
    updateDropdown();
  }

  const addBtn = document.getElementById("gui-add-btn");

  if (addBtn) {
    addBtn.addEventListener("click", () => {
      if (dropdown.value) {
        addField(dropdown.value);
        dropdown.value = "";
      }
    });
  }

  // Hide selector if subtype has no gui_schema fields.
  const selectorRow = dropdown ? dropdown.closest(".form-group") : null;
  if (selectorRow && Object.keys(getSchema()).length === 0) {
    selectorRow.hidden = true;
  }

  // Populate existing gui fields on page load.
  if (typeof existingGuiFields === "object" && existingGuiFields !== null) {
    for (const [key, value] of Object.entries(existingGuiFields)) {
      addField(key, value);
    }
  }
  updateDropdown();
}
