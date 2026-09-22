// ---------------------------------------------------------------------------
// Reorder mesocycles and microcycles within a macrocycle.
//
// The page is rendered here from the JSON data block emitted by
// MacrocycleReorderView. Dates are recomputed on every change using the same
// bottom-up walk Macrocycle.hydrate() performs server-side, so the user can see
// exactly which weeks a move shifts — and which of those they have already
// trained — before committing to it.
//
// Saving POSTs the complete resulting order (not a "move X to Y" instruction),
// which the server validates by set equality and applies atomically.
// ---------------------------------------------------------------------------

const app = document.getElementById("reorder-app");
const planEl = document.getElementById("reorder-plan");
const bannerEl = document.getElementById("shift-banner");
const errorEl = document.getElementById("form-error");
const metaEl = document.getElementById("plan-meta");
const statusEl = document.getElementById("reorder-status");
const saveBtn = document.getElementById("reorder-save");

let PLAN_START = null;
let TODAY = null;
let INITIAL = [];
let ORIGINAL = null;

let plan = [];
let selected = null; // microcycle pk currently picked up
let focusPk = null; // row to refocus after a re-render

// -- Helpers ----------------------------------------------------------------

const addDays = (d, n) => {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
};

const fmt = d =>
  d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

const fmtKm = v => (v === null || v === undefined ? "" : String(Math.round(v * 10) / 10));

function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.class) node.className = opts.class;
  if (opts.text !== undefined) node.textContent = opts.text;
  if (opts.attrs) {
    for (const [name, value] of Object.entries(opts.attrs)) {
      node.setAttribute(name, value);
    }
  }
  for (const child of children) node.append(child);
  return node;
}

// Mirrors Macrocycle.hydrate(): walk mesocycles in order, microcycles in order;
// each start is the running cursor, which advances by duration_days.
function computeDates(source) {
  const micro = new Map();
  const meso = new Map();
  let cursor = new Date(PLAN_START);
  for (const m of source) {
    const mStart = new Date(cursor);
    let days = 0;
    for (const c of m.micros) {
      const start = new Date(cursor);
      micro.set(c.pk, { start, end: addDays(start, c.days - 1) });
      cursor = addDays(cursor, c.days);
      days += c.days;
    }
    meso.set(m.pk, {
      start: mStart,
      end: days ? addDays(mStart, days - 1) : mStart,
      days,
    });
  }
  return { micro, meso, end: addDays(cursor, -1) };
}

function diffDates(now) {
  const info = new Map();
  let shifted = 0;
  let touchingPast = 0;
  for (const meso of plan) {
    for (const micro of meso.micros) {
      const d = now.micro.get(micro.pk);
      const o = ORIGINAL.micro.get(micro.pk);
      const moved = d.start.getTime() !== o.start.getTime();
      // "Touches the past" if the window was already trained, or now lands on
      // dates that were — either way its Actual columns re-bucket.
      const past = o.end < TODAY || d.end < TODAY;
      if (moved) {
        shifted += 1;
        if (past) touchingPast += 1;
      }
      info.set(micro.pk, {
        moved,
        delta: Math.round((d.start - o.start) / 86400000),
        isNow: d.start <= TODAY && TODAY <= d.end,
        start: d.start,
        origStart: o.start,
      });
    }
  }
  return { info, shifted, touchingPast };
}

const payload = (source = plan) => ({
  mesocycles: source.map(m => ({ pk: m.pk, micros: m.micros.map(c => c.pk) })),
});

const isChanged = () =>
  JSON.stringify(payload()) !== JSON.stringify(payload(INITIAL));

// -- Mutations --------------------------------------------------------------

function locate(pk) {
  for (let mi = 0; mi < plan.length; mi += 1) {
    const ci = plan[mi].micros.findIndex(c => c.pk === pk);
    if (ci !== -1) return { mi, ci };
  }
  return null;
}

function place(mesoPk, index) {
  const { mi, ci } = locate(selected);
  const targetMi = plan.findIndex(m => m.pk === mesoPk);
  const [micro] = plan[mi].micros.splice(ci, 1);
  // Removing shifts every later slot down by one.
  if (targetMi === mi && ci < index) index -= 1;
  plan[targetMi].micros.splice(index, 0, micro);
  focusPk = selected;
  selected = null;
  render(`Moved into ${plan[targetMi].label}.`);
}

function moveMeso(pk, dir) {
  const i = plan.findIndex(m => m.pk === pk);
  const j = dir === "up" ? i - 1 : i + 1;
  if (j < 0 || j >= plan.length) return;
  [plan[i], plan[j]] = [plan[j], plan[i]];
  render(`${plan[j].label} moved ${dir}.`);
  const same = planEl.querySelector(`[data-meso="${pk}"][data-meso-move="${dir}"]`);
  const target = same && !same.disabled ? same : planEl.querySelector(`[data-meso="${pk}"]`);
  if (target) target.focus();
}

function toggleSelect(pk) {
  selected = selected === pk ? null : pk;
  focusPk = pk;
  render(selected === null ? "Put back." : "Picked up. Choose a place-here marker.");
}

// -- Rendering --------------------------------------------------------------

function dropGap(mesoPk, index) {
  const button = el("button", {
    text: "Place here",
    attrs: { type: "button", "data-meso": mesoPk, "data-index": index },
  });
  return el("div", { class: "drop-gap" }, [button]);
}

function mesoHead(meso, index, now) {
  const md = now.meso.get(meso.pk);
  const od = ORIGINAL.meso.get(meso.pk);
  const mesoShifted =
    md.start.getTime() !== od.start.getTime() || md.days !== od.days;

  let meta = "no microcycles";
  if (md.days) {
    const count = meso.micros.length;
    meta =
      `${fmt(md.start)} – ${fmt(md.end)} · ${md.days} days · ` +
      `${count} microcycle${count === 1 ? "" : "s"}`;
    if (mesoShifted) meta += ` · was ${fmt(od.start)}, ${od.days} days`;
  }

  const moves = el("span", { class: "meso-moves" }, [
    el("button", {
      class: "secondary outline",
      text: "▲",
      attrs: {
        type: "button",
        "data-meso": meso.pk,
        "data-meso-move": "up",
        "aria-label": `Move ${meso.label} up`,
        ...(index === 0 ? { disabled: "" } : {}),
      },
    }),
    el("button", {
      class: "secondary outline",
      text: "▼",
      attrs: {
        type: "button",
        "data-meso": meso.pk,
        "data-meso-move": "down",
        "aria-label": `Move ${meso.label} down`,
        ...(index === plan.length - 1 ? { disabled: "" } : {}),
      },
    }),
  ]);

  return el("div", { class: "meso-head" }, [
    el("span", { class: "meso-title", text: meso.label }),
    el("span", {
      class: mesoShifted ? "meso-meta is-shifted" : "meso-meta",
      text: meta,
    }),
    moves,
  ]);
}

function microRow(micro, info) {
  const start = el("span", { class: "micro-cell micro-cell--start" }, [
    el("span", { class: "micro-date", text: fmt(info.start) }),
  ]);
  if (info.isNow) {
    start.append(el("span", { class: "chip chip--now", text: "now" }));
  }
  if (info.moved) {
    const sign = info.delta > 0 ? "+" : "";
    start.append(
      el("span", {
        class: "date-shift",
        text: `was ${fmt(info.origStart)} · ${sign}${info.delta}d`,
      })
    );
  }

  const cells = [
    start,
    el("span", { class: "micro-cell", text: micro.label, attrs: { "data-label": "Type" } }),
    el("span", {
      class: "micro-cell",
      text: String(micro.days),
      attrs: { "data-label": "Days" },
    }),
    el("span", {
      class: "micro-cell",
      text: fmtKm(micro.km),
      attrs: { "data-label": "km" },
    }),
    el("span", {
      class: "micro-cell",
      text: fmtKm(micro.long_km),
      attrs: { "data-label": "Long" },
    }),
    el("span", {
      class: "micro-cell micro-cell--comment",
      text: micro.comment,
      attrs: { "data-label": "Comment" },
    }),
  ];

  const picked = selected === micro.pk;
  if (picked) {
    cells.push(
      el("span", {
        class: "selected-hint",
        text: "Picked up — choose a marker, or tap again to put back",
      })
    );
  }

  let cls = "micro-row";
  if (picked) cls += " is-selected";
  if (info.moved) cls += " is-shifted";

  // While one microcycle is picked up the others are inert: you must put the
  // current one back first (tap it again, or Esc).
  const locked = selected !== null && !picked;
  const attrs = {
    "data-pk": micro.pk,
    role: "button",
    "aria-pressed": String(picked),
  };
  if (locked) {
    // Omit tabindex entirely rather than setting "-1": a div with tabindex
    // "-1" is still focusable by click, and Pico draws its role=button focus
    // ring on it. With no tabindex at all the row cannot take focus.
    attrs["aria-disabled"] = "true";
  } else {
    attrs.tabindex = "0";
  }

  return el("div", { class: cls, attrs }, cells);
}

function render(message) {
  const now = computeDates(plan);
  const { info, shifted, touchingPast } = diffDates(now);
  const src = selected === null ? null : locate(selected);

  const frag = document.createDocumentFragment();
  plan.forEach((meso, mesoIdx) => {
    const section = el("section", { class: "meso-group" }, [
      mesoHead(meso, mesoIdx, now),
    ]);
    const srcSameMeso = src !== null && plan[src.mi].pk === meso.pk;
    // The two slots either side of where the row already sits would put it
    // back exactly where it is, so they are not rendered at all. This holds
    // only within the picked-up row's own mesocycle: the marker on the far
    // side of a group boundary looks adjacent but re-parents the microcycle,
    // which is a real change.
    const isNoop = i => srcSameMeso && (i === src.ci || i === src.ci + 1);

    meso.micros.forEach((micro, i) => {
      if (selected !== null && !isNoop(i)) section.append(dropGap(meso.pk, i));
      section.append(microRow(micro, info.get(micro.pk)));
    });

    if (selected !== null && !isNoop(meso.micros.length)) {
      section.append(dropGap(meso.pk, meso.micros.length));
    } else if (selected === null && !meso.micros.length) {
      section.append(
        el("p", {
          class: "meso-empty",
          text: "Empty — 0 days. This phase contributes nothing to the plan.",
        })
      );
    }
    frag.append(section);
  });

  planEl.replaceChildren(frag);
  document.body.classList.toggle("is-placing", selected !== null);

  const totalDays = plan.reduce(
    (n, m) => n + m.micros.reduce((s, c) => s + c.days, 0),
    0
  );
  metaEl.textContent =
    `Starts ${fmt(new Date(PLAN_START))} · ends ${fmt(now.end)} · ` +
    `${totalDays} days total (reordering never changes plan length).`;

  if (shifted) {
    bannerEl.hidden = false;
    bannerEl.replaceChildren(
      el("strong", {
        text: `${shifted} microcycle${shifted === 1 ? "" : "s"} shift date. `,
      }),
      document.createTextNode(
        touchingPast
          ? `${touchingPast} of them overlap dates you have already trained — the ` +
            "Actual columns for those weeks will re-bucket to whatever workouts " +
            "really fall in the new window."
          : "All of them are in the future, so no recorded workouts change hands."
      )
    );
  } else {
    bannerEl.hidden = true;
  }

  saveBtn.disabled = !isChanged();

  if (focusPk !== null) {
    const row = planEl.querySelector(`.micro-row[data-pk="${focusPk}"]`);
    if (row) row.focus();
    focusPk = null;
  }
  if (message) statusEl.textContent = message;
}

// -- Saving -----------------------------------------------------------------

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  // The banner sits above the list (as in form_base.html) but Save is below it,
  // so on a long plan the message would otherwise appear off-screen.
  errorEl.scrollIntoView({ block: "center", behavior: "smooth" });
}

async function save() {
  errorEl.hidden = true;
  saveBtn.setAttribute("aria-busy", "true");
  saveBtn.disabled = true;
  try {
    const response = await fetch(app.dataset.saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": app.dataset.csrfToken,
      },
      body: JSON.stringify(payload()),
    });
    const result = await response.json().catch(() => ({}));
    if (response.ok && result.redirect) {
      // Keep the reorder page out of history, like the other mutation views.
      location.replace(result.redirect);
      return;
    }
    showError(result.error || "Could not save the new order.");
  } catch {
    showError("Network error — the new order was not saved.");
  }
  saveBtn.removeAttribute("aria-busy");
  saveBtn.disabled = false;
}

// -- Events -----------------------------------------------------------------

// Only the picked-up row responds while a move is pending — see microRow().
const isSelectable = row =>
  selected === null || selected === Number(row.dataset.pk);

function onPlanClick(e) {
  const drop = e.target.closest(".drop-gap button");
  if (drop) {
    place(Number(drop.dataset.meso), Number(drop.dataset.index));
    return;
  }
  const mesoBtn = e.target.closest("[data-meso-move]");
  if (mesoBtn) {
    moveMeso(Number(mesoBtn.dataset.meso), mesoBtn.dataset.mesoMove);
    return;
  }
  const row = e.target.closest(".micro-row");
  if (row && isSelectable(row)) toggleSelect(Number(row.dataset.pk));
}

function onPlanKeydown(e) {
  const row = e.target.closest(".micro-row");
  if (row && isSelectable(row) && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    toggleSelect(Number(row.dataset.pk));
  }
}

function init() {
  const data = JSON.parse(document.getElementById("reorder-data").textContent);
  PLAN_START = `${data.plan_start}T00:00:00`;
  TODAY = new Date(`${data.today}T00:00:00`);
  INITIAL = data.mesocycles;
  ORIGINAL = computeDates(INITIAL);
  plan = structuredClone(INITIAL);

  planEl.addEventListener("click", onPlanClick);
  planEl.addEventListener("keydown", onPlanKeydown);

  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && selected !== null) {
      focusPk = selected;
      selected = null;
      render("Put back.");
      return;
    }
    // Ctrl+S / Cmd+S → Save, matching form_handler.js on the CRUD form views.
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      if (!saveBtn.disabled) saveBtn.click();
    }
  });

  saveBtn.addEventListener("click", save);

  render();
}

if (app) init();
